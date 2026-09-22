import os
import re
from dataclasses import dataclass

from database import run_query


@dataclass
class ColumnMap:
    table_name: str
    date_col: str
    fecha_col: str | None
    tramo_col: str
    apertura_col: str
    ejecutivo_col: str
    zona_col: str | None
    deuda_col: str
    contenido_col: str
    normalizado_col: str
    meta_cont_col: str
    meta_norm_col: str
    negocio_col: str | None = None
    segmento_col: str | None = None


def _is_safe_table_name(name: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_\.\[\]]+", name))


def _table_name() -> str:
    name = os.getenv("PRODUCTIVIDAD_TABLE", "dbo.tmp_bench_STC")
    if not _is_safe_table_name(name):
        raise RuntimeError("PRODUCTIVIDAD_TABLE contiene caracteres no permitidos")
    return name


def _max_source_files() -> int:
    raw = os.getenv("PRODUCTIVIDAD_MAX_SOURCE_FILES", "24")
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError("PRODUCTIVIDAD_MAX_SOURCE_FILES debe ser numerico") from exc
    return max(1, value)


def _latest_source_files_clause(cols: ColumnMap) -> str:
    return f"""
    {cols.table_name}.source_file IN (
        SELECT source_file
        FROM (
            SELECT TOP ({_max_source_files()}) source_file
            FROM {cols.table_name}
            WHERE source_file IS NOT NULL
            GROUP BY source_file
            ORDER BY MAX(ts_carga) DESC, MAX(id_bench_stc) DESC
        ) latest_sources
    )
    """


def _runtime_columns(table_name: str) -> set[str]:
    if "." not in table_name:
        raise RuntimeError(
            "La tabla debe incluir esquema, por ejemplo dbo.tmp_bench_STC"
        )

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
    raise RuntimeError(f"No se encontró columna para {label}. Probadas: {candidates}")


def _pick_optional(available: set[str], candidates: list[str]) -> str | None:
    for col in candidates:
        if col in available:
            return col
    return None


def resolve_columns() -> ColumnMap:
    table_name = _table_name()
    available = _runtime_columns(table_name)

    columns = ColumnMap(
        table_name=table_name,
        date_col=_pick_first(available, ["fecha_carga", "ts_carga"], "fecha"),
        fecha_col=_pick_optional(available, ["fld_FECHA"]),
        tramo_col=_pick_first(available, ["fld_TRAMO_MORA"], "tramo"),
        apertura_col=_pick_first(available, ["fld_APERTURA"], "apertura"),
        ejecutivo_col=_pick_first(
            available,
            ["fld_EJECUTIVO", "fld_COBRADOR", "fld_GESTOR", "fld_ASESOR"],
            "ejecutivo",
        ),
        zona_col=next(
            (c for c in ["fld_ZONA", "fld_REGION", "fld_SUCURSAL"] if c in available),
            None,
        ),
        deuda_col=_pick_first(available, ["fld_DEUDA_INI"], "deuda asignada"),
        contenido_col=_pick_first(available, ["fld_CONTENIDO"], "saldo contenido"),
        normalizado_col=_pick_first(
            available, ["fld_NORMALIZADO"], "saldo normalizado"
        ),
        meta_cont_col=_pick_first(
            available, ["meta_contencion_pct"], "meta contención"
        ),
        meta_norm_col=_pick_first(
            available, ["meta_normalizacion_pct"], "meta normalización"
        ),
    )
    columns.negocio_col = _pick_optional(
        available, ["fld_NEGOCIO", "fld_NEGOCIO_NOMBRE", "fld_BUSINESS", "negocio"]
    )
    columns.segmento_col = _pick_optional(available, ["fld_SEGMENTO", "segmento"])
    return columns


def _clean_text(value) -> str:
    if value is None:
        return ""
    return str(value).strip().upper()


def _period_expr(cols: ColumnMap) -> str:
    if cols.fecha_col:
        # Intenta convertir YYYYMMDD a fecha y luego a YYYY-MM-DD
        return f"FORMAT(CONVERT(date, {cols.fecha_col}, 112), 'yyyy-MM-dd')"
    # Convierte fecha_carga (DATE) a YYYY-MM-DD
    return f"CONVERT(char(10), {cols.date_col}, 126)"


def _exclude_f_tramos_clause(cols: ColumnMap) -> str:
    return f"UPPER(LTRIM(RTRIM({cols.tramo_col}))) NOT IN ('F1','F2','F3','F4')"


def _build_filters(filters: dict, cols: ColumnMap) -> tuple[str, list]:
    clauses = []
    params: list = []
    period_expr = _period_expr(cols)

    # Excluir completamente F1-F4 en todos los calculos
    clauses.append(_exclude_f_tramos_clause(cols))
    clauses.append(_latest_source_files_clause(cols))

    if filters.get("periodo"):
        clauses.append(f"{period_expr} = ?")
        params.append(_clean_text(filters["periodo"]))
    else:
        clauses.append(
            f"{period_expr} = (SELECT MAX({period_expr}) FROM {cols.table_name} WHERE {period_expr} IS NOT NULL)"
        )

    if filters.get("tramo"):
        clauses.append(f"UPPER(LTRIM(RTRIM({cols.tramo_col}))) = ?")
        params.append(_clean_text(filters["tramo"]))

    if filters.get("apertura"):
        clauses.append(f"UPPER(LTRIM(RTRIM({cols.apertura_col}))) = ?")
        params.append(_clean_text(filters["apertura"]))

    if filters.get("ejecutivo"):
        clauses.append(f"UPPER(LTRIM(RTRIM({cols.ejecutivo_col}))) = ?")
        params.append(_clean_text(filters["ejecutivo"]))

    if filters.get("zona") and cols.zona_col:
        clauses.append(f"UPPER(LTRIM(RTRIM({cols.zona_col}))) = ?")
        params.append(_clean_text(filters["zona"]))

    if filters.get("negocio") and cols.negocio_col:
        clauses.append(f"UPPER(LTRIM(RTRIM({cols.negocio_col}))) = ?")
        params.append(_clean_text(filters["negocio"]))

    if filters.get("segmento") and cols.segmento_col:
        clauses.append(f"UPPER(LTRIM(RTRIM({cols.segmento_col}))) = ?")
        params.append(_clean_text(filters["segmento"]))

    where_sql = ""
    if clauses:
        where_sql = "WHERE " + " AND ".join(clauses)

    return where_sql, params


def _safe_div(num: float, den: float) -> float:
    if den is None or den == 0:
        return 0.0
    return (num / den) * 100.0


def _cap_pct(value: float) -> float:
    return max(0.0, min(130.0, value))


def _cumplimiento_variable(pct_real: float, meta: float) -> float:
    if meta is None or meta <= 0:
        return 0.0
    return _cap_pct(_safe_div(pct_real, meta))


def _cumplimiento_final(
    pct_cont: float,
    meta_cont: float,
    pct_norm: float,
    meta_norm: float,
    tramo: str,
    apertura: str,
) -> float:
    cumpl_cont = _cumplimiento_variable(pct_cont, meta_cont)
    cumpl_norm = _cumplimiento_variable(pct_norm, meta_norm)

    bucket = _general_bucket(tramo, apertura)
    is_c3 = _clean_text(tramo) == "C3" or bucket == "C3"

    if is_c3:
        return _cap_pct((cumpl_cont * 0.40) + (cumpl_norm * 0.60))
    return cumpl_cont


def _general_bucket(tramo: str, apertura: str) -> str | None:
    tramo = _clean_text(tramo)
    apertura = _clean_text(apertura)

    if tramo in {"C6", "C7", "C8"} and apertura == "SUSCEPTIBLE CASTIGO":
        return "PRE CASTIGO"
    if tramo == "C6" and apertura != "SUSCEPTIBLE CASTIGO":
        return "C6"
    if tramo == "C3":
        return "C3"
    if apertura == "SUSCEPTIBLE CV":
        return "SUSCEPTIBLE CV"
    if tramo == "C5":
        return "C5"
    return None


def get_cycle_rows(filters: dict) -> list[dict]:
    cols = resolve_columns()
    where_sql, params = _build_filters(filters, cols)
    period_expr = _period_expr(cols)

    zona_expr = f"UPPER(LTRIM(RTRIM({cols.zona_col})))" if cols.zona_col else "NULL"

    sql = f"""
    SELECT
        {period_expr} AS periodo,
        UPPER(LTRIM(RTRIM({cols.tramo_col}))) AS tramo,
        UPPER(LTRIM(RTRIM({cols.apertura_col}))) AS apertura,
        UPPER(LTRIM(RTRIM({cols.ejecutivo_col}))) AS ejecutivo,
        {zona_expr} AS zona,
        SUM(CAST({cols.deuda_col} AS FLOAT)) AS deuda_asignada,
        SUM(CAST({cols.contenido_col} AS FLOAT)) AS saldo_contenido,
        SUM(CAST({cols.normalizado_col} AS FLOAT)) AS saldo_normalizado,
        COUNT_BIG(1) AS casos_asignados,
        AVG(CAST({cols.meta_cont_col} AS FLOAT)) AS meta_contencion_pct,
        AVG(CAST({cols.meta_norm_col} AS FLOAT)) AS meta_normalizacion_pct
    FROM {cols.table_name}
    {where_sql}
    GROUP BY
        {period_expr},
        UPPER(LTRIM(RTRIM({cols.tramo_col}))),
        UPPER(LTRIM(RTRIM({cols.apertura_col}))),
        UPPER(LTRIM(RTRIM({cols.ejecutivo_col}))),
        {zona_expr}
    ORDER BY ejecutivo, tramo
    """

    raw_rows = run_query(sql, tuple(params))
    rows = []

    for row in raw_rows:
        deuda = float(row["deuda_asignada"] or 0)
        contenido = float(row["saldo_contenido"] or 0)
        normalizado = float(row["saldo_normalizado"] or 0)
        meta_cont = float(row["meta_contencion_pct"] or 0)
        meta_norm = float(row["meta_normalizacion_pct"] or 0)

        pct_cont = _safe_div(contenido, deuda)
        pct_norm = _safe_div(normalizado, deuda)
        cumpl_final = _cumplimiento_final(
            pct_cont,
            meta_cont,
            pct_norm,
            meta_norm,
            row["tramo"],
            row["apertura"],
        )

        rows.append(
            {
                "periodo": row["periodo"],
                "zona": row["zona"],
                "tramo": row["tramo"],
                "apertura": row["apertura"],
                "ejecutivo": row["ejecutivo"],
                "deuda_asignada": deuda,
                "saldo_contenido": contenido,
                "porcentaje_contenido": pct_cont,
                "saldo_normalizado": normalizado,
                "porcentaje_normalizado": pct_norm,
                "meta_contencion_pct": meta_cont,
                "meta_normalizacion_pct": meta_norm,
                "cumplimiento_final": cumpl_final,
                "casos_asignados": int(row["casos_asignados"] or 0),
            }
        )

    return rows


def get_cycle_view(filters: dict) -> list[dict]:
    rows = get_cycle_rows(filters)
    ciclo = filters.get("ciclo")
    ciclo = _clean_text(ciclo) if ciclo else ""

    grouped: dict[tuple, dict] = {}
    for row in rows:
        bucket = _general_bucket(row["tramo"], row["apertura"])
        if not bucket:
            continue
        if ciclo and bucket != ciclo:
            continue

        key = (row["periodo"], row["zona"], bucket, row["ejecutivo"])
        current = grouped.setdefault(
            key,
            {
                "periodo": row["periodo"],
                "zona": row["zona"],
                "tramo": bucket,
                "apertura": "TODAS",
                "ejecutivo": row["ejecutivo"],
                "deuda_asignada": 0.0,
                "saldo_contenido": 0.0,
                "saldo_normalizado": 0.0,
                "casos_asignados": 0,
                "meta_cont_pond": 0.0,
                "meta_norm_pond": 0.0,
            },
        )

        deuda = row["deuda_asignada"]
        current["deuda_asignada"] += deuda
        current["saldo_contenido"] += row["saldo_contenido"]
        current["saldo_normalizado"] += row["saldo_normalizado"]
        current["casos_asignados"] += row["casos_asignados"]
        current["meta_cont_pond"] += row["meta_contencion_pct"] * deuda
        current["meta_norm_pond"] += row["meta_normalizacion_pct"] * deuda

    response = []
    for item in grouped.values():
        deuda = item["deuda_asignada"]
        meta_cont = (item["meta_cont_pond"] / deuda) if deuda else 0.0
        meta_norm = (item["meta_norm_pond"] / deuda) if deuda else 0.0
        pct_cont = _safe_div(item["saldo_contenido"], deuda)
        pct_norm = _safe_div(item["saldo_normalizado"], deuda)
        response.append(
            {
                "periodo": item["periodo"],
                "zona": item["zona"],
                "tramo": item["tramo"],
                "apertura": item["apertura"],
                "ejecutivo": item["ejecutivo"],
                "deuda_asignada": deuda,
                "saldo_contenido": item["saldo_contenido"],
                "porcentaje_contenido": pct_cont,
                "saldo_normalizado": item["saldo_normalizado"],
                "porcentaje_normalizado": pct_norm,
                "meta_contencion_pct": meta_cont,
                "meta_normalizacion_pct": meta_norm,
                "cumplimiento_final": _cumplimiento_final(
                    pct_cont,
                    meta_cont,
                    pct_norm,
                    meta_norm,
                    item["tramo"],
                    item["apertura"],
                ),
                "casos_asignados": item["casos_asignados"],
            }
        )

    response.sort(key=lambda x: (x["ejecutivo"], x["tramo"]))
    return response


def get_general_view(filters: dict) -> list[dict]:
    rows = get_cycle_rows(filters)
    by_exec: dict[str, dict] = {}

    for row in rows:
        key = row["ejecutivo"] or "SIN_EJECUTIVO"
        current = by_exec.setdefault(
            key,
            {
                "ejecutivo": key,
                "zona": row["zona"],
                "deuda_total": 0.0,
                "casos_asignados": 0,
                "ponderado": 0.0,
                "bucket_data": {},
            },
        )

        deuda = row["deuda_asignada"]
        current["deuda_total"] += deuda
        current["casos_asignados"] += row["casos_asignados"]
        current["ponderado"] += row["cumplimiento_final"] * deuda

        bucket = _general_bucket(row["tramo"], row["apertura"])
        if bucket:
            bucket_current = current["bucket_data"].setdefault(
                bucket,
                {
                    "deuda": 0.0,
                    "contenido": 0.0,
                    "normalizado": 0.0,
                    "meta_cont_pond": 0.0,
                    "meta_norm_pond": 0.0,
                },
            )
            bucket_current["deuda"] += deuda
            bucket_current["contenido"] += row["saldo_contenido"]
            bucket_current["normalizado"] += row["saldo_normalizado"]
            bucket_current["meta_cont_pond"] += row["meta_contencion_pct"] * deuda
            bucket_current["meta_norm_pond"] += row["meta_normalizacion_pct"] * deuda

    response = []
    for item in by_exec.values():
        deuda_total = item["deuda_total"]
        cumplimiento_final = (item["ponderado"] / deuda_total) if deuda_total else 0.0
        ciclos = {}
        for bucket, bucket_values in item["bucket_data"].items():
            bucket_deuda = bucket_values["deuda"]
            pct_cont = _safe_div(bucket_values["contenido"], bucket_deuda)
            pct_norm = _safe_div(bucket_values["normalizado"], bucket_deuda)
            meta_cont = (
                (bucket_values["meta_cont_pond"] / bucket_deuda) if bucket_deuda else 0.0
            )
            meta_norm = (
                (bucket_values["meta_norm_pond"] / bucket_deuda) if bucket_deuda else 0.0
            )
            ciclos[bucket] = _cumplimiento_final(
                pct_cont,
                meta_cont,
                pct_norm,
                meta_norm,
                bucket,
                "TODAS",
            )

        response.append(
            {
                "ejecutivo": item["ejecutivo"],
                "zona": item["zona"],
                "deuda_total": deuda_total,
                "casos_asignados": item["casos_asignados"],
                "cumplimiento_final": cumplimiento_final,
                "ciclos": ciclos,
            }
        )

    response.sort(key=lambda x: x["cumplimiento_final"], reverse=True)
    return response


def get_filter_values(filters: dict | None = None) -> dict:
    filters = filters or {}
    cols = resolve_columns()
    period_expr = _period_expr(cols)
    base_where = f"WHERE {_exclude_f_tramos_clause(cols)} AND {_latest_source_files_clause(cols)}"

    data = {
        "periodos": run_query(
            f"SELECT DISTINCT {period_expr} AS valor FROM {cols.table_name} {base_where} AND {period_expr} IS NOT NULL ORDER BY valor DESC"
        ),
        "tramos": run_query(
            f"SELECT DISTINCT UPPER(LTRIM(RTRIM({cols.tramo_col}))) AS valor FROM {cols.table_name} {base_where} ORDER BY valor"
        ),
        "aperturas": run_query(
            f"SELECT DISTINCT UPPER(LTRIM(RTRIM({cols.apertura_col}))) AS valor FROM {cols.table_name} {base_where} ORDER BY valor"
        ),
        "ejecutivos": run_query(
            f"SELECT DISTINCT UPPER(LTRIM(RTRIM({cols.ejecutivo_col}))) AS valor FROM {cols.table_name} {base_where} ORDER BY valor"
        ),
        "zonas": [],
        "negocios": [],
        "segmentos": [],
    }

    if cols.zona_col:
        data["zonas"] = run_query(
            f"SELECT DISTINCT UPPER(LTRIM(RTRIM({cols.zona_col}))) AS valor FROM {cols.table_name} {base_where} ORDER BY valor"
        )

    if cols.negocio_col:
        data["negocios"] = run_query(
            f"""
            SELECT DISTINCT UPPER(LTRIM(RTRIM({cols.negocio_col}))) AS valor
            FROM {cols.table_name}
            {base_where}
              AND {cols.negocio_col} IS NOT NULL
              AND LTRIM(RTRIM({cols.negocio_col})) <> ''
            ORDER BY valor
            """
        )

    if cols.segmento_col:
        segmento_params = []
        negocio_clause = ""
        if filters.get("negocio") and cols.negocio_col:
            negocio_clause = f"AND UPPER(LTRIM(RTRIM({cols.negocio_col}))) = ?"
            segmento_params.append(_clean_text(filters["negocio"]))

        data["segmentos"] = run_query(
            f"""
            SELECT DISTINCT UPPER(LTRIM(RTRIM({cols.segmento_col}))) AS valor
            FROM {cols.table_name}
            {base_where}
              AND {cols.segmento_col} IS NOT NULL
              AND LTRIM(RTRIM({cols.segmento_col})) <> ''
              {negocio_clause}
            ORDER BY valor
            """,
            tuple(segmento_params),
        )

    return {
        "periodos": [r["valor"] for r in data["periodos"] if r["valor"]],
        "tramos": [r["valor"] for r in data["tramos"] if r["valor"]],
        "aperturas": [r["valor"] for r in data["aperturas"] if r["valor"]],
        "ejecutivos": [r["valor"] for r in data["ejecutivos"] if r["valor"]],
        "zonas": [r["valor"] for r in data["zonas"] if r["valor"]],
        "negocios": [r["valor"] for r in data["negocios"] if r["valor"]],
        "segmentos": [r["valor"] for r in data["segmentos"] if r["valor"]],
    }
