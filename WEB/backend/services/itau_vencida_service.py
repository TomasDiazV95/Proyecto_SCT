from __future__ import annotations

from datetime import date, datetime

from database import run_query


DEFAULT_EXECUTIVE = "PHOENIX"
GESTOR_PHOENIX = "PHOENIX"


def _clean_text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _parse_fecha_carga(value: str | None) -> str:
    text = _clean_text(value)
    if not text:
        rows = run_query(
            """
            SELECT TOP 1 CONVERT(char(10), fecha_carga, 126) AS fecha_carga
            FROM dbo.contencion_itau_vencida
            WHERE fecha_carga IS NOT NULL
              AND GESTOR = ?
            GROUP BY fecha_carga
            ORDER BY fecha_carga DESC
            """,
            (GESTOR_PHOENIX,),
        )
        if not rows or not rows[0].get("fecha_carga"):
            raise RuntimeError("No hay fechas de carga disponibles para Itaú Vencida")
        return str(rows[0]["fecha_carga"])

    if len(text) >= 10:
        text = text[:10]

    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass

    raise RuntimeError(f"Fecha de carga invalida: {value}")


def _periodo_from_fecha(fecha_carga: str) -> str:
    parsed = date.fromisoformat(fecha_carga)
    return parsed.replace(day=1).isoformat()


def _cap(value: float, max_value: float = 1.3) -> float:
    return max(0.0, min(value, max_value))


def _safe_div(num: float, den: float) -> float:
    if den is None or den == 0:
        return 0.0
    return num / den


PRODUCTOS = ("CONSUMO", "HIPOTECARIO")
CUMPLIMIENTO_MAX = 1.3


def _load_metas(periodo: str) -> dict[str, dict]:
    """Metas de la ultima vigencia <= periodo: {producto: {"ponderacion": x, "fases": {fase: meta}}}."""
    metas: dict[str, dict] = {}
    for row in run_query(
        """
        SELECT producto, fase, CAST(meta_contencion AS float) AS meta_contencion, CAST(ponderacion AS float) AS ponderacion
        FROM dbo.itau_vencida_metas
        WHERE activo = 1
          AND periodo = (SELECT MAX(periodo) FROM dbo.itau_vencida_metas WHERE activo = 1 AND periodo <= ?)
        """,
        (periodo,),
    ):
        producto = _clean_text(row.get("producto")).upper()
        entry = metas.setdefault(producto, {"ponderacion": float(row.get("ponderacion") or 0), "fases": {}})
        entry["fases"][int(row["fase"])] = float(row.get("meta_contencion") or 0)
    return metas


# Carterizado deduplicado por RUT para el mes, para no duplicar saldos.
BASE_CTE = f"""
WITH carterizado AS (
    SELECT
        LTRIM(RTRIM(c.rut)) AS rut,
        LTRIM(RTRIM(c.ejecutivo)) AS ejecutivo,
        ROW_NUMBER() OVER (
            PARTITION BY LTRIM(RTRIM(c.rut))
            ORDER BY c.fecha_carga DESC, c.id DESC
        ) AS rn
    FROM dbo.tmp_carterizado_ITAU_VENCIDA c
    WHERE c.mes_carterizado = ?
), base AS (
    SELECT
        ISNULL(NULLIF(car.ejecutivo, ''), '{DEFAULT_EXECUTIVE}') AS Ejecutivo,
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
    LEFT JOIN carterizado car
        ON car.rut = CONVERT(varchar(20), b.RUT)
       AND car.rn = 1
    WHERE b.fecha_carga = ?
      AND b.GESTOR = ?
      /*MEDIBLES*/
)
"""

# Columnas de la contencion que se pueden usar como filtro de casos medibles (lista blanca:
# el nombre de columna se interpola en el SQL, los valores siempre van como parametros).
COLUMNAS_MEDIBLES = ("DETALLE_MARCA", "CANAL", "PRODUCTO", "SEGMENTO")


def _load_filtros_medibles(periodo: str) -> list[dict]:
    """Valores medibles del mes (periodo 'YYYY-MM' en la tabla). No se heredan del mes anterior."""
    return [
        {
            "columna": _clean_text(row.get("columna")).upper(),
            "valor": _clean_text(row.get("valor")),
        }
        for row in run_query(
            """
            SELECT columna, valor
            FROM dbo.itau_vencida_filtros_medibles
            WHERE periodo = ?
              AND activo = 1
            ORDER BY columna, valor
            """,
            (periodo[:7],),
        )
    ]


def _medibles_sql(filtros: list[dict]) -> tuple[str, list]:
    """Solo es medible lo configurado: en cada columna con valores, el caso debe tener uno de ellos
    (columnas con AND). Una columna sin valores no restringe. Un mes sin nada configurado no tiene casos medibles."""
    if not filtros:
        return "AND 1 = 0", []
    clauses: list[str] = []
    params: list = []
    for columna in COLUMNAS_MEDIBLES:
        valores = [f["valor"].upper() for f in filtros if f["columna"] == columna]
        if valores:
            clauses.append(f"AND ISNULL(UPPER(LTRIM(RTRIM(b.[{columna}]))), '') IN ({', '.join('?' for _ in valores)})")
            params.extend(valores)
    return "\n      ".join(clauses), params


def _base_cte(periodo: str, fecha_carga: str, filtros: list[dict]) -> tuple[str, list]:
    medibles_sql, medibles_params = _medibles_sql(filtros)
    return BASE_CTE.replace("/*MEDIBLES*/", medibles_sql), [periodo, fecha_carga, GESTOR_PHOENIX, *medibles_params]


def get_filter_values() -> dict:
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

    ejecutivos: list[str] = []
    if fechas_carga:
        fecha_carga = fechas_carga[0]
        periodo = _periodo_from_fecha(fecha_carga)
        cte_sql, cte_params = _base_cte(periodo, fecha_carga, _load_filtros_medibles(periodo))
        ejecutivos = [
            r["Ejecutivo"]
            for r in run_query(
                cte_sql + "SELECT DISTINCT Ejecutivo FROM base ORDER BY Ejecutivo",
                tuple(cte_params),
            )
            if r.get("Ejecutivo")
        ]

    return {
        "fechas_carga": fechas_carga,
        "ejecutivos": ejecutivos,
    }


def _empty_acc() -> dict:
    return {
        "casos": set(),
        "operaciones": 0,
        "saldo_ini": 0.0,
        "saldo_cont": 0.0,
        **_empty_productos(),
        "fases": {},
    }


def _empty_productos() -> dict:
    return {producto: {"saldo_ini": 0.0, "saldo_cont": 0.0, "meta_monto": 0.0} for producto in PRODUCTOS}


def _add(acc: dict, row: dict, metas: dict) -> None:
    saldo_ini = float(row.get("Saldo_Ini") or 0)
    saldo_cont = float(row.get("Saldo_Cont") or 0)
    acc["operaciones"] += int(row.get("Operaciones") or 0)
    acc["saldo_ini"] += saldo_ini
    acc["saldo_cont"] += saldo_cont

    # Solo las fases con meta entran al cumplimiento del producto.
    producto = row.get("Producto")
    meta_fase = metas.get(producto, {}).get("fases", {}).get(row.get("Fase"))
    if meta_fase is None:
        return
    fase = acc["fases"].setdefault(row.get("Fase"), _empty_productos())
    for target in (acc[producto], fase[producto]):
        target["saldo_ini"] += saldo_ini
        target["saldo_cont"] += saldo_cont
        target["meta_monto"] += saldo_ini * meta_fase


def _producto_values(out: dict, producto: str, data: dict) -> float | None:
    key = producto.lower()
    cumplimiento = _cap(_safe_div(data["saldo_cont"], data["meta_monto"]), CUMPLIMIENTO_MAX) if data["meta_monto"] else None
    out[f"{key}_saldo_ini"] = data["saldo_ini"]
    out[f"{key}_saldo_cont"] = data["saldo_cont"]
    out[f"{key}_meta_monto"] = data["meta_monto"]
    out[f"{key}_cumplimiento"] = cumplimiento
    return cumplimiento


def _fases_detalle(acc: dict, metas: dict) -> list[dict]:
    """Detalle por fase del ejecutivo: solo fases con meta; sin cumplimiento final porque la ponderacion es por producto."""
    fases = sorted({fase for producto in PRODUCTOS for fase in metas.get(producto, {}).get("fases", {})})
    detalle = []
    for fase in fases:
        data = acc["fases"].get(fase, _empty_productos())
        item = {"fase": fase}
        for producto in PRODUCTOS:
            _producto_values(item, producto, data[producto])
            item[f"{producto.lower()}_meta_pct"] = metas.get(producto, {}).get("fases", {}).get(fase)
        detalle.append(item)
    return detalle


def _result(nombre: str, casos: int, acc: dict, metas: dict) -> dict:
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

    # Si el ejecutivo no tiene saldo con meta en un producto, su ponderacion se reparte en el otro.
    out["cumplimiento"] = _safe_div(ponderado, peso_total) if peso_total else None
    out["fases"] = _fases_detalle(acc, metas)
    return out


def get_general(filters: dict) -> dict:
    fecha_carga = _parse_fecha_carga(filters.get("fecha_carga"))
    periodo = _periodo_from_fecha(fecha_carga)
    ejecutivo = _clean_text(filters.get("ejecutivo"))

    filtros_medibles = _load_filtros_medibles(periodo)
    cte_sql, params = _base_cte(periodo, fecha_carga, filtros_medibles)
    filter_sql = ""
    if ejecutivo:
        filter_sql = "WHERE UPPER(Ejecutivo) = UPPER(LTRIM(RTRIM(?)))"
        params.append(ejecutivo)

    sql = (
        cte_sql
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
    """
    )

    metas = _load_metas(periodo)
    por_ejecutivo: dict[str, dict] = {}
    total = _empty_acc()
    for row in run_query(sql, tuple(params)):
        nombre = row.get("Ejecutivo") or DEFAULT_EXECUTIVE
        acc = por_ejecutivo.setdefault(nombre, _empty_acc())
        acc["casos"].add(row.get("RUT"))
        total["casos"].add(row.get("RUT"))
        _add(acc, row, metas)
        _add(total, row, metas)

    rows = [_result(nombre, len(acc["casos"]), acc, metas) for nombre, acc in sorted(por_ejecutivo.items())]
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
        "filtros_medibles": filtros_medibles,
        "rows": rows,
        "total": _result("Total general", len(total["casos"]), total, metas),
    }
