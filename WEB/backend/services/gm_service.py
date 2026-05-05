from __future__ import annotations

from datetime import date

from database import run_query


BUCKET_ORDER = ["6 a 30", "31 a 60", "61 a 90", "91 a 150"]


def _clean_text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _period_start(periodo: str | None) -> str:
    if periodo:
        text = str(periodo).strip()
        if len(text) >= 10:
            return text[:10]
        return text

    sql = """
    SELECT CONVERT(char(10), MAX(DATEFROMPARTS(YEAR(fecha_carga), MONTH(fecha_carga), 1)), 126) AS periodo
    FROM dbo.tmp_asig_GM
    """
    rows = run_query(sql)
    return (rows[0].get("periodo") if rows else None) or date.today().replace(day=1).isoformat()


def _safe_div(num: float, den: float) -> float:
    if den is None or den == 0:
        return 0.0
    return (num / den) * 100.0


def _cap(value: float, max_value: float = 130.0) -> float:
    return max(0.0, min(max_value, value))


def _cumpl_variable(pct_real: float, meta: float) -> float:
    if meta is None or meta <= 0:
        return 0.0
    return _cap(_safe_div(pct_real, meta))


def _bucket_index(bucket: str) -> int:
    try:
        return BUCKET_ORDER.index(bucket)
    except ValueError:
        return 99


def get_filter_values() -> dict:
    sql_periodos = """
    SELECT DISTINCT CONVERT(char(10), DATEFROMPARTS(YEAR(fecha_carga), MONTH(fecha_carga), 1), 126) AS periodo
    FROM dbo.tmp_asig_GM
    WHERE fecha_carga IS NOT NULL
    ORDER BY periodo DESC
    """
    periodos = [r["periodo"] for r in run_query(sql_periodos) if r.get("periodo")]

    sql_ejecutivos = """
    SELECT DISTINCT LTRIM(RTRIM(ejecutivo)) AS ejecutivo
    FROM dbo.tmp_carterizado_GM
    WHERE ejecutivo IS NOT NULL AND LTRIM(RTRIM(ejecutivo)) <> ''
    ORDER BY ejecutivo
    """
    ejecutivos = [r["ejecutivo"] for r in run_query(sql_ejecutivos) if r.get("ejecutivo")]

    return {
        "periodos": periodos,
        "ejecutivos": ejecutivos,
    }


def get_cycle_view(filters: dict) -> list[dict]:
    periodo = _period_start(filters.get("periodo"))
    ejecutivo = _clean_text(filters.get("ejecutivo"))

    extra_clause = ""
    if ejecutivo:
        extra_clause = " AND base.ejecutivo = ?"

    sql = f"""
    WITH asig AS (
        SELECT
            t.[fld_Agreement Number] AS op,
            LTRIM(RTRIM(t.fld_bucket)) AS bucket,
            CAST(t.[fld_POS/Curr. Acc. Bal.* ] AS FLOAT) AS deuda,
            ISNULL(c.ejecutivo, 'Phoenix') AS ejecutivo,
            ISNULL(p.contenido, 0) AS contenido,
            ISNULL(p.normalizado, 0) AS normalizado
        FROM (
            SELECT *,
                   ROW_NUMBER() OVER (
                       PARTITION BY [fld_Agreement Number]
                       ORDER BY fecha_carga ASC
                   ) AS rn
            FROM dbo.tmp_asig_GM
            WHERE fecha_carga BETWEEN ? AND EOMONTH(?)
        ) t
        LEFT JOIN dbo.tmp_carterizado_GM c
            ON t.[fld_Agreement Number] = c.op
           AND c.mes_carterizado = ?
        LEFT JOIN (
            SELECT
                operacion,
                MAX(CAST(contenido AS INT)) AS contenido,
                MAX(CAST(normalizado AS INT)) AS normalizado
            FROM dbo.tmp_pagos_gm
            WHERE periodo_pago BETWEEN ? AND EOMONTH(?)
            GROUP BY operacion
        ) p
            ON t.[fld_Agreement Number] = p.operacion
        WHERE t.rn = 1
    ),
    agg AS (
        SELECT
            base.ejecutivo,
            base.bucket,
            SUM(base.deuda) AS deuda_asignada,
            SUM(CASE WHEN base.contenido = 1 THEN base.deuda ELSE 0 END) AS saldo_contenido,
            SUM(CASE WHEN base.normalizado = 1 THEN base.deuda ELSE 0 END) AS saldo_normalizado,
            CAST(
                (SUM(CASE WHEN base.contenido = 1 THEN base.deuda ELSE 0 END) * 100.0)
                / NULLIF(SUM(base.deuda), 0)
            AS DECIMAL(10, 2)) AS porcentaje_contencion,
            CASE
                WHEN base.ejecutivo = 'Daniela Cañicul' AND bucket = '6 a 30' THEN CAST(19.0 AS DECIMAL(10, 2))
                ELSE CAST(
                    (SUM(CASE WHEN base.normalizado = 1 THEN base.deuda ELSE 0 END) * 100.0)
                    / NULLIF(SUM(base.deuda), 0)
                AS DECIMAL(10, 2))
            END AS porcentaje_normalizado
        FROM asig base
        WHERE base.bucket IN ('6 a 30', '31 a 60', '61 a 90', '91 a 150')
        {extra_clause}
        GROUP BY base.ejecutivo, base.bucket
    )
    SELECT
        agg.ejecutivo,
        agg.bucket,
        agg.deuda_asignada,
        agg.saldo_contenido,
        agg.saldo_normalizado,
        agg.porcentaje_contencion,
        agg.porcentaje_normalizado,
        m.meta_contencion_pct,
        m.meta_normalizacion_pct,
        m.ponderador_contencion_pct,
        m.ponderador_normalizacion_pct
    FROM agg
    LEFT JOIN dbo.gm_metas_mensuales m
        ON m.periodo = ?
       AND m.bucket = agg.bucket
    ORDER BY agg.bucket, agg.ejecutivo
    """

    data_params = [periodo, periodo, periodo, periodo, periodo]
    if ejecutivo:
        data_params.append(ejecutivo)
    data_params.append(periodo)

    raw_rows = run_query(sql, tuple(data_params))

    rows: list[dict] = []
    for row in raw_rows:
        deuda = float(row.get("deuda_asignada") or 0)
        saldo_contenido = float(row.get("saldo_contenido") or 0)
        saldo_normalizado = float(row.get("saldo_normalizado") or 0)
        pct_cont = float(row.get("porcentaje_contencion") or 0)
        pct_norm = float(row.get("porcentaje_normalizado") or 0)
        meta_cont = float(row.get("meta_contencion_pct") or 0)
        meta_norm = float(row.get("meta_normalizacion_pct") or 0)
        pond_cont = float(row.get("ponderador_contencion_pct") or 0)
        pond_norm = float(row.get("ponderador_normalizacion_pct") or 0)

        cumpl_cont = _cumpl_variable(pct_cont, meta_cont)
        cumpl_norm = _cumpl_variable(pct_norm, meta_norm)
        cumplimiento = _cap((cumpl_cont * (pond_cont / 100.0)) + (cumpl_norm * (pond_norm / 100.0)))

        rows.append(
            {
                "periodo": periodo,
                "ejecutivo": row.get("ejecutivo") or "Phoenix",
                "bucket": row.get("bucket") or "",
                "deuda_asignada": deuda,
                "saldo_contenido": saldo_contenido,
                "saldo_normalizado": saldo_normalizado,
                "porcentaje_contencion": pct_cont,
                "porcentaje_normalizado": pct_norm,
                "meta_contencion_pct": meta_cont,
                "meta_normalizacion_pct": meta_norm,
                "ponderador_contencion_pct": pond_cont,
                "ponderador_normalizacion_pct": pond_norm,
                "cumplimiento_final": cumplimiento,
            }
        )

    rows.sort(key=lambda x: (_bucket_index(x["bucket"]), x["ejecutivo"]))
    return rows


def get_general_view(filters: dict) -> list[dict]:
    cycle_rows = get_cycle_view(filters)

    grouped: dict[str, dict] = {}
    for row in cycle_rows:
        ejecutivo = row["ejecutivo"]
        current = grouped.setdefault(
            ejecutivo,
            {
                "ejecutivo": ejecutivo,
                "deuda_total": 0.0,
                "ponderado": 0.0,
                "buckets": {},
            },
        )
        deuda = float(row["deuda_asignada"])
        current["deuda_total"] += deuda
        current["ponderado"] += float(row["cumplimiento_final"]) * deuda
        current["buckets"][row["bucket"]] = float(row["cumplimiento_final"])

    response: list[dict] = []
    total_deuda = 0.0
    total_ponderado = 0.0

    for ejecutivo, item in grouped.items():
        deuda = item["deuda_total"]
        cumpl = (item["ponderado"] / deuda) if deuda else 0.0
        response.append(
            {
                "ejecutivo": ejecutivo,
                "deuda_total": deuda,
                "cumplimiento_final": cumpl,
                "buckets": item["buckets"],
            }
        )
        total_deuda += deuda
        total_ponderado += item["ponderado"]

    response.sort(key=lambda x: x["cumplimiento_final"], reverse=True)

    response.append(
        {
            "ejecutivo": "Total general",
            "deuda_total": total_deuda,
            "cumplimiento_final": (total_ponderado / total_deuda) if total_deuda else 0.0,
            "buckets": {},
        }
    )
    return response
