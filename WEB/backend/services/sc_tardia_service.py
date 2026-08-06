from __future__ import annotations

from datetime import date

from database import run_query


BLOCK_ORDER = [
    "C3",
    "SUSCEPTIBLE CV",
    "C5",
    "C6",
    "PRE CASTIGO",
    "F1 - F2",
    "F3",
    "F4",
    "TOTAL F1 - F4",
]


def _clean_text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _period_date(periodo: str | None) -> str:
    if periodo:
        text = str(periodo).strip()
        if len(text) >= 10:
            return text[:10]
        return text

    sql = """
    SELECT CONVERT(char(10), MAX(fecha), 126) AS periodo
    FROM dbo.vw_stc_sabana_avance
    WHERE fecha IS NOT NULL
    """
    rows = run_query(sql)
    return (rows[0].get("periodo") if rows else None) or date.today().isoformat()


def _block_index(block: str) -> int:
    try:
        return BLOCK_ORDER.index(block)
    except ValueError:
        return 99


def _active_blocks_by_executive(periodo: str) -> dict[str, list[str]]:
    sql = """
    SELECT
        LTRIM(RTRIM(ejecutivo)) AS ejecutivo,
        LTRIM(RTRIM(bloque)) AS bloque
    FROM dbo.stc_bloques_ejecutivos
    WHERE periodo = DATEFROMPARTS(YEAR(CAST(? AS DATE)), MONTH(CAST(? AS DATE)), 1)
      AND activo = 1
    ORDER BY ejecutivo, bloque
    """
    active: dict[str, list[str]] = {}
    for row in run_query(sql, (periodo, periodo)):
        ejecutivo = row.get("ejecutivo") or ""
        bloque = row.get("bloque") or ""
        if ejecutivo and bloque:
            active.setdefault(ejecutivo, []).append(bloque)
    return active


def _level_1_weights(periodo: str) -> dict[str, float]:
    sql = """
    SELECT
        meta_tipo,
        MAX(ponderador_nivel_1_pct) AS ponderador_nivel_1_pct
    FROM dbo.stc_metas_mensuales
    WHERE periodo = DATEFROMPARTS(YEAR(CAST(? AS DATE)), MONTH(CAST(? AS DATE)), 1)
      AND activo = 1
      AND meta_tipo IN ('PCT', 'STOCK')
    GROUP BY meta_tipo
    """
    weights = {"PCT": 0.0, "PTC": 0.0, "STOCK": 0.0}
    for row in run_query(sql, (periodo, periodo)):
        meta_tipo = row.get("meta_tipo") or ""
        if meta_tipo in weights:
            weights[meta_tipo] = float(row.get("ponderador_nivel_1_pct") or 0)
    weights["PTC"] = weights["PCT"]
    return weights


def _sc_tardia_sql(extra_where: str = "") -> str:
    return f"""
    WITH parametros AS (
        SELECT CAST(? AS DATE) AS fecha_consulta
    ),

    periodo_meta AS (
        SELECT
            fecha_consulta,
            DATEFROMPARTS(YEAR(fecha_consulta), MONTH(fecha_consulta), 1) AS periodo
        FROM parametros
    ),

    ultimas_fechas AS (
        SELECT
            v.origen,
            MAX(v.fecha) AS fecha_utilizada
        FROM dbo.vw_stc_sabana_avance v
        CROSS JOIN parametros p
        WHERE v.fecha <= p.fecha_consulta
        GROUP BY v.origen
    ),

    base AS (
        SELECT
            v.fecha,
            v.rut,
            v.operacion,
            v.zona,
            v.deuda,
            v.contenido,
            v.normalizado,
            LTRIM(RTRIM(v.ciclo)) AS ciclo,
            LTRIM(RTRIM(v.apertura)) AS apertura,
            LTRIM(RTRIM(v.ejecutivo)) AS ejecutivo,
            v.origen
        FROM dbo.vw_stc_sabana_avance v
        INNER JOIN ultimas_fechas uf
            ON v.origen = uf.origen
           AND v.fecha = uf.fecha_utilizada
    ),

    stc_clasificado AS (
        SELECT
            fecha,
            rut,
            operacion,
            zona,
            deuda,
            contenido,
            normalizado,
            ciclo,
            apertura,
            ejecutivo,
            origen,
            CASE
                WHEN ciclo IN ('C6', 'C7', 'C8') AND apertura = 'SUSCEPTIBLE CASTIGO' THEN 'PRE CASTIGO'
                WHEN ciclo = 'C6' AND ISNULL(apertura, '') <> 'SUSCEPTIBLE CASTIGO' THEN 'C6'
                WHEN ciclo = 'C3' THEN 'C3'
                WHEN apertura = 'SUSCEPTIBLE CV' THEN 'SUSCEPTIBLE CV'
                WHEN ciclo = 'C5' THEN 'C5'
                ELSE NULL
            END AS bloque
        FROM base
        WHERE origen = 'STC'
    ),

    castigo_clasificado AS (
        SELECT
            fecha,
            rut,
            operacion,
            zona,
            deuda,
            contenido,
            normalizado,
            ciclo,
            apertura,
            ejecutivo,
            origen,
            CASE
                WHEN ciclo IN ('F1', 'F2') THEN 'F1 - F2'
                WHEN ciclo = 'F3' THEN 'F3'
                WHEN ciclo = 'F4' THEN 'F4'
                ELSE NULL
            END AS bloque
        FROM base
        WHERE origen = 'CASTIGO'
    ),

    metas AS (
        SELECT
            m.periodo,
            LTRIM(RTRIM(m.variable)) AS variable,
            m.meta_valor,
            m.meta_tipo,
            m.ponderador_nivel_1_pct,
            m.ponderador_nivel_2_pct,
            m.ponderador_nivel_3_pct
        FROM dbo.stc_metas_mensuales m
        INNER JOIN periodo_meta p
            ON m.periodo = p.periodo
        WHERE m.activo = 1
    ),

    resultado_stc_base AS (
        SELECT
            'STC' AS reporte,
            bloque,
            ejecutivo,
            zona,
            SUM(ISNULL(deuda, 0)) AS deuda_asignada,
            SUM(ISNULL(contenido, 0)) AS contenido,
            CASE WHEN bloque = 'C3' THEN SUM(ISNULL(normalizado, 0)) ELSE NULL END AS normalizado,
            COUNT(DISTINCT operacion) AS cantidad_casos,
            CASE
                WHEN bloque = 'C3' THEN 'Contención C3'
                WHEN bloque = 'SUSCEPTIBLE CV' THEN 'Cont Suscept CV'
                WHEN bloque = 'C5' THEN 'Contención C5'
                WHEN bloque = 'C6' THEN 'Salidas CV C6'
                WHEN bloque = 'PRE CASTIGO' THEN 'Contención Pre Castigo'
                ELSE NULL
            END AS variable_meta_cont,
            CASE WHEN bloque = 'C3' THEN 'Normalización C3' ELSE NULL END AS variable_meta_norm
        FROM stc_clasificado
        WHERE bloque IS NOT NULL
        GROUP BY bloque, ejecutivo, zona
    ),

    resultado_stc AS (
        SELECT
            r.reporte,
            r.bloque,
            r.ejecutivo,
            r.zona,
            r.deuda_asignada,
            CASE WHEN meta_cont.meta_valor IS NULL THEN NULL ELSE ROUND(r.deuda_asignada * meta_cont.meta_valor / 100.0, 0) END AS monto_meta_cont,
            r.contenido,
            CASE WHEN meta_norm.meta_valor IS NULL THEN NULL ELSE ROUND(r.deuda_asignada * meta_norm.meta_valor / 100.0, 0) END AS monto_meta_norm,
            r.normalizado,
            r.cantidad_casos
        FROM resultado_stc_base r
        LEFT JOIN metas meta_cont
            ON meta_cont.variable = r.variable_meta_cont
        LEFT JOIN metas meta_norm
            ON meta_norm.variable = r.variable_meta_norm
    ),

    resultado_castigo_base AS (
        SELECT
            'CASTIGO' AS reporte,
            bloque,
            ejecutivo,
            zona,
            SUM(ISNULL(deuda, 0)) AS deuda_asignada,
            SUM(ISNULL(contenido, 0)) AS contenido,
            COUNT(DISTINCT operacion) AS cantidad_casos,
            CASE
                WHEN bloque = 'F1 - F2' THEN 'Recupero castigo F1 y F2'
                WHEN bloque = 'F3' THEN 'Recupero castigo F3'
                ELSE NULL
            END AS variable_meta_cont
        FROM castigo_clasificado
        WHERE bloque IS NOT NULL
        GROUP BY bloque, ejecutivo, zona
    ),

    resultado_castigo AS (
        SELECT
            r.reporte,
            r.bloque,
            r.ejecutivo,
            r.zona,
            r.deuda_asignada,
            CASE WHEN meta_cont.meta_valor IS NULL THEN NULL ELSE ROUND(r.deuda_asignada * meta_cont.meta_valor / 100.0, 0) END AS monto_meta_cont,
            r.contenido,
            CAST(NULL AS NUMERIC(18, 2)) AS monto_meta_norm,
            CAST(NULL AS NUMERIC(18, 2)) AS normalizado,
            r.cantidad_casos
        FROM resultado_castigo_base r
        LEFT JOIN metas meta_cont
            ON meta_cont.variable = r.variable_meta_cont
    ),

    resultado_castigo_consolidado_base AS (
        SELECT
            'CASTIGO CONSOLIDADO' AS reporte,
            'TOTAL F1 - F4' AS bloque,
            ejecutivo,
            zona,
            SUM(CASE WHEN ciclo IN ('F1', 'F2', 'F3') THEN ISNULL(deuda, 0) ELSE 0 END) AS deuda_asignada,
            SUM(CASE WHEN ciclo IN ('F1', 'F2') THEN ISNULL(deuda, 0) ELSE 0 END) AS deuda_f1_f2,
            SUM(CASE WHEN ciclo = 'F3' THEN ISNULL(deuda, 0) ELSE 0 END) AS deuda_f3,
            SUM(CASE WHEN ciclo IN ('F1', 'F2', 'F3', 'F4') THEN ISNULL(contenido, 0) ELSE 0 END) AS contenido,
            COUNT(DISTINCT operacion) AS cantidad_casos
        FROM base
        WHERE origen = 'CASTIGO'
          AND ciclo IN ('F1', 'F2', 'F3', 'F4')
        GROUP BY ejecutivo, zona
    ),

    resultado_castigo_consolidado AS (
        SELECT
            r.reporte,
            r.bloque,
            r.ejecutivo,
            r.zona,
            r.deuda_asignada,
            ROUND(
                  (r.deuda_f1_f2 * ISNULL(meta_f1_f2.meta_valor, 0) / 100.0)
                + (r.deuda_f3 * ISNULL(meta_f3.meta_valor, 0) / 100.0),
                0
            ) AS monto_meta_cont,
            r.contenido,
            CAST(NULL AS NUMERIC(18, 2)) AS monto_meta_norm,
            CAST(NULL AS NUMERIC(18, 2)) AS normalizado,
            r.cantidad_casos
        FROM resultado_castigo_consolidado_base r
        LEFT JOIN metas meta_f1_f2
            ON meta_f1_f2.variable = 'Recupero castigo F1 y F2'
        LEFT JOIN metas meta_f3
            ON meta_f3.variable = 'Recupero castigo F3'
    ),

    resultado_final AS (
        SELECT * FROM resultado_stc
        UNION ALL
        SELECT * FROM resultado_castigo
        UNION ALL
        SELECT * FROM resultado_castigo_consolidado
    ),

    resultado_filtrado AS (
        SELECT
            rf.reporte,
            rf.bloque,
            rf.ejecutivo,
            rf.zona,
            rf.deuda_asignada,
            rf.monto_meta_cont,
            rf.contenido,
            rf.monto_meta_norm,
            rf.normalizado,
            rf.cantidad_casos
        FROM resultado_final rf
        CROSS JOIN periodo_meta pm
        INNER JOIN dbo.stc_bloques_ejecutivos be
            ON LTRIM(RTRIM(be.ejecutivo)) = rf.ejecutivo
           AND LTRIM(RTRIM(be.bloque)) = rf.bloque
           AND be.periodo = pm.periodo
           AND be.activo = 1
    )

    SELECT
        reporte,
        bloque,
        ejecutivo,
        zona,
        CAST(ROUND(deuda_asignada, 0) AS BIGINT) AS deuda_asignada,
        CAST(ROUND(monto_meta_cont, 0) AS BIGINT) AS monto_meta_cont,
        CAST(ROUND(contenido, 0) AS BIGINT) AS contenido,
        CAST(ROUND(monto_meta_norm, 0) AS BIGINT) AS monto_meta_norm,
        CAST(ROUND(normalizado, 0) AS BIGINT) AS normalizado,
        cantidad_casos
    FROM resultado_filtrado
    {extra_where}
    ORDER BY
        CASE reporte
            WHEN 'STC' THEN 1
            WHEN 'CASTIGO' THEN 2
            WHEN 'CASTIGO CONSOLIDADO' THEN 3
            ELSE 4
        END,
        ejecutivo,
        zona,
        CASE bloque
            WHEN 'C3' THEN 1
            WHEN 'SUSCEPTIBLE CV' THEN 2
            WHEN 'C5' THEN 3
            WHEN 'C6' THEN 4
            WHEN 'PRE CASTIGO' THEN 5
            WHEN 'F1 - F2' THEN 6
            WHEN 'F3' THEN 7
            WHEN 'F4' THEN 8
            WHEN 'TOTAL F1 - F4' THEN 9
            ELSE 10
        END
    """


def _rows_from_query(filters: dict) -> list[dict]:
    periodo = _period_date(filters.get("periodo"))
    active_blocks = _active_blocks_by_executive(periodo)
    level_1_weights = _level_1_weights(periodo)
    clauses: list[str] = []
    params: list = [periodo]

    if _clean_text(filters.get("zona")):
        clauses.append("LTRIM(RTRIM(zona)) = ?")
        params.append(_clean_text(filters.get("zona")))

    if _clean_text(filters.get("ejecutivo")):
        clauses.append("LTRIM(RTRIM(ejecutivo)) = ?")
        params.append(_clean_text(filters.get("ejecutivo")))

    if _clean_text(filters.get("ciclo")):
        clauses.append("LTRIM(RTRIM(bloque)) = ?")
        params.append(_clean_text(filters.get("ciclo")))

    extra_where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = run_query(_sc_tardia_sql(extra_where), tuple(params))

    response: list[dict] = []
    for row in rows:
        response.append(
            {
                "periodo": periodo,
                "reporte": row.get("reporte") or "",
                "bloque": row.get("bloque") or "",
                "ejecutivo": row.get("ejecutivo") or "SIN EJECUTIVO",
                "zona": row.get("zona") or "",
                "deuda_asignada": float(row.get("deuda_asignada") or 0),
                "monto_meta_cont": float(row.get("monto_meta_cont") or 0),
                "contenido": float(row.get("contenido") or 0),
                "monto_meta_norm": float(row.get("monto_meta_norm") or 0),
                "normalizado": float(row.get("normalizado") or 0),
                "cantidad_casos": int(row.get("cantidad_casos") or 0),
                "bloques_activos": active_blocks.get(row.get("ejecutivo") or "", []),
                "ponderadores_nivel_1": level_1_weights,
            }
        )

    response.sort(key=lambda x: (x["ejecutivo"], x["zona"], _block_index(x["bloque"])))
    return response


def get_cycle_view(filters: dict) -> list[dict]:
    return _rows_from_query(filters)


def get_general_view(filters: dict) -> list[dict]:
    return _rows_from_query(filters)


def get_filter_values() -> dict:
    sql_periodos = """
    SELECT DISTINCT CONVERT(char(10), fecha, 126) AS valor
    FROM dbo.vw_stc_sabana_avance
    WHERE fecha IS NOT NULL
    ORDER BY valor DESC
    """
    sql_zonas = """
    SELECT DISTINCT LTRIM(RTRIM(zona)) AS valor
    FROM dbo.vw_stc_sabana_avance
    WHERE zona IS NOT NULL AND LTRIM(RTRIM(zona)) <> ''
    ORDER BY valor
    """
    sql_ejecutivos = """
    SELECT DISTINCT LTRIM(RTRIM(ejecutivo)) AS valor
    FROM dbo.vw_stc_sabana_avance
    WHERE ejecutivo IS NOT NULL AND LTRIM(RTRIM(ejecutivo)) <> ''
    ORDER BY valor
    """

    return {
        "periodos": [r["valor"] for r in run_query(sql_periodos) if r.get("valor")],
        "tramos": BLOCK_ORDER,
        "aperturas": [],
        "ejecutivos": [r["valor"] for r in run_query(sql_ejecutivos) if r.get("valor")],
        "zonas": [r["valor"] for r in run_query(sql_zonas) if r.get("valor")],
    }
