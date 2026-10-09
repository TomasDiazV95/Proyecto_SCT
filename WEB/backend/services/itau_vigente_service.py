from __future__ import annotations

from cache import cached_view
from database import run_query
from services.itau_castigo_service import _recup_source_file
from services.itau_vencida_service import (
    CUMPLIMIENTO_MAX,
    GESTOR_PHOENIX,
    PRODUCTOS,
    _add,
    _cap,
    _clean_text,
    _empty_acc,
    _fases_detalle,
    _parse_fecha_carga,
    _periodo_from_fecha,
    _producto_values,
    _safe_div,
)


# Los RUT sin gestion de ningun ejecutivo quedan en la fila grupal PHOENIX.
DEFAULT_EXECUTIVE = "PHOENIX"
# Cartera Itau Vencida en el CRM de gestiones (dbo.tmp_GEST_CRM).
CRM_CARTERA = 523
# Universo de Itau Vigente dentro de la contencion Itau Vencida.
FASES = (1, 2, 3)
CANALES = ("CALL CENTER", "CONTACT CENTER")
VARIABLE_CASTIGO = "CASTIGO"
# Respuestas con mas peso al elegir la mejor gestion del RUT: compromiso, pago o renegociacion.
RESPUESTAS_COMPROMISO = (
    "PAGADO",
    "COMPROMISO CONTENCION",
    "COMPROMISO CONTENCION O ABONO",
    "COMPROMISO NORMALIZACION",
    "PROMESA DE PAGO ACEPTA NUEVA LLAMADA",
    "RENEGOCIACION CURSADA",
    "EN PROCESO RENEGOCIACION NUEVA LLAMADA",
    "SOLICITA LLAMADO DE EJECUTIVO PARA RENEGOCIAR",
)


def _in_list(values: tuple) -> str:
    return ", ".join("'{}'".format(str(value).replace("'", "''")) for value in values)


def _load_metas(periodo: str) -> tuple[dict[str, dict], dict | None]:
    """Metas de la ultima vigencia <= periodo: ({producto: {"ponderacion": x, "fases": {fase: meta}}}, castigo)."""
    metas: dict[str, dict] = {}
    castigo = None
    for row in run_query(
        """
        SELECT variable, fase, CAST(meta AS float) AS meta, CAST(ponderacion AS float) AS ponderacion
        FROM dbo.itau_vigente_metas
        WHERE activo = 1
          AND periodo = (SELECT MAX(periodo) FROM dbo.itau_vigente_metas WHERE activo = 1 AND periodo <= ?)
        """,
        (periodo,),
    ):
        variable = _clean_text(row.get("variable")).upper()
        meta = float(row.get("meta") or 0)
        ponderacion = float(row.get("ponderacion") or 0)
        if variable == VARIABLE_CASTIGO:
            castigo = {"meta": meta, "ponderacion": ponderacion}
            continue
        entry = metas.setdefault(variable, {"ponderacion": ponderacion, "fases": {}})
        entry["fases"][int(row["fase"])] = meta
    return metas, castigo


def _load_ejecutivos() -> list[str]:
    return [
        _clean_text(row.get("ejecutivo"))
        for row in run_query("SELECT ejecutivo FROM dbo.itau_vigente_ejecutivos WHERE activo = 1 ORDER BY ejecutivo")
        if _clean_text(row.get("ejecutivo"))
    ]


def _recupero_castigo(periodo: str, fecha_carga: str) -> tuple[str | None, dict[str, float]]:
    """Recupero Itau Castigo de cada ejecutivo: RUT que tiene carterizados en castigo, en el ultimo recupero
    del mes cargado hasta la fecha consultada."""
    rows = run_query(
        """
        SELECT CONVERT(char(10), MAX(fecha_carga), 126) AS fecha_carga
        FROM dbo.recup_itau_castigo
        WHERE fecha_carga >= ?
          AND fecha_carga <= ?
        """,
        (periodo, fecha_carga),
    )
    fecha_recupero = _clean_text(rows[0].get("fecha_carga")) or None if rows else None
    if not fecha_recupero:
        return None, {}

    recupero = {
        _clean_text(row.get("Ejecutivo")): float(row.get("Recupero") or 0)
        for row in run_query(
            """
            WITH cart AS (
                -- El nombre del carterizado cambia de escritura entre meses: se cruza por la tabla de equivalencias.
                SELECT DISTINCT c.rut, e.ejecutivo
                FROM dbo.tmp_carterizado_ITAU_CASTIGO c
                INNER JOIN dbo.itau_vigente_ejecutivos_castigo a
                    ON UPPER(a.nombre_carterizado) = UPPER(LTRIM(RTRIM(c.ejecutivo)))
                INNER JOIN dbo.itau_vigente_ejecutivos e
                    ON e.usuario = a.usuario
                   AND e.activo = 1
                WHERE c.mes_carterizado = ?
            )
            SELECT
                cart.ejecutivo AS Ejecutivo,
                SUM(COALESCE(CAST(r.RECUPERO AS float), 0)) AS Recupero
            FROM dbo.recup_itau_castigo r
            INNER JOIN cart
                ON cart.rut = r.RUT
            WHERE r.fecha_carga = ?
              AND r.source_file = ?
            GROUP BY cart.ejecutivo
            """,
            (periodo, fecha_recupero, _recup_source_file(fecha_recupero)),
        )
    }
    return fecha_recupero, recupero


@cached_view
def get_filter_values(fecha_carga: str | None = None) -> dict:
    fechas_carga = [
        r["fecha_carga"]
        for r in run_query(
            """
            SELECT DISTINCT CONVERT(char(10), fecha_carga, 126) AS fecha_carga
            FROM dbo.contencion_itau_vencida
            WHERE fecha_carga IS NOT NULL
              AND GESTOR = ?
            ORDER BY fecha_carga DESC
            """,
            (GESTOR_PHOENIX,),
        )
        if r.get("fecha_carga")
    ]

    return {
        "fechas_carga": fechas_carga,
        "ejecutivos": _load_ejecutivos(),
    }


def _result(nombre: str, casos: int, acc: dict, metas: dict, castigo: dict | None) -> dict:
    out = {
        "ejecutivo": nombre,
        "casos": casos,
        "operaciones": acc["operaciones"],
        "saldo_ini": acc["saldo_ini"],
        "saldo_cont": acc["saldo_cont"],
        "pct_contencion": _safe_div(acc["saldo_cont"], acc["saldo_ini"]),
    }

    ponderado = 0.0
    peso_total = 0.0
    for producto in PRODUCTOS:
        cumplimiento = _producto_values(out, producto, acc[producto])
        if cumplimiento is not None:
            peso = metas.get(producto, {}).get("ponderacion", 0.0)
            ponderado += cumplimiento * peso
            peso_total += peso

    # El castigo es grupal: todos los ejecutivos llevan el mismo cumplimiento. La fila grupal PHOENIX no lo lleva.
    out["castigo_recupero"] = None
    out["castigo_cumplimiento"] = None
    if castigo and nombre != DEFAULT_EXECUTIVE:
        out["castigo_cumplimiento"] = castigo["cumplimiento"]
        ponderado += castigo["cumplimiento"] * castigo["ponderacion"]
        peso_total += castigo["ponderacion"]

    # Si el ejecutivo no tiene saldo con meta en un producto, su ponderacion se reparte en el resto.
    out["cumplimiento"] = _safe_div(ponderado, peso_total) if peso_total and nombre != DEFAULT_EXECUTIVE else None
    out["fases"] = _fases_detalle(acc, metas)
    return out


@cached_view
def get_general(filters: dict) -> dict:
    fecha_carga = _parse_fecha_carga(filters.get("fecha_carga"))
    periodo = _periodo_from_fecha(fecha_carga)
    ejecutivo = _clean_text(filters.get("ejecutivo"))

    params: list = [periodo, fecha_carga, fecha_carga, GESTOR_PHOENIX]
    filter_sql = ""
    if ejecutivo:
        filter_sql = "WHERE UPPER(Ejecutivo) = UPPER(LTRIM(RTRIM(?)))"
        params.append(ejecutivo)

    # Cada RUT (su saldo inicial y lo contenido) va al ejecutivo con la mejor gestion del mes: primero el peso
    # de la respuesta y, a igual peso, la mas reciente. Solo cuentan las gestiones de los ejecutivos de Itau Vigente.
    sql = f"""
    WITH gest AS (
        SELECT
            TRY_CAST(g.rut AS bigint) AS RUT,
            e.ejecutivo AS Ejecutivo,
            g.GestionFecha,
            g.GestionHora,
            CASE
                WHEN UPPER(LTRIM(RTRIM(g.RespuestaGestion))) IN ({_in_list(RESPUESTAS_COMPROMISO)}) THEN 1
                WHEN UPPER(LTRIM(RTRIM(g.ContactoGestion))) = 'TITULAR' THEN 2
                WHEN UPPER(LTRIM(RTRIM(g.ContactoGestion))) IN ('TERCERO', 'TERCEROS') THEN 3
                ELSE 4
            END AS peso_gestion
        FROM dbo.tmp_GEST_CRM g
        INNER JOIN dbo.itau_vigente_ejecutivos e
            ON e.usuario = UPPER(LTRIM(RTRIM(g.UsuarioGestion)))
           AND e.activo = 1
        WHERE g.cartera = {CRM_CARTERA}
          AND g.GestionFecha >= ?
          AND g.GestionFecha <= ?
    ), mejor_gestion AS (
        SELECT
            RUT,
            Ejecutivo,
            ROW_NUMBER() OVER (
                PARTITION BY RUT
                ORDER BY peso_gestion ASC, GestionFecha DESC, GestionHora DESC
            ) AS rn
        FROM gest
        WHERE RUT IS NOT NULL
    ), base AS (
        SELECT
            ISNULL(mg.Ejecutivo, '{DEFAULT_EXECUTIVE}') AS Ejecutivo,
            b.RUT,
            CASE UPPER(LTRIM(RTRIM(b.GLOSA_TIPO_CARTERA)))
                WHEN 'CONSUMO' THEN 'CONSUMO'
                WHEN 'VIVIENDA' THEN 'HIPOTECARIO'
                ELSE 'OTRO'
            END AS Producto,
            CAST(b.FASE_PROY_MAX AS int) AS Fase,
            COALESCE(CAST(b.SALDO_INI AS float), 0) AS SALDO_INI,
            COALESCE(CAST(b.SALDO_CONT AS float), 0) AS SALDO_CONT
        FROM dbo.contencion_itau_vencida b
        LEFT JOIN mejor_gestion mg
            ON mg.RUT = b.RUT
           AND mg.rn = 1
        WHERE b.fecha_carga = ?
          AND b.GESTOR = ?
          AND b.FASE_PROY_MAX IN ({", ".join(str(fase) for fase in FASES)})
          AND UPPER(LTRIM(RTRIM(b.CANAL))) IN ({_in_list(CANALES)})
    )
    SELECT
        Ejecutivo,
        Producto,
        Fase,
        RUT,
        COUNT(*) AS Operaciones,
        SUM(SALDO_INI) AS Saldo_Ini,
        SUM(SALDO_CONT) AS Saldo_Cont
    FROM base
    {filter_sql}
    GROUP BY Ejecutivo, Producto, Fase, RUT
    OPTION (HASH JOIN)
    """

    metas, meta_castigo = _load_metas(periodo)
    ejecutivos = _load_ejecutivos()
    # Los ejecutivos se muestran aunque todavia no se lleven ningun RUT.
    por_ejecutivo: dict[str, dict] = {
        nombre: _empty_acc() for nombre in ejecutivos if not ejecutivo or nombre.upper() == ejecutivo.upper()
    }
    total = _empty_acc()
    for row in run_query(sql, tuple(params)):
        nombre = row.get("Ejecutivo") or DEFAULT_EXECUTIVE
        acc = por_ejecutivo.setdefault(nombre, _empty_acc())
        acc["casos"].add(row.get("RUT"))
        total["casos"].add(row.get("RUT"))
        _add(acc, row, metas)
        _add(total, row, metas)

    # El recupero de castigo es la suma de todos los ejecutivos, aunque se filtre por uno.
    fecha_recupero, recupero_ejecutivo = _recupero_castigo(periodo, fecha_carga)
    castigo = None
    if meta_castigo:
        recupero = sum(recupero_ejecutivo.values())
        castigo = {
            "recupero": recupero,
            "meta": meta_castigo["meta"],
            "ponderacion": meta_castigo["ponderacion"],
            "cumplimiento": _cap(_safe_div(recupero, meta_castigo["meta"]), CUMPLIMIENTO_MAX),
            "fecha_recupero": fecha_recupero,
        }

    rows = []
    for nombre, acc in sorted(por_ejecutivo.items(), key=lambda item: (item[0] == DEFAULT_EXECUTIVE, item[0])):
        result = _result(nombre, len(acc["casos"]), acc, metas, castigo)
        if nombre != DEFAULT_EXECUTIVE:
            result["castigo_recupero"] = recupero_ejecutivo.get(nombre, 0.0)
        rows.append(result)

    total_result = _result("Total general", len(total["casos"]), total, metas, castigo)
    if castigo:
        total_result["castigo_recupero"] = castigo["recupero"]

    metas_vista = [
        {
            "producto": producto,
            "fase": fase,
            "meta_contencion": meta,
            "ponderacion": metas[producto]["ponderacion"],
        }
        for producto in PRODUCTOS
        if producto in metas
        for fase, meta in sorted(metas[producto]["fases"].items())
    ]

    return {
        "fecha_carga": fecha_carga,
        "periodo": periodo,
        "metas": metas_vista,
        "castigo": castigo,
        "rows": rows,
        "total": total_result,
    }
