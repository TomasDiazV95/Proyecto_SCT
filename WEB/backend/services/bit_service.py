from database import run_query


BIT_DATA_CTE = """
WITH carterizado_unico AS (
    SELECT
        periodo,
        operation_key,
        usuario,
        ROW_NUMBER() OVER (
            PARTITION BY periodo, operation_key
            ORDER BY id ASC
        ) AS rn
    FROM (
        SELECT
            periodo,
            usuario,
            CASE
                WHEN LTRIM(RTRIM(COALESCE(nro_operacion, ''))) <> ''
                 AND LTRIM(RTRIM(COALESCE(nro_operacion, ''))) NOT LIKE '%[^0-9]%'
                    THEN CAST(CAST(LTRIM(RTRIM(nro_operacion)) AS BIGINT) AS VARCHAR(50))
                ELSE UPPER(LTRIM(RTRIM(COALESCE(nro_operacion, ''))))
            END AS operation_key,
            id
        FROM dbo.tmp_BIT_carterizado
    ) src
), dotacion AS (
    SELECT
        UPPER(LTRIM(RTRIM(usuario_ejecutivo))) AS usuario,
        nombre_ejecutivo,
        periodo_desde,
        periodo_hasta
    FROM dbo.tmp_ejecutivos
    WHERE cartera = 532
), metas AS (
    SELECT periodo, tramo, meta
    FROM (
        SELECT
            periodo,
            CASE
                WHEN tramo IN ('30-89', '30-90') THEN '30-90'
                ELSE tramo
            END AS tramo,
            meta,
            ROW_NUMBER() OVER (
                PARTITION BY periodo, CASE WHEN tramo IN ('30-89', '30-90') THEN '30-90' ELSE tramo END
                ORDER BY CASE WHEN tramo = '30-90' THEN 1 ELSE 2 END
            ) AS rn
        FROM dbo.tmp_BIT_metas
    ) src
    WHERE rn = 1
), bit_data AS (
    SELECT
        c.periodo,
        c.rut,
        c.dv,
        c.con_no,
        COALESCE(cu.usuario, 'Phoenix') AS carterizado,
        COALESCE(d.nombre_ejecutivo, 'Phoenix') AS ejecutivo,
        CASE
            WHEN LEFT(COALESCE(c.tramo_proyectado_nuevo, ''), 2) IN ('T1', 'T2', 'T3') THEN '30-90'
            WHEN LEFT(COALESCE(c.tramo_proyectado_nuevo, ''), 2) IN ('T4', 'T5', 'T6', 'T7') THEN '90+'
            ELSE ''
        END AS tramo,
        m.meta,
        CASE WHEN m.meta IS NULL THEN 0 ELSE ISNULL(c.total, 0) * m.meta END AS meta_final,
        ISNULL(c.total, 0) AS mto_inicial,
        ISNULL(c.mto_contiene, 0) AS mto_contenido,
        ISNULL(c.contiene, 0) AS contiene,
        c.tipo_cont
    FROM dbo.tmp_BIT_contencion c
    LEFT JOIN carterizado_unico cu
        ON cu.periodo = c.periodo
       AND cu.operation_key = CASE
            WHEN LTRIM(RTRIM(COALESCE(c.con_no, ''))) <> ''
             AND LTRIM(RTRIM(COALESCE(c.con_no, ''))) NOT LIKE '%[^0-9]%'
                THEN CAST(CAST(LTRIM(RTRIM(c.con_no)) AS BIGINT) AS VARCHAR(50))
            ELSE UPPER(LTRIM(RTRIM(COALESCE(c.con_no, ''))))
        END
       AND cu.rn = 1
    LEFT JOIN dotacion d
        ON d.usuario = UPPER(LTRIM(RTRIM(COALESCE(cu.usuario, 'Phoenix'))))
       AND (
            d.periodo_desde IS NULL
            OR d.periodo_desde <= EOMONTH(DATEFROMPARTS(CAST(LEFT(c.periodo, 4) AS INT), CAST(RIGHT(c.periodo, 2) AS INT), 1))
       )
       AND (
            d.periodo_hasta IS NULL
            OR d.periodo_hasta >= DATEFROMPARTS(CAST(LEFT(c.periodo, 4) AS INT), CAST(RIGHT(c.periodo, 2) AS INT), 1)
       )
    LEFT JOIN metas m
        ON m.periodo = c.periodo
       AND m.tramo = CASE
            WHEN LEFT(COALESCE(c.tramo_proyectado_nuevo, ''), 2) IN ('T1', 'T2', 'T3') THEN '30-90'
            WHEN LEFT(COALESCE(c.tramo_proyectado_nuevo, ''), 2) IN ('T4', 'T5', 'T6', 'T7') THEN '90+'
            ELSE ''
        END
    WHERE UPPER(LTRIM(RTRIM(COALESCE(c.cartera, '')))) <> 'UNIVERSITARIOS'
)
"""

BIT_DATA_CTE_TRAMOS = """
WITH carterizado_unico AS (
    SELECT
        periodo,
        operation_key,
        usuario,
        ROW_NUMBER() OVER (
            PARTITION BY periodo, operation_key
            ORDER BY id ASC
        ) AS rn
    FROM (
        SELECT
            periodo,
            usuario,
            CASE
                WHEN LTRIM(RTRIM(COALESCE(nro_operacion, ''))) <> ''
                 AND LTRIM(RTRIM(COALESCE(nro_operacion, ''))) NOT LIKE '%[^0-9]%'
                    THEN CAST(CAST(LTRIM(RTRIM(nro_operacion)) AS BIGINT) AS VARCHAR(50))
                ELSE UPPER(LTRIM(RTRIM(COALESCE(nro_operacion, ''))))
            END AS operation_key,
            id
        FROM dbo.tmp_BIT_carterizado
    ) src
), dotacion AS (
    SELECT
        UPPER(LTRIM(RTRIM(usuario_ejecutivo))) AS usuario,
        nombre_ejecutivo,
        periodo_desde,
        periodo_hasta
    FROM dbo.tmp_ejecutivos
    WHERE cartera = 532
), metas AS (
    SELECT periodo, tramo, meta
    FROM (
        SELECT
            periodo,
            CASE
                WHEN tramo IN ('30-89', '30-90') THEN '30-90'
                ELSE tramo
            END AS tramo,
            meta,
            ROW_NUMBER() OVER (
                PARTITION BY periodo, CASE WHEN tramo IN ('30-89', '30-90') THEN '30-90' ELSE tramo END
                ORDER BY CASE WHEN tramo = '30-90' THEN 1 ELSE 2 END
            ) AS rn
        FROM dbo.tmp_BIT_metas
    ) src
    WHERE rn = 1
), bit_data AS (
    SELECT
        c.periodo,
        c.rut,
        c.dv,
        c.con_no,
        COALESCE(cu.usuario, 'Phoenix') AS carterizado,
        COALESCE(d.nombre_ejecutivo, 'Phoenix') AS ejecutivo,
        CASE
            WHEN LEFT(COALESCE(c.tramo_proyectado_nuevo, ''), 2) IN ('T1', 'T2', 'T3') THEN '30-90'
            WHEN LEFT(COALESCE(c.tramo_proyectado_nuevo, ''), 2) IN ('T4', 'T5', 'T6', 'T7') THEN '90+'
            ELSE ''
        END AS tramo,
        m.meta,
        CASE WHEN m.meta IS NULL THEN 0 ELSE ISNULL(c.total, 0) * m.meta END AS meta_final,
        ISNULL(c.total, 0) AS mto_inicial,
        ISNULL(c.mto_contiene, 0) AS mto_contenido,
        ISNULL(c.contiene, 0) AS contiene,
        c.tipo_cont
    FROM dbo.tmp_BIT_contencion c
    LEFT JOIN carterizado_unico cu
        ON cu.periodo = c.periodo
       AND cu.operation_key = CASE
            WHEN LTRIM(RTRIM(COALESCE(c.con_no, ''))) <> ''
             AND LTRIM(RTRIM(COALESCE(c.con_no, ''))) NOT LIKE '%[^0-9]%'
                THEN CAST(CAST(LTRIM(RTRIM(c.con_no)) AS BIGINT) AS VARCHAR(50))
            ELSE UPPER(LTRIM(RTRIM(COALESCE(c.con_no, ''))))
        END
       AND cu.rn = 1
    LEFT JOIN dotacion d
        ON d.usuario = UPPER(LTRIM(RTRIM(COALESCE(cu.usuario, 'Phoenix'))))
       AND (
            d.periodo_desde IS NULL
            OR d.periodo_desde <= EOMONTH(DATEFROMPARTS(CAST(LEFT(c.periodo, 4) AS INT), CAST(RIGHT(c.periodo, 2) AS INT), 1))
       )
       AND (
            d.periodo_hasta IS NULL
            OR d.periodo_hasta >= DATEFROMPARTS(CAST(LEFT(c.periodo, 4) AS INT), CAST(RIGHT(c.periodo, 2) AS INT), 1)
       )
    LEFT JOIN metas m
        ON m.periodo = c.periodo
       AND m.tramo = CASE
            WHEN LEFT(COALESCE(c.tramo_proyectado_nuevo, ''), 2) IN ('T1', 'T2', 'T3') THEN '30-90'
            WHEN LEFT(COALESCE(c.tramo_proyectado_nuevo, ''), 2) IN ('T4', 'T5', 'T6', 'T7') THEN '90+'
            ELSE ''
        END
)
"""


def _safe_div(num: float, den: float) -> float:
    if den is None or den == 0:
        return 0.0
    return num / den


def _safe_avg(values: list[float]) -> float:
    clean = [float(value) for value in values if value is not None]
    if not clean:
        return 0.0
    return sum(clean) / len(clean)


def _get_contencion_source_file(periodo: str) -> str:
    rows = run_query(
        """
        SELECT TOP 1 source_file
        FROM dbo.tmp_BIT_contencion
        WHERE periodo = ? AND source_file IS NOT NULL AND LTRIM(RTRIM(source_file)) <> ''
          AND UPPER(LTRIM(RTRIM(COALESCE(cartera, '')))) <> 'UNIVERSITARIOS'
        GROUP BY source_file
        ORDER BY COUNT(1) DESC, source_file DESC
        """,
        (periodo,),
    )
    if not rows:
        return ""
    return str(rows[0].get("source_file") or "")


def _base_where(filters: dict) -> tuple[str, list]:
    clauses = ["periodo = ?"]
    params: list = [str(filters.get("periodo") or "").strip()]

    ejecutivo = str(filters.get("ejecutivo") or "").strip()
    if ejecutivo:
        clauses.append("UPPER(LTRIM(RTRIM(ejecutivo))) = UPPER(LTRIM(RTRIM(?)))")
        params.append(ejecutivo)

    tramo = str(filters.get("tramo") or "").strip()
    if tramo:
        clauses.append("UPPER(LTRIM(RTRIM(tramo))) = UPPER(LTRIM(RTRIM(?)))")
        params.append(tramo)

    return " AND ".join(clauses), params


def get_filter_values() -> dict:
    periodos = [
        r["v"]
        for r in run_query(
            """
            SELECT DISTINCT periodo AS v
            FROM dbo.tmp_BIT_contencion
            WHERE periodo IS NOT NULL
              AND UPPER(LTRIM(RTRIM(COALESCE(cartera, '')))) <> 'UNIVERSITARIOS'
            ORDER BY v DESC
            """
        )
        if r.get("v")
    ]
    ejecutivos = [
        r["v"]
        for r in run_query(
            f"""
            {BIT_DATA_CTE}
            SELECT DISTINCT LTRIM(RTRIM(ejecutivo)) AS v
            FROM bit_data
            WHERE ejecutivo IS NOT NULL AND LTRIM(RTRIM(ejecutivo)) <> ''
            ORDER BY v
            """
        )
        if r.get("v")
    ]
    tramos = [
        r["v"]
        for r in run_query(
            """
            SELECT v
            FROM (
                SELECT
                    CASE
                        WHEN LEFT(COALESCE(tramo_proyectado_nuevo, ''), 2) IN ('T1', 'T2', 'T3') THEN '30-90'
                        WHEN LEFT(COALESCE(tramo_proyectado_nuevo, ''), 2) IN ('T4', 'T5', 'T6', 'T7') THEN '90+'
                        ELSE ''
                    END AS v,
                    MIN(CASE
                        WHEN LEFT(COALESCE(tramo_proyectado_nuevo, ''), 2) IN ('T1', 'T2', 'T3') THEN 1
                        WHEN LEFT(COALESCE(tramo_proyectado_nuevo, ''), 2) IN ('T4', 'T5', 'T6', 'T7') THEN 2
                        ELSE 99
                    END) AS ord
                FROM dbo.tmp_BIT_contencion
                WHERE UPPER(LTRIM(RTRIM(COALESCE(cartera, '')))) <> 'UNIVERSITARIOS'
                GROUP BY CASE
                    WHEN LEFT(COALESCE(tramo_proyectado_nuevo, ''), 2) IN ('T1', 'T2', 'T3') THEN '30-90'
                    WHEN LEFT(COALESCE(tramo_proyectado_nuevo, ''), 2) IN ('T4', 'T5', 'T6', 'T7') THEN '90+'
                    ELSE ''
                END
            ) t
            WHERE v <> ''
            ORDER BY ord, v
            """
        )
        if r.get("v")
    ]
    return {"periodos": periodos, "ejecutivos": ejecutivos, "tramos": tramos}


def get_general(filters: dict) -> dict:
    periodo = str(filters.get("periodo") or "").strip()
    where_sql, params = _base_where(filters)
    where_sql = f"{where_sql} AND LTRIM(RTRIM(COALESCE(tramo, ''))) <> ''"
    sql = f"""
    {BIT_DATA_CTE}
    SELECT
        ejecutivo,
        tramo,
        SUM(COALESCE(CAST(mto_inicial AS float), 0)) AS monto_inicial,
        SUM(COALESCE(CAST(mto_contenido AS float), 0)) AS monto_contenido,
        SUM(COALESCE(CAST(meta_final AS float), 0)) AS meta_final
    FROM bit_data
    WHERE {where_sql}
    GROUP BY ejecutivo, tramo
    ORDER BY CASE WHEN ejecutivo = 'Phoenix' THEN 2 ELSE 1 END, ejecutivo,
             CASE WHEN tramo = '30-90' THEN 1 WHEN tramo = '90+' THEN 2 ELSE 99 END, tramo
    """
    agg_rows = run_query(sql, tuple(params))

    rows: list[dict] = []
    total_inicial = 0.0
    total_contenido = 0.0
    total_meta = 0.0
    pct_cumpl_meta_values: list[float] = []
    for r in agg_rows:
        monto_inicial = float(r.get("monto_inicial") or 0)
        monto_contenido = float(r.get("monto_contenido") or 0)
        meta_final = float(r.get("meta_final") or 0)
        pct_contencion = _safe_div(monto_contenido, monto_inicial)
        pct_cumpl_meta = _safe_div(monto_contenido, meta_final)
        rows.append(
            {
                "ejecutivo": r.get("ejecutivo") or "Phoenix",
                "tramo": r.get("tramo") or "",
                "monto_inicial": monto_inicial,
                "monto_contenido": monto_contenido,
                "pct_contencion": pct_contencion,
                "pct_contiene": pct_contencion,
                "pct_cumpl_meta": pct_cumpl_meta,
            }
        )
        total_inicial += monto_inicial
        total_contenido += monto_contenido
        total_meta += meta_final
        pct_cumpl_meta_values.append(pct_cumpl_meta)

    return {
        "periodo": periodo,
        "contencion_file": _get_contencion_source_file(periodo),
        "rows": rows,
        "total": {
            "ejecutivo": "Total general",
            "tramo": "",
            "monto_inicial": total_inicial,
            "monto_contenido": total_contenido,
            "pct_contencion": _safe_div(total_contenido, total_inicial),
            "pct_contiene": _safe_div(total_contenido, total_inicial),
            "pct_cumpl_meta": _safe_avg(pct_cumpl_meta_values),
        },
    }


def get_tramos(filters: dict) -> dict:
    periodo = str(filters.get("periodo") or "").strip()
    where_sql, params = _base_where(filters)
    sql = f"""
    {BIT_DATA_CTE_TRAMOS}
    SELECT
        tramo,
        SUM(COALESCE(CAST(mto_inicial AS float), 0)) AS monto_inicial,
        SUM(COALESCE(CAST(mto_contenido AS float), 0)) AS monto_contenido,
        SUM(COALESCE(CAST(meta_final AS float), 0)) AS meta_final
    FROM bit_data
    WHERE {where_sql}
      AND LTRIM(RTRIM(COALESCE(tramo, ''))) <> ''
    GROUP BY tramo
    ORDER BY CASE WHEN tramo = '30-90' THEN 1 WHEN tramo = '90+' THEN 2 ELSE 99 END, tramo
    """
    agg_rows = run_query(sql, tuple(params))

    rows: list[dict] = []
    total_inicial = 0.0
    total_contenido = 0.0
    total_meta = 0.0
    pct_cumpl_meta_values: list[float] = []
    for r in agg_rows:
        monto_inicial = float(r.get("monto_inicial") or 0)
        monto_contenido = float(r.get("monto_contenido") or 0)
        meta_final = float(r.get("meta_final") or 0)
        pct_contencion = _safe_div(monto_contenido, monto_inicial)
        pct_cumpl_meta = _safe_div(monto_contenido, meta_final)
        rows.append(
            {
                "tramo": r.get("tramo") or "",
                "monto_inicial": monto_inicial,
                "monto_contenido": monto_contenido,
                "pct_contencion": pct_contencion,
                "pct_contiene": pct_contencion,
                "pct_cumpl_meta": pct_cumpl_meta,
            }
        )
        total_inicial += monto_inicial
        total_contenido += monto_contenido
        total_meta += meta_final
        pct_cumpl_meta_values.append(pct_cumpl_meta)

    return {
        "periodo": periodo,
        "contencion_file": _get_contencion_source_file(periodo),
        "rows": rows,
        "total": {
            "tramo": "Total general",
            "monto_inicial": total_inicial,
            "monto_contenido": total_contenido,
            "pct_contencion": _safe_div(total_contenido, total_inicial),
            "pct_contiene": _safe_div(total_contenido, total_inicial),
            "pct_cumpl_meta": _safe_avg(pct_cumpl_meta_values),
        },
    }


def get_detalle(filters: dict) -> dict:
    where_sql, params = _base_where(filters)
    sql = f"""
    {BIT_DATA_CTE}
    SELECT
        periodo,
        rut,
        dv,
        con_no,
        carterizado,
        ejecutivo,
        tramo,
        COALESCE(CAST(meta AS float), 0) AS meta,
        COALESCE(CAST(meta_final AS float), 0) AS meta_final,
        COALESCE(CAST(mto_inicial AS float), 0) AS mto_inicial,
        COALESCE(CAST(mto_contenido AS float), 0) AS mto_contenido,
        COALESCE(CAST(contiene AS int), 0) AS contiene,
        tipo_cont
    FROM bit_data
    WHERE {where_sql}
    ORDER BY ejecutivo, tramo, con_no
    """
    rows = run_query(sql, tuple(params))
    return {"periodo": str(filters.get("periodo") or "").strip(), "rows": rows}
