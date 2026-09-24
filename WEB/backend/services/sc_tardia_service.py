from __future__ import annotations

from datetime import date

from database import run_query


BLOCK_ORDER = [
    "C3",
    "SUSCEPTIBLE CV",
    "C5",
    "C6",
    "PRE CASTIGO",
    "F1",
    "F2",
    "F3",
    "F4",
    "TOTAL F1 - F4",
]


def _zona_sql(column: str) -> str:
    """Unifica la zona: la carga CASTIGO trae 'CENTRO-NORTE', 'CENTRO-SUR', 'METROPOLITANA'
    y STC trae 'ZONA NORTE CENTRO', 'ZONA CENTRO SUR', 'ZONA METROPOLITANA'."""
    return f"""
        CASE UPPER(REPLACE(REPLACE(LTRIM(RTRIM({column})), '-', ' '), 'ZONA ', ''))
            WHEN 'CENTRO SUR' THEN 'ZONA CENTRO SUR'
            WHEN 'METROPOLITANA' THEN 'ZONA METROPOLITANA'
            WHEN 'CENTRO NORTE' THEN 'ZONA NORTE CENTRO'
            WHEN 'NORTE CENTRO' THEN 'ZONA NORTE CENTRO'
            ELSE NULLIF(LTRIM(RTRIM({column})), '')
        END"""


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


def _executive_key(value) -> str:
    """Clave normalizada para cruzar ejecutivos entre tablas.

    El JOIN en SQL cruza sin problemas porque el collation de la base es
    case-insensitive, pero los diccionarios de Python no: la sabana puede traer
    el nombre en mayusculas y stc_bloques_ejecutivos en Title Case.
    """
    return _clean_text(value).upper()


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
            # La asignacion historica 'F1 - F2' habilita los bloques F1 y F2, que se reportan por separado.
            bloques = ["F1", "F2"] if bloque == "F1 - F2" else [bloque]
            actuales = active.setdefault(_executive_key(ejecutivo), [])
            actuales.extend(b for b in bloques if b not in actuales)
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
            {_zona_sql("v.zona")} AS zona,
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
                WHEN ciclo = 'F1' THEN 'F1'
                WHEN ciclo = 'F2' THEN 'F2'
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
            SUM(CASE WHEN ciclo = 'F1' THEN ISNULL(deuda, 0) ELSE 0 END) AS deuda_f1,
            SUM(CASE WHEN ciclo = 'F2' THEN ISNULL(deuda, 0) ELSE 0 END) AS deuda_f2,
            SUM(CASE WHEN ciclo = 'F3' THEN ISNULL(deuda, 0) ELSE 0 END) AS deuda_f3,
            COUNT(DISTINCT operacion) AS cantidad_casos
        FROM castigo_clasificado
        WHERE bloque IS NOT NULL
        GROUP BY bloque, ejecutivo, zona
    ),

    -- Meta de castigo por fase = asignacion de la fase x % de la fase.
    -- Desde 2026-08 las metas vienen separadas (F1, F2); antes era una sola 'F1 y F2'.
    metas_castigo AS (
        SELECT
            COALESCE(
                MAX(CASE WHEN variable = 'Recupero castigo F1' THEN meta_valor END),
                MAX(CASE WHEN variable = 'Recupero castigo F1 y F2' THEN meta_valor END)
            ) AS pct_f1,
            COALESCE(
                MAX(CASE WHEN variable = 'Recupero castigo F2' THEN meta_valor END),
                MAX(CASE WHEN variable = 'Recupero castigo F1 y F2' THEN meta_valor END)
            ) AS pct_f2,
            MAX(CASE WHEN variable = 'Recupero castigo F3' THEN meta_valor END) AS pct_f3
        FROM metas
    ),

    resultado_castigo AS (
        SELECT
            r.reporte,
            r.bloque,
            r.ejecutivo,
            r.zona,
            r.deuda_asignada,
            CASE
                WHEN r.bloque = 'F1' THEN ROUND(r.deuda_f1 * ISNULL(mc.pct_f1, 0) / 100.0, 0)
                WHEN r.bloque = 'F2' THEN ROUND(r.deuda_f2 * ISNULL(mc.pct_f2, 0) / 100.0, 0)
                WHEN r.bloque = 'F3' THEN ROUND(r.deuda_f3 * ISNULL(mc.pct_f3, 0) / 100.0, 0)
                ELSE NULL
            END AS monto_meta_cont,
            r.contenido,
            CAST(NULL AS NUMERIC(18, 2)) AS monto_meta_norm,
            CAST(NULL AS NUMERIC(18, 2)) AS normalizado,
            r.cantidad_casos
        FROM resultado_castigo_base r
        CROSS JOIN metas_castigo mc
    ),

    -- Cumplimiento castigo = SUM(recupero F1..F3) / SUM(meta F1..F3): se suma primero y se divide despues.
    resultado_castigo_consolidado_base AS (
        SELECT
            'CASTIGO CONSOLIDADO' AS reporte,
            'TOTAL F1 - F4' AS bloque,
            ejecutivo,
            zona,
            SUM(CASE WHEN ciclo IN ('F1', 'F2', 'F3') THEN ISNULL(deuda, 0) ELSE 0 END) AS deuda_asignada,
            SUM(CASE WHEN ciclo = 'F1' THEN ISNULL(deuda, 0) ELSE 0 END) AS deuda_f1,
            SUM(CASE WHEN ciclo = 'F2' THEN ISNULL(deuda, 0) ELSE 0 END) AS deuda_f2,
            SUM(CASE WHEN ciclo = 'F3' THEN ISNULL(deuda, 0) ELSE 0 END) AS deuda_f3,
            SUM(CASE WHEN ciclo IN ('F1', 'F2', 'F3') THEN ISNULL(contenido, 0) ELSE 0 END) AS contenido,
            COUNT(DISTINCT operacion) AS cantidad_casos
        FROM base
        WHERE origen = 'CASTIGO'
          AND ciclo IN ('F1', 'F2', 'F3')
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
                  (r.deuda_f1 * ISNULL(mc.pct_f1, 0) / 100.0)
                + (r.deuda_f2 * ISNULL(mc.pct_f2, 0) / 100.0)
                + (r.deuda_f3 * ISNULL(mc.pct_f3, 0) / 100.0),
                0
            ) AS monto_meta_cont,
            r.contenido,
            CAST(NULL AS NUMERIC(18, 2)) AS monto_meta_norm,
            CAST(NULL AS NUMERIC(18, 2)) AS normalizado,
            r.cantidad_casos
        FROM resultado_castigo_consolidado_base r
        CROSS JOIN metas_castigo mc
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
        WHERE EXISTS (
            SELECT 1
            FROM dbo.stc_bloques_ejecutivos be
            WHERE LTRIM(RTRIM(be.ejecutivo)) = rf.ejecutivo
              AND be.periodo = pm.periodo
              AND be.activo = 1
              AND (
                    LTRIM(RTRIM(be.bloque)) = rf.bloque
                    -- La asignacion historica 'F1 - F2' habilita F1 y F2 por separado.
                 OR (LTRIM(RTRIM(be.bloque)) = 'F1 - F2' AND rf.bloque IN ('F1', 'F2'))
              )
        )
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
            WHEN 'F1' THEN 6
            WHEN 'F2' THEN 7
            WHEN 'F3' THEN 8
            WHEN 'F4' THEN 9
            WHEN 'TOTAL F1 - F4' THEN 10
            ELSE 11
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
                "bloques_activos": active_blocks.get(_executive_key(row.get("ejecutivo")), []),
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
    sql_zonas = f"""
    SELECT DISTINCT {_zona_sql("zona")} AS valor
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
