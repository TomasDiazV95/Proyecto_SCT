from database import run_query


MIN_FACTURA_PERIOD = "2026-06"
GLOBAL_SCOPE = "global"
BIT_SCOPE = "bco_internacional"
SUPPORTED_SCOPES = {GLOBAL_SCOPE, BIT_SCOPE}


def _safe_float(value: object) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _zero_matrix() -> dict:
    return {
        "tramo_30_90": {
            "muy_bajo_lo_esperado": 0.0,
            "bajo_lo_esperado": 0.0,
            "esperado": 0.0,
            "sobre_lo_esperado": 0.0,
        },
        "tramo_90_mas": {
            "muy_bajo_lo_esperado": 0.0,
            "bajo_lo_esperado": 0.0,
            "esperado": 0.0,
            "sobre_lo_esperado": 0.0,
        },
        "castigo": {
            "muy_bajo_lo_esperado": 0.0,
            "bajo_lo_esperado": 0.0,
            "esperado": 0.0,
            "sobre_lo_esperado": 0.0,
        },
        "simulacion_total": {
            "muy_bajo_lo_esperado": 0.0,
            "bajo_lo_esperado": 0.0,
            "esperado": 0.0,
            "sobre_lo_esperado": 0.0,
        },
    }


def _percentages() -> dict:
    return {
        "tramo_30_90": {
            "muy_bajo_lo_esperado": 0.20,
            "bajo_lo_esperado": 0.25,
            "esperado": 0.30,
            "sobre_lo_esperado": 0.35,
        },
        "tramo_90_mas": {
            "muy_bajo_lo_esperado": 0.45,
            "bajo_lo_esperado": 0.50,
            "esperado": 0.60,
            "sobre_lo_esperado": 0.65,
        },
        "castigo": {
            "muy_bajo_lo_esperado": 0.25,
            "bajo_lo_esperado": 0.25,
            "esperado": 0.25,
            "sobre_lo_esperado": 0.25,
        },
    }


def _build_business_summary(
    business_key: str,
    business_label: str,
    summary: dict,
    matrix: dict,
    has_real_invoice: bool = False,
    factura_real_total: float | None = None,
    factura_real_periodo: str | None = None,
) -> dict:
    factura_real_value = None if factura_real_total is None else _safe_float(factura_real_total)
    simulado_total = _safe_float(summary.get("total_sobre"))
    diferencia_total = factura_real_value - simulado_total if factura_real_value is not None else None
    diferencia_pct = (diferencia_total / simulado_total) if factura_real_value is not None and simulado_total else None
    return {
        "key": business_key,
        "label": business_label,
        "simulado_total": simulado_total,
        "simulado_esperado": _safe_float(summary.get("total_esperado")),
        "factura_real_total": factura_real_value,
        "factura_real_periodo": factura_real_periodo,
        "has_real_invoice": has_real_invoice,
        "diferencia_total": diferencia_total,
        "diferencia_pct": diferencia_pct,
        "components": {
            "tramo_30_90": _safe_float(matrix.get("tramo_30_90", {}).get("sobre_lo_esperado")),
            "tramo_90_mas": _safe_float(matrix.get("tramo_90_mas", {}).get("sobre_lo_esperado")),
            "castigo": _safe_float(matrix.get("castigo", {}).get("sobre_lo_esperado")),
        },
    }


def _normalize_periods(rows: list[dict], key: str) -> list[str]:
    return [str(row.get(key) or "").strip() for row in rows if str(row.get(key) or "").strip()]


def get_factura_bit_periods() -> list[str]:
    rows = run_query(
        """
        SELECT DISTINCT periodo
        FROM (
            SELECT periodo
            FROM dbo.tmp_BIT_contencion
            WHERE periodo >= ?
              AND periodo IS NOT NULL
              AND LTRIM(RTRIM(periodo)) <> ''
            UNION
            SELECT periodo
            FROM dbo.tmp_BIT_castigo
            WHERE periodo >= ?
              AND periodo IS NOT NULL
              AND LTRIM(RTRIM(periodo)) <> ''
        ) src
        ORDER BY periodo DESC
        """,
        (MIN_FACTURA_PERIOD, MIN_FACTURA_PERIOD),
    )
    return _normalize_periods(rows, "periodo")


def _get_available_periods(selected_scope: str) -> list[str]:
    return get_factura_bit_periods()


def _select_period(periodo: str | None, available_periods: list[str]) -> str:
    requested_period = str(periodo or "").strip()
    if not available_periods:
        return ""
    if requested_period and requested_period in available_periods:
        return requested_period
    return available_periods[0]


def _empty_business_row(key: str, label: str) -> dict:
    return {
        "key": key,
        "label": label,
        "has_real_invoice": False,
    }


def _build_empty_dashboard(selected_scope: str, available_periods: list[str]) -> dict:
    businesses = [_empty_business_row(BIT_SCOPE, "Bco Internacional")]

    matrix = _zero_matrix()
    return {
        "periodo": "",
        "scope": selected_scope,
        "available_scopes": [GLOBAL_SCOPE, BIT_SCOPE],
        "businesses": businesses,
        "scope_summary": {
            "simulado_total": 0.0,
            "simulado_esperado": 0.0,
            "factura_real_total": None,
            "factura_real_periodo": None,
            "negocios_con_datos": 0,
            "negocios_con_factura_real": 0,
        },
        "business_summary_rows": [],
        "available_periods": available_periods,
        "matrix": matrix,
        "percentages": _percentages(),
        "summary": {
            "base_30_90": 0.0,
            "base_90_mas": 0.0,
            "base_castigo": 0.0,
            "castigo_simulado": 0.0,
            "total_esperado": 0.0,
            "total_sobre": 0.0,
        },
    }


def _build_bit_response(selected_period: str, available_periods: list[str]) -> dict:
    cont_rows = run_query(
        """
        WITH filtered_data AS (
            SELECT
                CASE
                    WHEN LEFT(COALESCE(tramo_proyectado_nuevo, ''), 2) IN ('T1', 'T2', 'T3') THEN '30-90'
                    WHEN LEFT(COALESCE(tramo_proyectado_nuevo, ''), 2) IN ('T4', 'T5', 'T6', 'T7') THEN '90+'
                    ELSE ''
                END AS tramo,
                CASE
                    WHEN gasto_cobranza IS NULL THEN 0
                    WHEN ISNUMERIC(CONVERT(VARCHAR(255), gasto_cobranza)) = 1 THEN CAST(gasto_cobranza AS float)
                    ELSE 0
                END AS gasto_cobranza
            FROM dbo.tmp_BIT_contencion
            WHERE periodo = ?
              AND periodo >= ?
              AND LEFT(COALESCE(tramo_proyectado_nuevo, ''), 2) <> 'T0'
        )
        SELECT
            SUM(CASE WHEN tramo = '30-90' THEN gasto_cobranza ELSE 0 END) AS base_30_90,
            SUM(CASE WHEN tramo = '90+' THEN gasto_cobranza ELSE 0 END) AS base_90_mas
        FROM filtered_data
        WHERE tramo IN ('30-90', '90+')
        """,
        (selected_period, MIN_FACTURA_PERIOD),
    )

    castigo_rows = run_query(
        """
        SELECT
            SUM(
                CASE
                    WHEN mto_recupero_final IS NULL THEN 0
                    WHEN ISNUMERIC(CONVERT(VARCHAR(255), mto_recupero_final)) = 1 THEN CAST(mto_recupero_final AS float)
                    ELSE 0
                END
            ) AS base_castigo,
            SUM(
                CASE
                    WHEN mto_recupero_final IS NULL THEN 0
                    WHEN ISNUMERIC(CONVERT(VARCHAR(255), mto_recupero_final)) = 1 THEN CAST(mto_recupero_final AS float)
                    ELSE 0
                END
                *
                CASE
                    WHEN gc_castigo IS NULL THEN 0.25
                    WHEN ISNUMERIC(CONVERT(VARCHAR(255), gc_castigo)) = 1 THEN CAST(gc_castigo AS float)
                    ELSE 0.25
                END
            ) AS castigo_simulado
        FROM dbo.tmp_BIT_castigo
        WHERE periodo = ?
          AND periodo >= ?
        """,
        (selected_period, MIN_FACTURA_PERIOD),
    )

    row = cont_rows[0] if cont_rows else {}
    castigo_row = castigo_rows[0] if castigo_rows else {}
    base_30_90 = _safe_float(row.get("base_30_90"))
    base_90_mas = _safe_float(row.get("base_90_mas"))
    base_castigo = _safe_float(castigo_row.get("base_castigo"))
    castigo_simulado = _safe_float(castigo_row.get("castigo_simulado"))
    percentages = _percentages()
    matrix = {
        "tramo_30_90": {
            "muy_bajo_lo_esperado": base_30_90 * percentages["tramo_30_90"]["muy_bajo_lo_esperado"],
            "bajo_lo_esperado": base_30_90 * percentages["tramo_30_90"]["bajo_lo_esperado"],
            "esperado": base_30_90 * percentages["tramo_30_90"]["esperado"],
            "sobre_lo_esperado": base_30_90 * percentages["tramo_30_90"]["sobre_lo_esperado"],
        },
        "tramo_90_mas": {
            "muy_bajo_lo_esperado": base_90_mas * percentages["tramo_90_mas"]["muy_bajo_lo_esperado"],
            "bajo_lo_esperado": base_90_mas * percentages["tramo_90_mas"]["bajo_lo_esperado"],
            "esperado": base_90_mas * percentages["tramo_90_mas"]["esperado"],
            "sobre_lo_esperado": base_90_mas * percentages["tramo_90_mas"]["sobre_lo_esperado"],
        },
        "castigo": {
            "muy_bajo_lo_esperado": castigo_simulado,
            "bajo_lo_esperado": castigo_simulado,
            "esperado": castigo_simulado,
            "sobre_lo_esperado": castigo_simulado,
        },
        "simulacion_total": {},
    }
    matrix["simulacion_total"] = {
        key: matrix["tramo_30_90"][key] + matrix["tramo_90_mas"][key] + matrix["castigo"][key]
        for key in ("muy_bajo_lo_esperado", "bajo_lo_esperado", "esperado", "sobre_lo_esperado")
    }
    summary = {
        "base_30_90": base_30_90,
        "base_90_mas": base_90_mas,
        "base_castigo": base_castigo,
        "castigo_simulado": castigo_simulado,
        "total_esperado": matrix["simulacion_total"]["esperado"],
        "total_sobre": matrix["simulacion_total"]["sobre_lo_esperado"],
    }
    business_summary_rows = [
        _build_business_summary(
            business_key=BIT_SCOPE,
            business_label="Bco Internacional",
            summary=summary,
            matrix=matrix,
            has_real_invoice=False,
        )
    ]
    scope_summary = {
        "simulado_total": sum(row["simulado_total"] for row in business_summary_rows),
        "simulado_esperado": sum(row["simulado_esperado"] for row in business_summary_rows),
        "factura_real_total": None,
        "factura_real_periodo": None,
        "negocios_con_datos": len(business_summary_rows),
        "negocios_con_factura_real": sum(1 for row in business_summary_rows if row["has_real_invoice"]),
    }

    return {
        "periodo": selected_period,
        "scope": BIT_SCOPE,
        "available_scopes": [GLOBAL_SCOPE, BIT_SCOPE],
        "businesses": [
            {
                "key": BIT_SCOPE,
                "label": "Bco Internacional",
                "has_real_invoice": False,
            }
        ],
        "scope_summary": scope_summary,
        "business_summary_rows": business_summary_rows,
        "available_periods": available_periods,
        "matrix": matrix,
        "percentages": percentages,
        "summary": summary,
    }


def _build_global_response(selected_period: str, available_periods: list[str]) -> dict:
    bit_available = get_factura_bit_periods()
    business_summary_rows: list[dict] = []

    if selected_period in bit_available:
        bit_response = _build_bit_response(selected_period, bit_available)
        business_summary_rows.extend(bit_response["business_summary_rows"])

    scope_summary = {
        "simulado_total": sum(row["simulado_total"] for row in business_summary_rows),
        "simulado_esperado": sum(row["simulado_esperado"] for row in business_summary_rows),
        "factura_real_total": sum(
            row["factura_real_total"] for row in business_summary_rows if row["factura_real_total"] is not None
        )
        if any(row["factura_real_total"] is not None for row in business_summary_rows)
        else None,
        "factura_real_periodo": selected_period if business_summary_rows else None,
        "negocios_con_datos": len(business_summary_rows),
        "negocios_con_factura_real": sum(1 for row in business_summary_rows if row["has_real_invoice"]),
    }

    return {
        "periodo": selected_period,
        "scope": GLOBAL_SCOPE,
        "available_scopes": [GLOBAL_SCOPE, BIT_SCOPE],
        "businesses": [
            {
                "key": BIT_SCOPE,
                "label": "Bco Internacional",
                "has_real_invoice": any(row["key"] == BIT_SCOPE and row["has_real_invoice"] for row in business_summary_rows),
            },
        ],
        "scope_summary": scope_summary,
        "business_summary_rows": business_summary_rows,
        "available_periods": available_periods,
        "matrix": _zero_matrix(),
        "percentages": _percentages(),
        "summary": {
            "base_30_90": 0.0,
            "base_90_mas": 0.0,
            "base_castigo": 0.0,
            "castigo_simulado": 0.0,
            "total_esperado": scope_summary["simulado_esperado"],
            "total_sobre": scope_summary["simulado_total"],
        },
    }


def get_factura_bit_dashboard(periodo: str | None, scope: str | None = None) -> dict:
    selected_scope = (str(scope or "").strip()) or GLOBAL_SCOPE
    if selected_scope not in SUPPORTED_SCOPES:
        raise ValueError(f"El scope {selected_scope} no está soportado para factura")

    available_periods = _get_available_periods(selected_scope)
    selected_period = _select_period(periodo, available_periods)

    if selected_period and selected_period < MIN_FACTURA_PERIOD:
        raise ValueError(f"El periodo debe ser {MIN_FACTURA_PERIOD} o posterior")

    if not selected_period:
        return _build_empty_dashboard(selected_scope, available_periods)

    if selected_scope == BIT_SCOPE:
        return _build_bit_response(selected_period, available_periods)
    return _build_global_response(selected_period, available_periods)
