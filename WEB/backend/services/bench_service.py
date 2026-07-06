from collections import defaultdict
import re

from database import run_query


TABLE = "dbo.tmp_BENCH_CONTROL_DIARIO"
PHOENIX_NAME = "PHOENIX"


def _normalize_text(value: str | None) -> str:
    return str(value or "").strip().upper()


def _segment_sort_key(value: str) -> tuple[int, int, str]:
    text = str(value or "").strip()
    normalized = _normalize_text(text)
    match = re.search(r"BUCKET\s*(\d+)\s*-\s*(\d+)", normalized)
    if match:
        start = int(match.group(1))
        end = int(match.group(2))
        return (0, start * 1000 + end, normalized)
    return (1, 0, normalized)


def _safe_float(value: object) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _empty_kpi_response(filters_context: dict) -> dict:
    return {
        "filters_context": filters_context,
        "summary": {
            "selected_periodo": filters_context.get("periodo") or "",
            "selected_negocio": filters_context.get("negocio") or "",
            "selected_segmento": filters_context.get("segmento") or "",
            "latest_date": "",
            "companies_count": 0,
        },
        "phoenix_vs_competencia": {
            "value": 0.0,
            "phoenix": 0.0,
            "competitor": 0.0,
            "competitor_name": "",
        },
        "estado_phoenix": {
            "label": "Pendiente",
            "code": "pending",
            "color": "neutral",
        },
        "ranking": [],
        "serie_diaria": [],
        "source_info": {
            "fecha_actualizacion": "",
        },
    }


def get_filter_values(filters: dict | None = None, user: dict | None = None) -> dict:
    filters = filters or {}
    negocio = str(filters.get("negocio") or "").strip()
    periodo = str(filters.get("periodo") or "").strip()

    periodos = [
        str(row["v"])
        for row in run_query(
            f"""
            SELECT DISTINCT CONVERT(char(7), fecha, 126) AS v
            FROM {TABLE}
            WHERE fecha IS NOT NULL
              AND (? = '' OR UPPER(LTRIM(RTRIM(negocio))) = UPPER(LTRIM(RTRIM(?))))
            ORDER BY v DESC
            """,
            (negocio, negocio),
        )
    ]
    negocios = [
        str(row["v"])
        for row in run_query(
            f"""
            SELECT DISTINCT negocio AS v
            FROM {TABLE}
            WHERE negocio IS NOT NULL AND LTRIM(RTRIM(negocio)) <> ''
            ORDER BY v
            """,
        )
    ]
    segmentos = [
        str(row["v"])
        for row in run_query(
            f"""
            SELECT DISTINCT segmento AS v
            FROM {TABLE}
            WHERE segmento IS NOT NULL AND LTRIM(RTRIM(segmento)) <> ''
              AND (? = '' OR UPPER(LTRIM(RTRIM(negocio))) = UPPER(LTRIM(RTRIM(?))))
              AND (? = '' OR CONVERT(char(7), fecha, 126) = ?)
            ORDER BY v
            """,
            (negocio, negocio, periodo, periodo),
        )
    ]
    segmentos.sort(key=_segment_sort_key)
    return {
        "periodos": periodos,
        "negocios": negocios,
        "segmentos": segmentos,
    }


def _resolve_periodo(filters: dict) -> str:
    requested = str(filters.get("periodo") or "").strip()
    if requested:
        return requested
    rows = run_query(f"SELECT TOP 1 CONVERT(char(7), fecha, 126) AS periodo FROM {TABLE} WHERE fecha IS NOT NULL ORDER BY periodo DESC")
    return str(rows[0]["periodo"]) if rows else ""


def _build_where(filters: dict) -> tuple[str, list]:
    clauses = ["CONVERT(char(7), fecha, 126) = ?"]
    params: list = [_resolve_periodo(filters)]

    negocio = str(filters.get("negocio") or "").strip()
    if negocio:
        clauses.append("UPPER(LTRIM(RTRIM(negocio))) = UPPER(LTRIM(RTRIM(?)))")
        params.append(negocio)

    segmento = str(filters.get("segmento") or "").strip()
    if segmento:
        clauses.append("UPPER(LTRIM(RTRIM(segmento))) = UPPER(LTRIM(RTRIM(?)))")
        params.append(segmento)

    return " AND ".join(clauses), params


def _resolve_phoenix_status(phoenix_latest_row: dict | None) -> dict:
    if not phoenix_latest_row:
        return {"label": "Pendiente", "code": "pending", "color": "neutral"}

    label = str(phoenix_latest_row.get("estado_phoenix") or "").strip()
    code = str(phoenix_latest_row.get("estado_codigo") or "").strip()
    color = str(phoenix_latest_row.get("estado_color") or "").strip()
    if label:
        return {
            "label": label,
            "code": code or _normalize_text(label).replace(" ", "_").lower(),
            "color": color or "neutral",
        }
    return {"label": "Pendiente", "code": "pending", "color": "neutral"}


def get_kpi_view(filters: dict, user: dict | None = None) -> dict:
    periodo = _resolve_periodo(filters)
    filters_context = {
        "periodo": periodo,
        "negocio": str(filters.get("negocio") or "").strip(),
        "segmento": str(filters.get("segmento") or "").strip(),
    }
    if not periodo:
        return _empty_kpi_response(filters_context)

    where_sql, params = _build_where(filters)
    rows = run_query(
        f"""
        SELECT
            fecha,
            anio,
            mes,
            dia_habil,
            negocio,
            segmento,
            empresa,
            cumplimiento,
            fecha_actualizacion
        FROM {TABLE}
        WHERE {where_sql}
        ORDER BY fecha ASC, empresa ASC
        """,
        tuple(params),
    )
    if not rows:
        return _empty_kpi_response(filters_context)

    rows_with_value = [row for row in rows if row.get("fecha") and row.get("cumplimiento") is not None]
    latest_date = max((row["fecha"] for row in rows_with_value), default=max(row["fecha"] for row in rows if row.get("fecha")))
    latest_rows = [row for row in rows_with_value if row.get("fecha") == latest_date]

    ranking_source: dict[str, list[dict]] = defaultdict(list)
    for row in latest_rows:
        ranking_source[str(row.get("empresa") or "").strip()].append(row)

    ranking = []
    for empresa, company_rows in ranking_source.items():
        debug_ultimo_dia = sum(_safe_float(item.get("cumplimiento")) for item in company_rows) / len(company_rows)
        ranking.append(
            {
                "empresa": empresa,
                "debug_ultimo_dia": round(debug_ultimo_dia, 2),
                "is_phoenix": _normalize_text(empresa) == PHOENIX_NAME,
            }
        )
    ranking.sort(key=lambda item: (-item["debug_ultimo_dia"], item["empresa"]))
    for index, item in enumerate(ranking, start=1):
        item["ranking"] = index

    phoenix_item = next((item for item in ranking if item["is_phoenix"]), None)
    competitor_item = next((item for item in ranking if not item["is_phoenix"]), None)
    series_source: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        fecha = row.get("fecha")
        if not fecha:
            continue
        series_source[str(fecha)]
        empresa = str(row.get("empresa") or "").strip()
        if not empresa or row.get("cumplimiento") is None:
            continue
        series_source[str(fecha)][empresa].append(_safe_float(row.get("cumplimiento")))

    serie_diaria = []
    for fecha_key in sorted(series_source.keys()):
        empresas = {
            empresa: round(sum(values) / len(values), 2)
            for empresa, values in sorted(series_source[fecha_key].items())
        }
        serie_diaria.append({"fecha": fecha_key, "empresas": empresas})

    latest_row = max(rows, key=lambda row: row.get("fecha_actualizacion") or row.get("fecha"))
    return {
        "filters_context": filters_context,
        "summary": {
            "selected_periodo": periodo,
            "selected_negocio": filters_context["negocio"],
            "selected_segmento": filters_context["segmento"],
            "latest_date": str(latest_date),
            "companies_count": len(ranking),
        },
        "phoenix_vs_competencia": {
            "value": round((phoenix_item or {}).get("debug_ultimo_dia", 0) - (competitor_item or {}).get("debug_ultimo_dia", 0), 2),
            "phoenix": round((phoenix_item or {}).get("debug_ultimo_dia", 0), 2),
            "competitor": round((competitor_item or {}).get("debug_ultimo_dia", 0), 2),
            "competitor_name": (competitor_item or {}).get("empresa", ""),
        },
        "estado_phoenix": {"label": "Pendiente", "code": "pending", "color": "neutral"},
        "ranking": ranking,
        "serie_diaria": serie_diaria,
        "source_info": {
            "fecha_actualizacion": str(latest_row.get("fecha_actualizacion") or ""),
        },
    }
