from __future__ import annotations

from collections import defaultdict
import re

from database import run_query


TABLE = "dbo.tmp_BENCH_CONTROL_DIARIO"
PHOENIX_NAME = "PHOENIX"


def _clean_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_period(value: object) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    if re.fullmatch(r"\d{4}-\d{2}", text):
        return text
    if re.fullmatch(r"\d{6}", text):
        return f"{text[:4]}-{text[4:6]}"
    return text[:7] if len(text) >= 7 else text


def _filter_clauses(filters: dict, include_segment: bool = True) -> tuple[list[str], list]:
    clauses: list[str] = ["UPPER(LTRIM(RTRIM(empresa))) = 'PHOENIX'"]
    params: list = []

    negocio = _clean_text(filters.get("negocio"))
    if negocio:
        clauses.append("UPPER(LTRIM(RTRIM(negocio))) = UPPER(LTRIM(RTRIM(?)))")
        params.append(negocio)

    segmento = _clean_text(filters.get("segmento"))
    if include_segment and segmento:
        clauses.append("UPPER(LTRIM(RTRIM(segmento))) = UPPER(LTRIM(RTRIM(?)))")
        params.append(segmento)

    return clauses, params


def _query_periodos(filters: dict) -> list[str]:
    clauses, params = _filter_clauses(filters)
    where_sql = "WHERE fecha IS NOT NULL"
    if clauses:
        where_sql += " AND " + " AND ".join(clauses)

    rows = run_query(
        f"""
        SELECT DISTINCT CONVERT(char(7), fecha, 126) AS periodo
        FROM {TABLE}
        {where_sql}
        ORDER BY periodo DESC
        """,
        tuple(params),
    )
    return [str(row["periodo"]) for row in rows if row.get("periodo")]


def _get_last_db_update() -> str:
    rows = run_query(f"SELECT MAX(fecha_actualizacion) AS fecha_actualizacion FROM {TABLE}")
    return str(rows[0].get("fecha_actualizacion") or "") if rows else ""


def get_filter_values(filters: dict | None = None) -> dict:
    filters = filters or {}
    periodos = _query_periodos(filters)

    negocios = [
        str(row["negocio"])
        for row in run_query(
            f"""
            SELECT DISTINCT LTRIM(RTRIM(negocio)) AS negocio
            FROM {TABLE}
            WHERE negocio IS NOT NULL AND LTRIM(RTRIM(negocio)) <> ''
              AND UPPER(LTRIM(RTRIM(empresa))) = 'PHOENIX'
            ORDER BY negocio
            """
        )
        if row.get("negocio")
    ]

    clauses, params = _filter_clauses(filters, include_segment=False)
    where_sql = "WHERE segmento IS NOT NULL AND LTRIM(RTRIM(segmento)) <> ''"
    if clauses:
        where_sql += " AND " + " AND ".join(clauses)

    segmentos = [
        str(row["segmento"])
        for row in run_query(
            f"""
            SELECT DISTINCT LTRIM(RTRIM(segmento)) AS segmento
            FROM {TABLE}
            {where_sql}
            ORDER BY segmento
            """,
            tuple(params),
        )
        if row.get("segmento")
    ]

    return {
        "periodos": periodos,
        "negocios": negocios,
        "segmentos": segmentos,
        "fecha_actualizacion": _get_last_db_update(),
    }


def _resolve_periodos(filters: dict) -> list[str]:
    requested_raw = filters.get("periodos") or []
    if isinstance(requested_raw, str):
        requested_raw = [requested_raw]

    available = _query_periodos(filters)
    requested: list[str] = []
    for item in requested_raw:
        normalized = _normalize_period(item)
        if normalized and normalized in available and normalized not in requested:
            requested.append(normalized)

    if requested:
        return requested

    return available[:2]


def get_comparison_view(filters: dict) -> dict:
    selected_periods = _resolve_periodos(filters)
    if not selected_periods:
        return {"series": []}

    clauses = [
        "fecha IS NOT NULL",
        "dia_habil IS NOT NULL",
        "UPPER(LTRIM(RTRIM(empresa))) = 'PHOENIX'",
    ]
    params: list = list(selected_periods)

    clauses.append(f"CONVERT(char(7), fecha, 126) IN ({', '.join('?' for _ in selected_periods)})")

    negocio = _clean_text(filters.get("negocio"))
    if negocio:
        clauses.append("UPPER(LTRIM(RTRIM(negocio))) = UPPER(LTRIM(RTRIM(?)))")
        params.append(negocio)

    segmento = _clean_text(filters.get("segmento"))
    if segmento:
        clauses.append("UPPER(LTRIM(RTRIM(segmento))) = UPPER(LTRIM(RTRIM(?)))")
        params.append(segmento)

    rows = run_query(
        f"""
        SELECT
            CONVERT(char(7), fecha, 126) AS periodo,
            dia_habil,
            MAX(CONVERT(char(10), fecha, 126)) AS fecha,
            AVG(CAST(cumplimiento AS float)) AS cumplimiento
        FROM {TABLE}
        WHERE {" AND ".join(clauses)}
        GROUP BY CONVERT(char(7), fecha, 126), dia_habil
        ORDER BY periodo DESC, dia_habil ASC
        """,
        tuple(params),
    )

    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        periodo = str(row.get("periodo") or "").strip()
        if not periodo:
            continue
        grouped[periodo].append(
            {
                "dia_habil": int(row.get("dia_habil") or 0),
                "fecha": str(row.get("fecha") or ""),
                "cumplimiento": round(float(row.get("cumplimiento") or 0), 2),
            }
        )

    series = []
    for periodo in selected_periods:
        series.append(
            {
                "periodo": periodo,
                "puntos": grouped.get(periodo, []),
            }
        )

    return {"series": series}
