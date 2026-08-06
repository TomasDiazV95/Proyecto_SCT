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
    WITH porcentajes_manual AS (
        SELECT CAST('2026-04-01' AS DATE) AS periodo, 'Daniela Cañicul' AS ejecutivo, '6 a 30' AS bucket, CAST(24.58 AS DECIMAL(10, 2)) AS porcentaje
        UNION ALL
        SELECT CAST('2026-05-01' AS DATE), 'Luis Toledo', '6 a 30', CAST(26.39 AS DECIMAL(10, 2))
        UNION ALL
        SELECT CAST('2026-06-01' AS DATE), 'Erika Alderete', '6 a 30', CAST(24.16 AS DECIMAL(10, 2))
        UNION ALL
        SELECT CAST('2026-07-01' AS DATE), 'Erika Alderete', '6 a 30', CAST(14.44 AS DECIMAL(10, 2))
    ),
    asig AS (
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

            ISNULL(
                pm.porcentaje,
                CAST(
                    (SUM(CASE WHEN base.normalizado = 1 THEN base.deuda ELSE 0 END) * 100.0)
                    / NULLIF(SUM(base.deuda), 0)
                AS DECIMAL(10, 2))
            ) AS porcentaje_normalizado

        FROM asig base
        LEFT JOIN porcentajes_manual pm
            ON pm.periodo = ?
        AND pm.ejecutivo = base.ejecutivo
        AND pm.bucket = base.bucket
        WHERE base.bucket IN ('6 a 30', '31 a 60', '61 a 90', '91 a 150')
        {extra_clause}
        GROUP BY 
            base.ejecutivo, 
            base.bucket,
            pm.porcentaje
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

    data_params = [periodo, periodo, periodo, periodo, periodo, periodo]
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


def get_bucket_view(filters: dict) -> list[dict]:
    cycle_rows = get_cycle_view({"periodo": filters.get("periodo"), "ejecutivo": ""})

    grouped: dict[str, dict] = {}
    for row in cycle_rows:
        bucket = row["bucket"]
        current = grouped.setdefault(
            bucket,
            {
                "bucket": bucket,
                "deuda_asignada": 0.0,
                "saldo_contenido": 0.0,
                "saldo_normalizado": 0.0,
                "meta_contencion_pct": float(row.get("meta_contencion_pct") or 0),
                "meta_normalizacion_pct": float(row.get("meta_normalizacion_pct") or 0),
                "ponderador_contencion_pct": float(row.get("ponderador_contencion_pct") or 0),
                "ponderador_normalizacion_pct": float(row.get("ponderador_normalizacion_pct") or 0),
            },
        )
        current["deuda_asignada"] += float(row.get("deuda_asignada") or 0)
        current["saldo_contenido"] += float(row.get("saldo_contenido") or 0)
        current["saldo_normalizado"] += float(row.get("saldo_normalizado") or 0)

    response: list[dict] = []
    total_deuda = 0.0
    total_contenido = 0.0
    total_normalizado = 0.0
    total_ponderado = 0.0

    for bucket in BUCKET_ORDER:
        item = grouped.get(bucket)
        if not item:
            continue

        deuda = item["deuda_asignada"]
        contenido = item["saldo_contenido"]
        normalizado = item["saldo_normalizado"]
        pct_cont = _safe_div(contenido, deuda)
        pct_norm = _safe_div(normalizado, deuda)
        meta_cont = float(item["meta_contencion_pct"])
        meta_norm = float(item["meta_normalizacion_pct"])
        pond_cont = float(item["ponderador_contencion_pct"])
        pond_norm = float(item["ponderador_normalizacion_pct"])

        cumpl_cont = _cumpl_variable(pct_cont, meta_cont)
        cumpl_norm = _cumpl_variable(pct_norm, meta_norm)
        cumplimiento = _cap((cumpl_cont * (pond_cont / 100.0)) + (cumpl_norm * (pond_norm / 100.0)))

        response.append(
            {
                "bucket": bucket,
                "deuda_asignada": deuda,
                "saldo_contenido": contenido,
                "porcentaje_contencion": pct_cont,
                "saldo_normalizado": normalizado,
                "porcentaje_normalizado": pct_norm,
                "meta_contencion_pct": meta_cont,
                "meta_normalizacion_pct": meta_norm,
                "ponderador_contencion_pct": pond_cont,
                "ponderador_normalizacion_pct": pond_norm,
                "cumplimiento_final": cumplimiento,
            }
        )

        total_deuda += deuda
        total_contenido += contenido
        total_normalizado += normalizado
        total_ponderado += cumplimiento * deuda

    response.append(
        {
            "bucket": "Total general",
            "deuda_asignada": total_deuda,
            "saldo_contenido": total_contenido,
            "porcentaje_contencion": _safe_div(total_contenido, total_deuda),
            "saldo_normalizado": total_normalizado,
            "porcentaje_normalizado": _safe_div(total_normalizado, total_deuda),
            "meta_contencion_pct": 0.0,
            "meta_normalizacion_pct": 0.0,
            "ponderador_contencion_pct": 0.0,
            "ponderador_normalizacion_pct": 0.0,
            "cumplimiento_final": (total_ponderado / total_deuda) if total_deuda else 0.0,
        }
    )

    return response


def get_detail_view(filters: dict) -> list[dict]:
    periodo = _period_start(filters.get("periodo"))
    op = _clean_text(filters.get("op"))
    bucket = _clean_text(filters.get("bucket"))
    ejecutivo = _clean_text(filters.get("ejecutivo"))
    contenido = _clean_text(filters.get("contenido"))
    normalizado = _clean_text(filters.get("normalizado"))

    where_clauses = []
    params: list = [periodo, periodo, periodo, periodo, periodo, periodo, periodo]

    if op:
        where_clauses.append("CAST(base.op AS VARCHAR(100)) LIKE ?")
        params.append(f"%{op}%")
    if bucket:
        where_clauses.append("base.bucket = ?")
        params.append(bucket)
    if ejecutivo:
        where_clauses.append("base.ejecutivo = ?")
        params.append(ejecutivo)
    if contenido in {"0", "1"}:
        where_clauses.append("base.contenido = ?")
        params.append(int(contenido))
    if normalizado in {"0", "1"}:
        where_clauses.append("base.normalizado = ?")
        params.append(int(normalizado))

    extra_where = ""
    if where_clauses:
        extra_where = "WHERE " + " AND ".join(where_clauses)

    sql = f"""
    WITH mejor_gestion AS (
        SELECT
            nroDocumento,
            UsuarioGestion,
            ContactoGestion,
            RespuestaGestion,
            GestionFecha,
            GestionHora,
            telefono
        FROM (
            SELECT
                nroDocumento,
                UsuarioGestion,
                ContactoGestion,
                RespuestaGestion,
                GestionFecha,
                GestionHora,
                telefono,
                ROW_NUMBER() OVER (
                    PARTITION BY nroDocumento
                    ORDER BY
                        CASE RespuestaGestion
                            WHEN 'COMPROMISO DE PAGO' THEN 1
                            WHEN 'SOLICITA CUPON' THEN 2
                            WHEN 'RENEGOCIACION' THEN 3
                            WHEN 'PREPAGO DE DEUDA' THEN 4
                            WHEN 'DACION' THEN 5
                            WHEN 'EXTENSION' THEN 6
                            WHEN 'SEGURO EN TRAMITE' THEN 7
                            WHEN 'CONSULTA ALTERNATIVAS DE PAGO' THEN 8
                            WHEN 'CONSULTA LUGAR DE PAGO' THEN 9
                            WHEN 'YA PAGO' THEN 10
                            WHEN 'OLVIDO' THEN 11
                            WHEN 'GESTION ADMINISTRATIVA' THEN 12
                            WHEN 'CONSULTA DEUDA' THEN 13
                            WHEN 'ANULACION DE CONVENIO' THEN 14
                            WHEN 'RECLAMO' THEN 15
                            WHEN 'VENCIMIENTO NO LE ACOMODA' THEN 16
                            WHEN 'PROBLEMAS ECONOMICOS' THEN 17
                            WHEN 'PROBLEMAS DE SALUD' THEN 18
                            WHEN 'COMPRA DE TERCEROS' THEN 19
                            WHEN 'PROBLEMA EN LA VENTA' THEN 20
                            WHEN 'ESTAFA O APERTURA FRAUDULENTA' THEN 21
                            WHEN 'SIN INTENCION DE PAGO' THEN 22
                            WHEN 'DESCONOCE DEUDA' THEN 23
                            WHEN 'CESANTE' THEN 24
                            WHEN 'NO ENTREGA INFORMACION' THEN 25
                            WHEN 'CLIENTE COLGO' THEN 26
                            ELSE 999
                        END ASC,
                        GestionFecha DESC,
                        GestionHora DESC
                ) AS rn
            FROM dbo.tmp_GEST_CRM
            WHERE cartera = 520
              AND GestionFecha BETWEEN ? AND EOMONTH(?)
              AND ContactoGestion = 'CONTACTO_VALIDO'
        ) x
        WHERE rn = 1
    ),
    base AS (
        SELECT
            t.[fld_Agreement Number] AS op,
            LTRIM(RTRIM(t.fld_bucket)) AS bucket,
            t.fld_DPD AS dias_de_mora,
            CAST(t.[fld_POS/Curr. Acc. Bal.* ] AS FLOAT) AS deuda,
            t.fld_EMI AS cuota,
            ISNULL(c.ejecutivo, 'Phoenix') AS ejecutivo,
            ISNULL(p.contenido, 0) AS contenido,
            ISNULL(p.normalizado, 0) AS normalizado,
            ISNULL(mg.telefono, '') AS telefono_gestion
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
        LEFT JOIN mejor_gestion mg
            ON t.[fld_Agreement Number] = mg.nroDocumento
        WHERE t.rn = 1
    ),
    enriched AS (
        SELECT
            base.*,
            CAST(
                base.deuda * 100.0 / NULLIF(SUM(base.deuda) OVER (PARTITION BY base.bucket), 0)
                AS DECIMAL(18, 2)
            ) AS peso_bucket_pct
        FROM base
    )
    SELECT
        base.op,
        base.bucket,
        base.dias_de_mora,
        base.deuda,
        base.peso_bucket_pct,
        base.cuota,
        base.ejecutivo,
        base.contenido,
        base.normalizado,
        base.telefono_gestion
    FROM enriched base
    {extra_where}
    ORDER BY
        CASE
            WHEN base.bucket = '6 a 30' THEN 1
            WHEN base.bucket = '31 a 60' THEN 2
            WHEN base.bucket = '61 a 90' THEN 3
            WHEN base.bucket = '91 a 150' THEN 4
            ELSE 99
        END,
        base.op
    """

    rows = []
    for row in run_query(sql, tuple(params)):
        rows.append(
            {
                "periodo": periodo,
                "op": row.get("op"),
                "bucket": row.get("bucket") or "",
                "dias_de_mora": row.get("dias_de_mora"),
                "deuda": float(row.get("deuda") or 0),
                "peso_bucket_pct": float(row.get("peso_bucket_pct") or 0),
                "cuota": float(row.get("cuota") or 0),
                "ejecutivo": row.get("ejecutivo") or "Phoenix",
                "contenido": int(row.get("contenido") or 0),
                "normalizado": int(row.get("normalizado") or 0),
                "telefono_gestion": row.get("telefono_gestion") or "",
            }
        )

    return rows


def get_monthly_export_rows(periodo: str | None) -> tuple[str, list[dict]]:
    periodo_base = _period_start(periodo)

    sql = """
    WITH mejor_gestion AS (
        SELECT
            nroDocumento,
            UsuarioGestion,
            ContactoGestion,
            RespuestaGestion,
            GestionFecha,
            GestionHora,
            telefono
        FROM (
            SELECT
                nroDocumento,
                UsuarioGestion,
                ContactoGestion,
                RespuestaGestion,
                GestionFecha,
                GestionHora,
                telefono,
                ROW_NUMBER() OVER (
                    PARTITION BY nroDocumento
                    ORDER BY
                        CASE RespuestaGestion
                            WHEN 'COMPROMISO DE PAGO' THEN 1
                            WHEN 'SOLICITA CUPON' THEN 2
                            WHEN 'RENEGOCIACION' THEN 3
                            WHEN 'PREPAGO DE DEUDA' THEN 4
                            WHEN 'DACION' THEN 5
                            WHEN 'EXTENSION' THEN 6
                            WHEN 'SEGURO EN TRAMITE' THEN 7
                            WHEN 'CONSULTA ALTERNATIVAS DE PAGO' THEN 8
                            WHEN 'CONSULTA LUGAR DE PAGO' THEN 9
                            WHEN 'YA PAGO' THEN 10
                            WHEN 'OLVIDO' THEN 11
                            WHEN 'GESTION ADMINISTRATIVA' THEN 12
                            WHEN 'CONSULTA DEUDA' THEN 13
                            WHEN 'ANULACION DE CONVENIO' THEN 14
                            WHEN 'RECLAMO' THEN 15
                            WHEN 'VENCIMIENTO NO LE ACOMODA' THEN 16
                            WHEN 'PROBLEMAS ECONOMICOS' THEN 17
                            WHEN 'PROBLEMAS DE SALUD' THEN 18
                            WHEN 'COMPRA DE TERCEROS' THEN 19
                            WHEN 'PROBLEMA EN LA VENTA' THEN 20
                            WHEN 'ESTAFA O APERTURA FRAUDULENTA' THEN 21
                            WHEN 'SIN INTENCION DE PAGO' THEN 22
                            WHEN 'DESCONOCE DEUDA' THEN 23
                            WHEN 'CESANTE' THEN 24
                            WHEN 'NO ENTREGA INFORMACION' THEN 25
                            WHEN 'CLIENTE COLGO' THEN 26
                            ELSE 999
                        END ASC,
                        GestionFecha DESC,
                        GestionHora DESC
                ) AS rn
            FROM tmp_GEST_CRM
            WHERE cartera = 520
            AND GestionFecha BETWEEN ? AND EOMONTH(?)
            AND ContactoGestion = 'CONTACTO_VALIDO'
        ) x
        WHERE rn = 1
    )

    SELECT 
        t.[fld_Agreement Number] AS op,
        t.[fld_National Id] AS rut,
        t.[fld_Customer Name] AS nombre,
        t.fld_bucket AS bucket,
        t.fld_DPD AS dias_de_mora,
        t.[fld_POS/Curr. Acc. Bal.* ] AS deuda,
        t.fld_EMI AS cuota,
        ISNULL(c.ejecutivo, 'Phoenix') AS ejecutivo,
        ISNULL(p.contenido, 0) AS contenido,
        ISNULL(p.normalizado, 0) AS normalizado,

        ISNULL(mg.UsuarioGestion, '') AS UsuarioGestion,
        ISNULL(mg.ContactoGestion, '') AS ContactoGestion,
        ISNULL(mg.RespuestaGestion, '') AS RespuestaGestion,
        ISNULL(CONVERT(VARCHAR(10), mg.GestionFecha, 120), '') AS GestionFecha,
        ISNULL(CONVERT(VARCHAR(8), mg.GestionHora, 108), '') AS GestionHora,
        ISNULL(mg.telefono, '') AS telefono_gestion

    FROM (
        SELECT *,
            ROW_NUMBER() OVER (
                PARTITION BY [fld_Agreement Number]
                ORDER BY fecha_carga ASC
            ) AS rn
        FROM tmp_asig_GM
        WHERE fecha_carga BETWEEN ? AND EOMONTH(?)
    ) t

    LEFT JOIN tmp_carterizado_GM c
        ON t.[fld_Agreement Number] = c.op
    AND c.mes_carterizado = ?

    LEFT JOIN (
        SELECT 
            operacion,
            MAX(CAST(contenido AS INT)) AS contenido,
            MAX(CAST(normalizado AS INT)) AS normalizado
        FROM tmp_pagos_gm
        WHERE periodo_pago BETWEEN ? AND EOMONTH(?)
        GROUP BY operacion
    ) p
        ON t.[fld_Agreement Number] = p.operacion

    LEFT JOIN mejor_gestion mg
        ON t.[fld_Agreement Number] = mg.nroDocumento

    WHERE t.rn = 1
    ORDER BY bucket, ejecutivo, op
    """

    rows = run_query(sql, (periodo_base, periodo_base, periodo_base, periodo_base, periodo_base, periodo_base, periodo_base))
    return periodo_base, rows
