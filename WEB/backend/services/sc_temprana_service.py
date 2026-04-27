import os
import re
from dataclasses import dataclass

from database import run_query


@dataclass
class TempColumnMap:
    table_name: str
    fecha_col: str
    tramo_col: str
    ejecutivo_col: str
    zona_col: str | None
    deuda_col: str
    contenido_col: str
    normalizado_col: str
    meta_cont_col: str
    meta_norm_col: str
    contacto_titular_col: str | None


def _is_safe_table_name(name: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_\.\[\]]+", name))


def _table_name() -> str:
    name = os.getenv("PRODUCTIVIDAD_TEMP_TABLE", "dbo.tmp_bench_temp_STC_asignado")
    if not _is_safe_table_name(name):
        raise RuntimeError("PRODUCTIVIDAD_TEMP_TABLE contiene caracteres no permitidos")
    return name


def _runtime_columns(table_name: str) -> set[str]:
    schema, table = table_name.split(".", 1)
    schema = schema.replace("[", "").replace("]", "")
    table = table.replace("[", "").replace("]", "")
    sql = """
    SELECT c.name
    FROM sys.columns c
    INNER JOIN sys.tables t ON c.object_id = t.object_id
    INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
    WHERE s.name = ? AND t.name = ?
    """
    rows = run_query(sql, (schema, table))
    return {r["name"] for r in rows}


def _pick_first(available: set[str], candidates: list[str], label: str) -> str:
    for col in candidates:
        if col in available:
            return col
    raise RuntimeError(f"No se encontro columna para {label}. Probadas: {candidates}")


def resolve_columns() -> TempColumnMap:
    table_name = _table_name()
    available = _runtime_columns(table_name)
    return TempColumnMap(
        table_name=table_name,
        fecha_col=_pick_first(available, ["fld_FECHA", "fld_PERIODO", "fecha_carga"], "fecha"),
        tramo_col=_pick_first(available, ["fld_TRAMO_MORA"], "tramo"),
        ejecutivo_col=_pick_first(available, ["usuario_gestion_asignado", "fld_COBRADOR"], "ejecutivo"),
        zona_col=next((c for c in ["fld_ZONA", "fld_REGION"] if c in available), None),
        deuda_col=_pick_first(available, ["fld_DEUDA_INI"], "deuda"),
        contenido_col=_pick_first(available, ["fld_CONTENIDO"], "contenido"),
        normalizado_col=_pick_first(available, ["fld_NORMALIZADO"], "normalizado"),
        meta_cont_col=_pick_first(available, ["meta_contencion_pct"], "meta contencion"),
        meta_norm_col=_pick_first(available, ["meta_normalizacion_pct"], "meta normalizacion"),
        contacto_titular_col=next((c for c in ["contacto_titular_flag"] if c in available), None),
    )


def _clean(value) -> str:
    if value is None:
        return ""
    return str(value).strip().upper()


def _build_filters(filters: dict, cols: TempColumnMap) -> tuple[str, list]:
    clauses = []
    params: list = []

    if filters.get("periodo"):
        clauses.append(f"UPPER(LTRIM(RTRIM(CONVERT(varchar(50), {cols.fecha_col})))) = ?")
        params.append(_clean(filters["periodo"]))

    if filters.get("zona") and cols.zona_col:
        clauses.append(f"UPPER(LTRIM(RTRIM(CONVERT(varchar(200), {cols.zona_col})))) = ?")
        params.append(_clean(filters["zona"]))

    if filters.get("ejecutivo"):
        clauses.append(f"UPPER(LTRIM(RTRIM(CONVERT(varchar(200), {cols.ejecutivo_col})))) = ?")
        params.append(_clean(filters["ejecutivo"]))

    if filters.get("tramo"):
        clauses.append(f"UPPER(LTRIM(RTRIM(CONVERT(varchar(50), {cols.tramo_col})))) = ?")
        params.append(_clean(filters["tramo"]))

    where_sql = ""
    if clauses:
        where_sql = "WHERE " + " AND ".join(clauses)
    return where_sql, params


def _safe_div(num: float, den: float) -> float:
    if den is None or den == 0:
        return 0.0
    return (num / den) * 100.0


def _cap(value: float) -> float:
    return max(0.0, min(130.0, value))


def _cumpl_variable(pct_real: float, meta: float) -> float:
    if meta is None or meta <= 0:
        return 0.0
    return _cap(_safe_div(pct_real, meta))


def _cumpl_final(tramo: str, pct_cont: float, meta_cont: float, pct_norm: float, meta_norm: float) -> float:
    cont = _cumpl_variable(pct_cont, meta_cont)
    norm = _cumpl_variable(pct_norm, meta_norm)
    if _clean(tramo) == "C3":
        return _cap((cont * 0.40) + (norm * 0.60))
    return cont


def get_rows(filters: dict) -> list[dict]:
    cols = resolve_columns()
    where_sql, params = _build_filters(filters, cols)
    zona_expr = f"UPPER(LTRIM(RTRIM(CONVERT(varchar(200), {cols.zona_col}))))" if cols.zona_col else "NULL"
    titular_expr = cols.contacto_titular_col if cols.contacto_titular_col else "0"

    sql = f"""
    SELECT
      UPPER(LTRIM(RTRIM(CONVERT(varchar(50), {cols.fecha_col})))) AS periodo,
      UPPER(LTRIM(RTRIM(CONVERT(varchar(50), {cols.tramo_col})))) AS tramo,
      UPPER(LTRIM(RTRIM(CONVERT(varchar(200), {cols.ejecutivo_col})))) AS ejecutivo,
      {zona_expr} AS zona,
      SUM(CAST({cols.deuda_col} AS FLOAT)) AS deuda_asignada,
      SUM(CAST({cols.contenido_col} AS FLOAT)) AS saldo_contenido,
      SUM(CAST({cols.normalizado_col} AS FLOAT)) AS saldo_normalizado,
      AVG(CAST({cols.meta_cont_col} AS FLOAT)) AS meta_contencion_pct,
      AVG(CAST({cols.meta_norm_col} AS FLOAT)) AS meta_normalizacion_pct,
      SUM(CAST({titular_expr} AS FLOAT)) AS contactos_titular,
      COUNT_BIG(1) AS casos_asignados
    FROM {cols.table_name}
    {where_sql}
    GROUP BY
      UPPER(LTRIM(RTRIM(CONVERT(varchar(50), {cols.fecha_col})))),
      UPPER(LTRIM(RTRIM(CONVERT(varchar(50), {cols.tramo_col})))),
      UPPER(LTRIM(RTRIM(CONVERT(varchar(200), {cols.ejecutivo_col})))),
      {zona_expr}
    ORDER BY ejecutivo, tramo
    """
    raw = run_query(sql, tuple(params))
    rows: list[dict] = []
    for r in raw:
        deuda = float(r["deuda_asignada"] or 0)
        contenido = float(r["saldo_contenido"] or 0)
        normalizado = float(r["saldo_normalizado"] or 0)
        meta_c = float(r["meta_contencion_pct"] or 0)
        meta_n = float(r["meta_normalizacion_pct"] or 0)
        pct_cont = _safe_div(contenido, deuda)
        pct_norm = _safe_div(normalizado, deuda)
        contacto_tit = _safe_div(float(r["contactos_titular"] or 0), float(r["casos_asignados"] or 0))
        rows.append(
            {
                "periodo": r["periodo"],
                "tramo": r["tramo"],
                "ejecutivo": r["ejecutivo"],
                "zona": r["zona"],
                "deuda_asignada": deuda,
                "saldo_contenido": contenido,
                "porcentaje_contenido": pct_cont,
                "saldo_normalizado": normalizado,
                "porcentaje_normalizado": pct_norm,
                "meta_contencion_pct": meta_c,
                "meta_normalizacion_pct": meta_n,
                "cumplimiento_final": _cumpl_final(r["tramo"], pct_cont, meta_c, pct_norm, meta_n),
                "contacto_titular_pct": contacto_tit,
                "casos_asignados": int(r["casos_asignados"] or 0),
            }
        )
    return rows


def get_general_view(filters: dict) -> list[dict]:
    rows = get_rows(filters)
    out: dict[str, dict] = {}
    for r in rows:
        key = r["ejecutivo"] or "SIN_EJECUTIVO"
        acc = out.setdefault(
            key,
            {
                "ejecutivo": key,
                "zona": r["zona"],
                "deuda_total": 0.0,
                "casos_asignados": 0,
                "ponderado": 0.0,
                "contacto_pond": 0.0,
                "ciclos": {},
            },
        )
        deuda = r["deuda_asignada"]
        acc["deuda_total"] += deuda
        acc["casos_asignados"] += r["casos_asignados"]
        acc["ponderado"] += r["cumplimiento_final"] * deuda
        acc["contacto_pond"] += r["contacto_titular_pct"] * deuda
        acc["ciclos"][r["tramo"]] = r["cumplimiento_final"]

    resp = []
    for v in out.values():
        deuda = v["deuda_total"]
        resp.append(
            {
                "ejecutivo": v["ejecutivo"],
                "zona": v["zona"],
                "deuda_total": deuda,
                "casos_asignados": v["casos_asignados"],
                "cumplimiento_final": (v["ponderado"] / deuda) if deuda else 0.0,
                "contacto_titular_pct": (v["contacto_pond"] / deuda) if deuda else 0.0,
                "ciclos": v["ciclos"],
            }
        )
    resp.sort(key=lambda x: x["cumplimiento_final"], reverse=True)
    return resp


def get_cycle_view(filters: dict) -> list[dict]:
    rows = get_rows(filters)
    ciclo = _clean(filters.get("ciclo")) if filters.get("ciclo") else ""
    if ciclo:
        rows = [r for r in rows if _clean(r["tramo"]) == ciclo]
    rows.sort(key=lambda x: (x["ejecutivo"], x["tramo"]))
    return rows


def get_filter_values() -> dict:
    cols = resolve_columns()
    zona_expr = f"UPPER(LTRIM(RTRIM(CONVERT(varchar(200), {cols.zona_col}))))" if cols.zona_col else "NULL"
    return {
        "periodos": [
            r["valor"]
            for r in run_query(
                f"SELECT DISTINCT UPPER(LTRIM(RTRIM(CONVERT(varchar(50), {cols.fecha_col})))) AS valor FROM {cols.table_name} ORDER BY valor DESC"
            )
            if r["valor"]
        ],
        "tramos": [
            r["valor"]
            for r in run_query(
                f"SELECT DISTINCT UPPER(LTRIM(RTRIM(CONVERT(varchar(50), {cols.tramo_col})))) AS valor FROM {cols.table_name} ORDER BY valor"
            )
            if r["valor"]
        ],
        "ejecutivos": [
            r["valor"]
            for r in run_query(
                f"SELECT DISTINCT UPPER(LTRIM(RTRIM(CONVERT(varchar(200), {cols.ejecutivo_col})))) AS valor FROM {cols.table_name} ORDER BY valor"
            )
            if r["valor"]
        ],
        "zonas": [
            r["valor"]
            for r in run_query(
                f"SELECT DISTINCT {zona_expr} AS valor FROM {cols.table_name} ORDER BY valor"
            )
            if r["valor"]
        ]
        if cols.zona_col
        else [],
    }
