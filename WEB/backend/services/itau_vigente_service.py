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
    _load_filtros_medibles,
    _medibles_sql,
    _parse_fecha_carga,
    _periodo_from_fecha,
    _producto_values,
    _safe_div,
    negocios_result,
)


# Los RUT sin gestion de ningun ejecutivo quedan en la fila grupal PHOENIX.
DEFAULT_EXECUTIVE = "PHOENIX"
# Cartera Itau Vencida en el CRM de gestiones (dbo.tmp_GEST_CRM).
CRM_CARTERA = 523
# Cobertura gestion: solo cuenta la gestion telefonica, de cualquier usuario menos el discador.
CANAL_GESTION_VALIDA = "LLAMADA"
USUARIOS_SIN_GESTION_VALIDA = ("VDAD",)
# Universo de Itau Vigente dentro de la contencion Itau Vencida.
FASES = (1, 2, 3)
CANALES = ("CALL CENTER", "CONTACT CENTER")
# Desde octubre 2026 tambien entran Inteligencia y los cruces vigente, salvo los RUT del cruce vigente que
# estan carterizados a ejecutivos de Itau Castigo en el mes (esos los mide el panel de castigo).
CANALES_DESDE_2026_10 = (
    "CALL CENTER",
    "CALL CENTER - CRUCE VIGENTE",
    "INTELIGENCIA",
    "CONTACT CENTER",
    "TERRENO PREJUDICIAL - CRUCE VIGENTE",
)
CANALES_AMPLIADOS_DESDE = "2026-10-01"


def _canales(periodo: str) -> tuple[str, ...]:
    return CANALES_DESDE_2026_10 if periodo >= CANALES_AMPLIADOS_DESDE else CANALES


# Desde octubre 2026 no se informa el efectivo recuperado de los casos no medibles.
SIN_EFECTIVO_DESDE = "2026-10-01"


def _con_efectivo(periodo: str) -> bool:
    return periodo < SIN_EFECTIVO_DESDE


# Desde octubre 2026 el resumen lleva % aporte y cobertura gestion.
APORTE_COBERTURA_DESDE = "2026-10-01"
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


def _vigente_en(alias: str, fecha_sql: str) -> str:
    """Condicion SQL: el ejecutivo (alias de dbo.itau_vigente_ejecutivos) esta activo y vigente en fecha_sql
    (desde/hasta NULL = sin limite)."""
    return (
        f"{alias}.activo = 1"
        f" AND ({alias}.desde IS NULL OR {alias}.desde <= {fecha_sql})"
        f" AND ({alias}.hasta IS NULL OR {alias}.hasta >= {fecha_sql})"
    )


def _load_ejecutivos(periodo: str) -> list[str]:
    """Ejecutivos vigentes en algun dia del mes."""
    return [
        _clean_text(row.get("ejecutivo"))
        for row in run_query(
            """
            SELECT ejecutivo
            FROM dbo.itau_vigente_ejecutivos
            WHERE activo = 1
              AND (desde IS NULL OR desde <= EOMONTH(?))
              AND (hasta IS NULL OR hasta >= ?)
            ORDER BY ejecutivo
            """,
            (periodo, periodo),
        )
        if _clean_text(row.get("ejecutivo"))
    ]


def _recupero_castigo(periodo: str, fecha_carga: str) -> tuple[str | None, dict[str, float]]:
    """Recupero Itau Castigo de cada ejecutivo: RUT que tiene carterizados en castigo, en el ultimo recupero
    del mes cargado hasta la fecha consultada."""
    fecha_recupero, filas = _recupero_castigo_ruts(periodo, fecha_carga)
    recupero: dict[str, float] = {}
    for fila in filas:
        recupero[fila["ejecutivo"]] = recupero.get(fila["ejecutivo"], 0.0) + fila["recupero"]
    return fecha_recupero, recupero


@cached_view
def get_recupero_castigo_detalle(filters: dict) -> dict:
    """Recupero castigo por ejecutivo y RUT (la suma por ejecutivo es castigo_recupero del resumen). El archivo
    de recupero de Itau Castigo no trae numero de operacion. Solo RUT con recupero."""
    fecha_carga = _parse_fecha_carga(filters.get("fecha_carga"))
    fecha_recupero, filas = _recupero_castigo_ruts(_periodo_from_fecha(fecha_carga), fecha_carga)
    filas = [fila for fila in filas if fila["recupero"]]
    filas.sort(key=lambda f: (f["ejecutivo"], -f["recupero"], f["rut"]))
    return {"fecha_recupero": fecha_recupero, "filas": filas}


def _recupero_castigo_ruts(periodo: str, fecha_carga: str) -> tuple[str | None, list[dict]]:
    """(fecha del recupero usado, una fila por ejecutivo y RUT carterizado en castigo con su recupero)."""
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
        return None, []

    filas = [
        {
            "ejecutivo": _clean_text(row.get("Ejecutivo")),
            "rut": f"{int(row['RUT'])}-{_clean_text(row.get('DV'))}" if row.get("RUT") is not None else "",
            "nombre": _clean_text(row.get("Nombre")),
            "deuda": float(row.get("Deuda") or 0),
            "recupero": float(row.get("Recupero") or 0),
            "fecha_recupero": _clean_text(row.get("Fecha_Recupero")),
        }
        for row in run_query(
            f"""
            WITH cart AS (
                -- El nombre del carterizado cambia de escritura entre meses: se cruza por la tabla de equivalencias.
                SELECT DISTINCT c.rut, e.ejecutivo
                FROM dbo.tmp_carterizado_ITAU_CASTIGO c
                INNER JOIN dbo.itau_vigente_ejecutivos_castigo a
                    ON UPPER(a.nombre_carterizado) = UPPER(LTRIM(RTRIM(c.ejecutivo)))
                INNER JOIN dbo.itau_vigente_ejecutivos e
                    ON e.usuario = a.usuario
                   AND {_vigente_en("e", "c.mes_carterizado")}
                WHERE c.mes_carterizado = ?
            )
            SELECT
                cart.ejecutivo AS Ejecutivo,
                r.RUT,
                MAX(r.DV) AS DV,
                MAX(LTRIM(RTRIM(CONCAT(r.NOMBRES, ' ', r.APELLIDO_PAT)))) AS Nombre,
                SUM(COALESCE(CAST(r.MONTO_CASTIGADO AS float), 0)) AS Deuda,
                SUM(COALESCE(CAST(r.RECUPERO AS float), 0)) AS Recupero,
                MAX(r.FECHA_RECUPERO) AS Fecha_Recupero
            FROM dbo.recup_itau_castigo r
            INNER JOIN cart
                ON cart.rut = r.RUT
            WHERE r.fecha_carga = ?
              AND r.source_file = ?
            GROUP BY cart.ejecutivo, r.RUT
            """,
            (periodo, fecha_recupero, _recup_source_file(fecha_recupero)),
        )
    ]
    return fecha_recupero, filas


@cached_view
def get_filter_values(fecha_carga: str | None = None) -> dict:
    fechas_carga = [
        r["fecha_carga"]
        for r in run_query(
            # Meses anteriores: solo su ultima carga (la foto de cierre); mes actual: todas las cargas.
            """
            WITH f AS (
                SELECT DISTINCT CAST(fecha_carga AS date) AS fecha
                FROM dbo.contencion_itau_vencida
                WHERE fecha_carga IS NOT NULL
                  AND GESTOR = ?
            )
            SELECT CONVERT(char(10), fecha, 126) AS fecha_carga
            FROM (SELECT fecha, MAX(fecha) OVER (PARTITION BY YEAR(fecha), MONTH(fecha)) AS ultima FROM f) x
            WHERE fecha = ultima
               OR fecha >= DATEFROMPARTS(YEAR(GETDATE()), MONTH(GETDATE()), 1)
            ORDER BY fecha DESC
            """,
            (GESTOR_PHOENIX,),
        )
        if r.get("fecha_carga")
    ]

    fecha = (fecha_carga or "")[:10] or (fechas_carga[0] if fechas_carga else "")
    return {
        "fechas_carga": fechas_carga,
        "ejecutivos": _load_ejecutivos(_periodo_from_fecha(fecha)) if fecha else [],
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


def _universo_canal(periodo: str, con_fases: bool = True) -> str:
    """Universo Itau Vigente dentro de la contencion: los canales del mes y, para el cumplimiento, fases 1 a 3."""
    fases = f"AND b.FASE_PROY_MAX IN ({', '.join(str(fase) for fase in FASES)})" if con_fases else ""
    sql = f"{fases} AND UPPER(LTRIM(RTRIM(b.CANAL))) IN ({_in_list(_canales(periodo))})"
    if periodo >= CANALES_AMPLIADOS_DESDE:
        # periodo viene de _periodo_from_fecha (YYYY-MM-DD): se puede interpolar. Va como un solo NOT EXISTS
        # con cruce por igualdad: escrito como NOT (canal AND EXISTS) no admite el OPTION (HASH JOIN) de las consultas.
        sql += f"""
          AND NOT EXISTS (
              SELECT 1
              FROM dbo.tmp_carterizado_ITAU_CASTIGO cc
              WHERE cc.mes_carterizado = '{periodo}'
                AND cc.rut = b.RUT
                AND UPPER(b.CANAL) LIKE '%CRUCE VIGENTE%'
          )"""
    return sql


def _base_cte(periodo: str, universo_sql: str | None = None) -> str:
    """CTE `base` del universo Itau Vigente (o el universo que se indique en universo_sql, cuyos parametros van
    despues de estos). Parametros: periodo, fecha_carga (gestiones), fecha_carga, GESTOR.
    Cada RUT (su saldo inicial y lo contenido) va al ejecutivo con la mejor gestion del mes: primero el peso
    de la respuesta y, a igual peso, la mas reciente. Solo cuentan las gestiones de los ejecutivos de Itau Vigente."""
    return f"""
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
           AND {_vigente_en("e", "g.GestionFecha")}
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
            COALESCE(CAST(b.SALDO_CONT AS float), 0) AS SALDO_CONT,
            b.OPER,
            b.NOMBRE,
            COALESCE(CAST(b.RENE_MES AS int), 0) AS RENE_MES,
            UPPER(LTRIM(RTRIM(b.CANAL))) AS CANAL,
            LTRIM(RTRIM(b.DETALLE_MARCA)) AS MARCA
        FROM dbo.contencion_itau_vencida b
        LEFT JOIN mejor_gestion mg
            ON mg.RUT = b.RUT
           AND mg.rn = 1
        WHERE b.fecha_carga = ?
          AND b.GESTOR = ?
          {_universo_canal(periodo) if universo_sql is None else universo_sql}
    )
    """


def _recupero_no_medible(periodo: str, fecha_carga: str, ejecutivo: str = "") -> tuple[dict, dict[str, tuple[int, float]]]:
    """Efectivo recuperado de los casos no medibles de Itau Vencida, por ejecutivo de la mejor gestion (sin gestion:
    PHOENIX). La columna EFECT_RECUPERADO del banco viene mal; se usan las cuotas pagadas con la misma logica del
    export de Panel Administrativo > Itau Vencida (administrativas_itau_service.get_cuotas_pagadas_export_rows):
    cada archivo de cuotas del mes se compara con el siguiente y la cuota que desaparece se pago. Solo operaciones
    contenidas en el mes (SALDO_CONT informado). Efectivo = suma del ValorCuota de esas cuotas, hasta la fecha consultada."""
    sql, params = _recupero_no_medible_sql(
        periodo,
        fecha_carga,
        ejecutivo,
        "SELECT o.Ejecutivo, COUNT(*) AS Cuotas, SUM(p.ValorCuota) AS Efectivo",
        "GROUP BY o.Ejecutivo",
    )
    archivos = run_query(
        """
        SELECT CONVERT(char(10), MIN(CAST(FechaDeProceso AS date)), 126) AS desde,
               CONVERT(char(10), MAX(CAST(FechaDeProceso AS date)), 126) AS hasta
        FROM dbo.cuotas_itau_vencida
        WHERE FechaDeProceso >= ?
          AND CAST(FechaDeProceso AS date) <= ?
        """,
        (periodo, fecha_carga),
    )
    fotos = {"foto_base": archivos[0].get("desde"), "foto_actual": archivos[0].get("hasta")} if archivos else {}
    return fotos, {
        (row.get("Ejecutivo") or DEFAULT_EXECUTIVE): (int(row.get("Cuotas") or 0), float(row.get("Efectivo") or 0))
        for row in run_query(sql, tuple(params))
    }


@cached_view
def get_efectivo_detalle(filters: dict) -> list[dict]:
    """Efectivo recuperado de los casos no medibles, una fila por operacion (misma regla que la pestaña
    Efectivo recuperado: la suma por ejecutivo da recupero_nm_efectivo)."""
    fecha_carga = _parse_fecha_carga(filters.get("fecha_carga"))
    periodo = _periodo_from_fecha(fecha_carga)
    if not _con_efectivo(periodo):
        return []
    sql, params = _recupero_no_medible_sql(
        periodo,
        fecha_carga,
        _clean_text(filters.get("ejecutivo")),
        "SELECT o.Ejecutivo, o.OPER, o.RUT, o.NOMBRE, COUNT(*) AS Cuotas, SUM(p.ValorCuota) AS Efectivo",
        "GROUP BY o.Ejecutivo, o.OPER, o.RUT, o.NOMBRE",
    )
    filas = [
        {
            "ejecutivo": row.get("Ejecutivo") or DEFAULT_EXECUTIVE,
            "operacion": _clean_text(row.get("OPER")),
            "rut": str(int(row["RUT"])) if row.get("RUT") is not None else "",
            "nombre": _clean_text(row.get("NOMBRE")),
            "cuotas": int(row.get("Cuotas") or 0),
            "efectivo": float(row.get("Efectivo") or 0),
        }
        for row in run_query(sql, tuple(params))
    ]
    filas.sort(key=lambda f: (f["ejecutivo"] == DEFAULT_EXECUTIVE, f["ejecutivo"], -f["efectivo"], f["operacion"]))
    return filas


def _recupero_no_medible_sql(periodo: str, fecha_carga: str, ejecutivo: str, select_sql: str, group_sql: str) -> tuple[str, list]:
    """Consulta de cuotas pagadas de los casos no medibles; select_sql/group_sql definen el nivel (ejecutivo u operacion)."""
    # No medible = todo lo de la contencion Phoenix que no cumple los filtros de casos medibles de Vencida.
    medibles_sql, medibles_params = _medibles_sql(_load_filtros_medibles(periodo))
    universo_sql = f"AND NOT (1 = 1 {medibles_sql})"
    params: list = [
        periodo, fecha_carga, fecha_carga, GESTOR_PHOENIX, *medibles_params,
        periodo, fecha_carga, periodo, fecha_carga, periodo, fecha_carga, GESTOR_PHOENIX,
    ]
    filter_sql = ""
    if ejecutivo:
        filter_sql = "WHERE UPPER(o.Ejecutivo) = UPPER(LTRIM(RTRIM(?)))"
        params.append(ejecutivo)
    sql = (
        _base_cte(periodo, universo_sql)
        + f""", ops AS (
        SELECT Ejecutivo, OPER, MAX(RUT) AS RUT, MAX(NOMBRE) AS NOMBRE
        FROM base
        WHERE OPER IS NOT NULL
        GROUP BY Ejecutivo, OPER
    ), fechas AS (
        SELECT FechaDeProceso, LEAD(FechaDeProceso) OVER (ORDER BY FechaDeProceso) AS FechaDeProcesoSiguiente
        FROM (
            SELECT DISTINCT CAST(FechaDeProceso AS date) AS FechaDeProceso
            FROM dbo.cuotas_itau_vencida
            WHERE FechaDeProceso >= ?
              AND CAST(FechaDeProceso AS date) <= ?
        ) f
    ), cuotas AS (
        SELECT DISTINCT CAST(FechaDeProceso AS date) AS FechaDeProceso, NumeroOperacion, NumeroCuota, ValorCuota
        FROM dbo.cuotas_itau_vencida
        WHERE FechaDeProceso >= ?
          AND CAST(FechaDeProceso AS date) <= ?
    ), pagadas AS (
        SELECT c.NumeroOperacion, COALESCE(CAST(c.ValorCuota AS float), 0) AS ValorCuota
        FROM fechas f
        INNER JOIN cuotas c
            ON c.FechaDeProceso = f.FechaDeProceso
        LEFT JOIN cuotas sig
            ON sig.FechaDeProceso = f.FechaDeProcesoSiguiente
           AND sig.NumeroOperacion = c.NumeroOperacion
           AND sig.NumeroCuota = c.NumeroCuota
        WHERE f.FechaDeProcesoSiguiente IS NOT NULL
          AND sig.NumeroOperacion IS NULL
    ), contenidas AS (
        SELECT DISTINCT OPER
        FROM dbo.contencion_itau_vencida
        WHERE fecha_carga >= ?
          AND fecha_carga <= ?
          AND GESTOR = ?
          AND SALDO_CONT IS NOT NULL
    )
    {select_sql}
    FROM ops o
    INNER JOIN contenidas k
        ON k.OPER = o.OPER
    INNER JOIN pagadas p
        ON p.NumeroOperacion = o.OPER
    {filter_sql}
    {group_sql}
    OPTION (HASH JOIN)
    """
    )
    return sql, params


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

    sql = (
        _base_cte(periodo)
        + f"""
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
    )

    metas, meta_castigo = _load_metas(periodo)
    ejecutivos = _load_ejecutivos(periodo)
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

    # Efectivo recuperado de los casos no medibles de Vencida: informativo, no entra al cumplimiento.
    efectivo = _con_efectivo(periodo)
    fotos_cuotas, recupero_nm = _recupero_no_medible(periodo, fecha_carga, ejecutivo) if efectivo else (None, {})
    for nombre in recupero_nm:
        por_ejecutivo.setdefault(nombre, _empty_acc())

    rows = []
    for nombre, acc in sorted(por_ejecutivo.items(), key=lambda item: (item[0] == DEFAULT_EXECUTIVE, item[0])):
        result = _result(nombre, len(acc["casos"]), acc, metas, castigo)
        if nombre != DEFAULT_EXECUTIVE:
            result["castigo_recupero"] = recupero_ejecutivo.get(nombre, 0.0)
        result["recupero_nm_cuotas"], result["recupero_nm_efectivo"] = recupero_nm.get(nombre, (0, 0.0))
        rows.append(result)

    total_result = _result("Total general", len(total["casos"]), total, metas, castigo)
    if castigo:
        total_result["castigo_recupero"] = castigo["recupero"]
    total_result["recupero_nm_cuotas"] = sum(cuotas for cuotas, _ in recupero_nm.values())
    total_result["recupero_nm_efectivo"] = sum(efectivo for _, efectivo in recupero_nm.values())

    # % aporte (como La Araucana): lo contenido por cada ejecutivo sobre la bolsa de todo lo contenido por los
    # ejecutivos. PHOENIX (sin gestion) no entra a la bolsa ni lleva aporte. Filtrando por ejecutivo, la bolsa
    # sigue siendo la de todos.
    # La cobertura de gestion es grupal (todas las marcas y fases, gestion telefonica de cualquier usuario sin VDAD,
    # antes del pago): el mismo % en cada ejecutivo, aunque se filtre.
    # Aporte y cobertura solo existen desde octubre 2026; los meses anteriores no los llevan.
    con_aporte = periodo >= APORTE_COBERTURA_DESDE
    bolsa = None
    cobertura = None
    if con_aporte and ejecutivo:
        completo = get_general({"fecha_carga": fecha_carga})
        bolsa = completo["aporte_bolsa"]
        cobertura = completo["cobertura_gestion"]
    elif con_aporte:
        bolsa = sum(row["saldo_cont"] for row in rows if row["ejecutivo"] != DEFAULT_EXECUTIVE)
        cobertura = _cobertura_gestion(periodo, fecha_carga)
    for row in rows:
        es_phoenix = row["ejecutivo"] == DEFAULT_EXECUTIVE
        row["pct_aporte"] = None if es_phoenix or not con_aporte else _safe_div(row["saldo_cont"], bolsa)
        row["cobertura_gestion"] = None if es_phoenix or not con_aporte else cobertura["pct"]
    total_result["pct_aporte"] = sum(row["pct_aporte"] or 0 for row in rows) if con_aporte else None
    total_result["cobertura_gestion"] = cobertura["pct"] if con_aporte else None

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
        "canales": list(_canales(periodo)),
        "metas": metas_vista,
        "castigo": castigo,
        "efectivo_recuperado": efectivo,
        "con_aporte_cobertura": con_aporte,
        "aporte_bolsa": bolsa,
        "cobertura_gestion": cobertura,
        "recupero_no_medible": fotos_cuotas,
        "rows": rows,
        "total": total_result,
    }


@cached_view
def get_negocios(filters: dict) -> dict:
    fecha_carga = _parse_fecha_carga(filters.get("fecha_carga"))
    periodo = _periodo_from_fecha(fecha_carga)
    ejecutivo = _clean_text(filters.get("ejecutivo"))

    # Negocios de Vigente = todo el Call/Contact Center (cualquier fase). El ejecutivo es el de la mejor
    # gestion del mes, igual que el resumen; lo que no tiene gestion queda en PHOENIX.
    params: list = [periodo, fecha_carga, fecha_carga, GESTOR_PHOENIX]
    filter_sql = ""
    if ejecutivo:
        filter_sql = "AND UPPER(Ejecutivo) = UPPER(LTRIM(RTRIM(?)))"
        params.append(ejecutivo)
    rows = run_query(
        _base_cte(periodo, _universo_canal(periodo, con_fases=False))
        + f"""
    SELECT Ejecutivo, RUT, NOMBRE, OPER, Producto, Fase, SALDO_INI, SALDO_CONT
    FROM base
    WHERE RENE_MES = 1
    {filter_sql}
    OPTION (HASH JOIN)
    """,
        tuple(params),
    )
    return {"fecha_carga": fecha_carga, "periodo": periodo, **negocios_result(rows)}


def _cobertura_gestion(periodo: str, fecha_carga: str) -> dict:
    """Cobertura de gestion grupal: RUT del universo Vigente del mes (todos sus canales y marcas, cualquier fase)
    con una gestion valida antes del pago. Valida = telefonica (canal LLAMADA) de cualquier usuario del CRM, salvo
    el discador VDAD. La fecha de pago es la primera carga de contencion del mes en que el RUT aparece con saldo
    contenido (igual que Itau Vencida); si aun no paga, vale cualquier gestion hasta la fecha consultada.
    Es grupal: el mismo % va en todos los ejecutivos."""
    rows = run_query(
        _base_cte(periodo, _universo_canal(periodo, con_fases=False))
        + f""", pago AS (
        SELECT RUT, MIN(fecha_carga) AS fecha_pago
        FROM (
            SELECT RUT, fecha_carga
            FROM dbo.contencion_itau_vencida
            WHERE fecha_carga >= ?
              AND fecha_carga <= ?
              AND GESTOR = ?
            GROUP BY RUT, fecha_carga
            HAVING SUM(COALESCE(CAST(SALDO_CONT AS float), 0)) > 0
        ) x
        GROUP BY RUT
    ), gestion AS (
        SELECT TRY_CAST(g.rut AS bigint) AS RUT, MIN(CAST(g.GestionFecha AS date)) AS primera_gestion
        FROM dbo.tmp_GEST_CRM g
        INNER JOIN dbo.kpi_accion_canal ac
            ON ac.valor = UPPER(LTRIM(RTRIM(g.AccionGestion)))
           AND ac.canal = '{CANAL_GESTION_VALIDA}'
        WHERE g.cartera = {CRM_CARTERA}
          AND g.GestionFecha >= ?
          AND g.GestionFecha <= ?
          AND UPPER(LTRIM(RTRIM(g.UsuarioGestion))) NOT IN ({_in_list(USUARIOS_SIN_GESTION_VALIDA)})
        GROUP BY TRY_CAST(g.rut AS bigint)
    )
    -- Primero por RUT: con COUNT(DISTINCT ...) directo el OPTION (HASH JOIN) no arma plan.
    SELECT COUNT(*) AS Ruts, SUM(Gestionado) AS Gestionados
    FROM (
        SELECT
            b.RUT,
            MAX(CASE
                WHEN ge.primera_gestion IS NOT NULL AND (p.fecha_pago IS NULL OR ge.primera_gestion < p.fecha_pago)
                THEN 1 ELSE 0
            END) AS Gestionado
        FROM base b
        LEFT JOIN pago p
            ON p.RUT = b.RUT
        LEFT JOIN gestion ge
            ON ge.RUT = b.RUT
        GROUP BY b.RUT
    ) x
    OPTION (HASH JOIN)
    """,
        (periodo, fecha_carga, fecha_carga, GESTOR_PHOENIX, periodo, fecha_carga, GESTOR_PHOENIX, periodo, fecha_carga),
    )
    ruts = int(rows[0].get("Ruts") or 0) if rows else 0
    gestionados = int(rows[0].get("Gestionados") or 0) if rows else 0
    return {"ruts": ruts, "gestionados": gestionados, "pct": _safe_div(gestionados, ruts) if ruts else None}
