import re
from datetime import datetime, timedelta

from database import run_query


ASIGNACION_TABLE = "dbo.tmp_LA_asignacion"
PAGOS_TABLE = "dbo.tmp_LA_pagos"
GESTION_TABLE = "dbo.tmp_GEST_CRM"
EJECUTIVOS_TABLE = "dbo.tmp_ejecutivos"


def _columns(table_name: str) -> set[str]:
    schema, table = table_name.split(".", 1)
    sql = """
    SELECT c.name
    FROM sys.columns c
    INNER JOIN sys.tables t ON c.object_id = t.object_id
    INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
    WHERE s.name = ? AND t.name = ?
    """
    rows = run_query(sql, (schema, table))
    return {r["name"] for r in rows}


def _pick(available: set[str], candidates: list[str], label: str) -> str:
    for c in candidates:
        if c in available:
            return c
    raise RuntimeError(f"No se encontro columna para {label}: {candidates}")


def _pick_optional(available: set[str], candidates: list[str]) -> str | None:
    for c in candidates:
        if c in available:
            return c
    return None


def _parse_period(periodo: str) -> tuple[str, str, str, str, str]:
    value = (periodo or "").strip()
    if not value:
        raise RuntimeError("periodo es obligatorio")

    dt = None
    for fmt in ("%Y-%m", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            dt = datetime.strptime(value, fmt)
            break
        except ValueError:
            continue

    if dt is None:
        raise RuntimeError(f"Formato de periodo no soportado: {periodo}")

    month_start = dt.replace(day=1)
    if len(value) <= 7:
        # Compatibilidad: si viene YYYY-MM, el fin es cierre de mes.
        next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
        month_end = next_month - timedelta(days=1)
    else:
        # Fecha exacta de corte YYYY-MM-DD.
        month_end = dt

    period_month = month_start.strftime("%Y-%m")
    asignacion_file = f"ASIGNACION_{period_month}.csv"
    recuperacion_file = f"RECUPERACION_{period_month}.csv"
    period_day = month_end.strftime("%Y-%m-%d")
    return period_month, period_day, month_start.strftime("%Y-%m-%d"), month_end.strftime("%Y-%m-%d"), asignacion_file + "|" + recuperacion_file


def _source_file_like_values(file_name: str, period_month: str) -> list[str]:
    compact = period_month.replace("-", "")
    return [f"%{file_name}%", f"%{compact}%"]


def _norm_payment_expr(col: str) -> str:
    return f"REPLACE(REPLACE(UPPER(LTRIM(RTRIM(CONVERT(varchar(100), {col})))), N'–', '-'), ' ', '')"


def _resolved_cols() -> dict:
    a = _columns(ASIGNACION_TABLE)
    p = _columns(PAGOS_TABLE)
    g = _columns(GESTION_TABLE)
    e = _columns(EJECUTIVOS_TABLE)
    return {
        "periodo": _pick(a, ["fld_PERIODO", "fld_FECHA", "fecha_carga"], "periodo"),
        "folio": _pick(a, ["fld_FOLIO_CREDITO"], "folio"),
        "rut_asig": _pick(a, ["fld_RUT_ASIGNADO"], "rut asignado"),
        "tramo": _pick(a, ["fld_TRAMO_MORA"], "tramo"),
        "tipo_cartera": _pick(a, ["fld_TIPO_CARTERA"], "tipo cartera"),
        "segmento": _pick(a, ["fld_SEGMENTO"], "segmento"),
        "capital": _pick(a, ["fld_CAPITAL"], "capital"),
        "deuda": _pick(a, ["fld_TOTAL_DEUDA"], "deuda"),
        "source_file_asig": _pick_optional(a, ["source_file", "archivo_origen", "file_name"]),
        "contrato_pago": _pick(p, ["fld_CONTRATO"], "contrato pagos"),
        "recupero": _pick(p, ["fld_Recuperacion", "fld_RECUPERACION"], "recuperacion"),
        "tipo_pago": _pick(p, ["fld_TipoPago", "fld_TIPOPAGO"], "tipo pago"),
        "fecha_negocio_pago": _pick(p, ["fecha_negocio", "fld_FECHA_NEGOCIO", "fld_FechaNegocio"], "fecha negocio pagos"),
        "source_file_pago": _pick_optional(p, ["source_file", "archivo_origen", "file_name"]),
        "rut_gest": _pick(g, ["rut", "RUT"], "rut gestion"),
        "usuario_gest": _pick(g, ["UsuarioGestion"], "usuario gestion"),
        "contacto_gest": _pick(g, ["ContactoGestion"], "contacto gestion"),
        "resp_gest": _pick(g, ["RespuestaGestion"], "respuesta gestion"),
        "obs_gest": _pick(g, ["observaciones", "Observaciones"], "observaciones"),
        "fecha_gest": _pick(g, ["GestionFecha"], "fecha gestion"),
        "hora_gest": _pick(g, ["GestionHora"], "hora gestion"),
        "cartera_gest": _pick(g, ["Cartera", "cartera", "fld_CARTERA", "fld_cartera"], "cartera gestion"),
        "usuario_ej": _pick(e, ["usuario_ejecutivo"], "usuario ejecutivo"),
        "nombre_ej": _pick(e, ["nombre_ejecutivo"], "nombre ejecutivo"),
    }


def get_filtros() -> dict:
    c = _resolved_cols()
    periodos_raw = [
        r["v"]
        for r in run_query(
            f"SELECT DISTINCT CONVERT(varchar(50), {c['fecha_negocio_pago']}, 23) AS v FROM {PAGOS_TABLE} WHERE {c['fecha_negocio_pago']} IS NOT NULL ORDER BY v DESC"
        )
    ]
    periodos = sorted({str(v)[:7] for v in periodos_raw if v and len(str(v)) >= 7}, reverse=True)
    tipos = [
        r["v"]
        for r in run_query(
            f"""
            SELECT DISTINCT
                CASE
                    WHEN LTRIM(RTRIM(CONVERT(varchar(100), {c['tipo_cartera']}))) = '365' THEN '+365'
                    ELSE LTRIM(RTRIM(CONVERT(varchar(100), {c['tipo_cartera']})))
                END AS v
            FROM {ASIGNACION_TABLE}
            WHERE {c['tipo_cartera']} IS NOT NULL
            ORDER BY v
            """
        )
    ]
    return {
        "periodos": periodos,
        "carteras_crm": [531],
        "tipo_cartera": tipos,
    }


def get_resumen(filters: dict) -> dict:
    c = _resolved_cols()
    period_month, _period_day, month_start, month_end, file_tokens = _parse_period(str(filters.get("periodo") or ""))
    asignacion_file, recuperacion_file = file_tokens.split("|")
    payment_type = _norm_payment_expr(c["tipo_pago"])
    where = ["base.incluir_en_resumen = 1"]
    params: list = []

    if filters.get("tipo_cartera"):
        where.append("UPPER(LTRIM(RTRIM(base.tipo_cartera))) = UPPER(LTRIM(RTRIM(?)))")
        params.append(str(filters["tipo_cartera"]))
    if filters.get("ejecutivo"):
        where.append("UPPER(LTRIM(RTRIM(base.mejor_ejecutivo))) = UPPER(LTRIM(RTRIM(?)))")
        params.append(str(filters["ejecutivo"]))

    where_sql = " AND ".join(where)
    sql = f"""
    WITH pagos_validos_contrato AS (
        SELECT
            CONVERT(varchar(100), {c['contrato_pago']}) AS contrato,
            SUM(COALESCE(CAST({c['recupero']} AS float), 0)) AS recupero
        FROM {PAGOS_TABLE} p
        WHERE {payment_type} IN ('E-ACTSEGCES', 'E-MANUAL', 'E-INTER-CC', 'E-CC')
          AND CAST(p.{c['fecha_negocio_pago']} AS date) >= CAST(? AS date)
          AND CAST(p.{c['fecha_negocio_pago']} AS date) <= CAST(? AS date)
          {f"AND (UPPER(CONVERT(varchar(300), p.{c['source_file_pago']})) LIKE UPPER(?) OR UPPER(CONVERT(varchar(300), p.{c['source_file_pago']})) LIKE UPPER(?))" if c['source_file_pago'] else ""}
        GROUP BY CONVERT(varchar(100), {c['contrato_pago']})
    ),
    gestiones_531 AS (
        SELECT
            CONVERT(varchar(50), {c['rut_gest']}) AS rut,
            CONVERT(varchar(200), {c['usuario_gest']}) AS usuario,
            CONVERT(varchar(200), {c['contacto_gest']}) AS contacto,
            CONVERT(varchar(300), {c['resp_gest']}) AS respuesta,
            CONVERT(varchar(500), {c['obs_gest']}) AS observaciones,
            {c['fecha_gest']} AS fecha_gestion,
            CONVERT(varchar(50), {c['hora_gest']}) AS hora_gestion
        FROM {GESTION_TABLE}
        WHERE {c['cartera_gest']} = 531
          AND CAST({c['fecha_gest']} AS date) >= CAST(? AS date)
          AND CAST({c['fecha_gest']} AS date) <= CAST(? AS date)
    ),
    intensidad AS (
        SELECT rut, COUNT(*) AS intensidad
        FROM gestiones_531
        GROUP BY rut
    ),
    mejor_gestion AS (
        SELECT
            g.*,
            ROW_NUMBER() OVER (
                PARTITION BY g.rut
                ORDER BY
                    CASE UPPER(LTRIM(RTRIM(COALESCE(g.contacto, ''))))
                        WHEN 'CONTACTO DIRECTO' THEN 1
                        WHEN 'CONTACTO INDIRECTO' THEN 2
                        WHEN 'NO CONTACTADO' THEN 3
                        WHEN 'GESTION DISCADOR' THEN 4
                        ELSE 99
                    END ASC,
                    g.fecha_gestion DESC,
                    g.hora_gestion DESC
            ) AS rn
        FROM gestiones_531 g
    ),
    base AS (
        SELECT
            CONVERT(varchar(50), a.{c['periodo']}) AS periodo,
            CONVERT(varchar(100), a.{c['folio']}) AS folio,
            CONVERT(varchar(50), a.{c['rut_asig']}) AS rut_deudor,
            CONVERT(varchar(100), a.{c['tramo']}) AS tramo,
            CASE
                WHEN LTRIM(RTRIM(CONVERT(varchar(100), a.{c['tipo_cartera']}))) = '365' THEN '+365'
                ELSE LTRIM(RTRIM(CONVERT(varchar(100), a.{c['tipo_cartera']})))
            END AS tipo_cartera,
            CONVERT(varchar(100), a.{c['segmento']}) AS segmento,
            COALESCE(CAST(a.{c['deuda']} AS float), 0) AS deuda,
            COALESCE(CAST(p.recupero AS float), 0) AS recupero,
            COALESCE(i.intensidad, 0) AS intensidad,
            mg.usuario,
            CASE
                WHEN mg.usuario IS NULL OR LTRIM(RTRIM(mg.usuario)) = '' THEN NULL
                WHEN e.{c['nombre_ej']} IS NOT NULL THEN e.{c['nombre_ej']}
                ELSE 'SIN EJECUTIVO'
            END AS mejor_ejecutivo,
            CASE WHEN UPPER(LTRIM(RTRIM(COALESCE(mg.contacto, '')))) = 'CONTACTO DIRECTO' THEN 1 ELSE 0 END AS flag_titular,
            CASE WHEN mg.usuario IS NULL OR LTRIM(RTRIM(mg.usuario)) = '' THEN 0 ELSE 1 END AS incluir_en_resumen
        FROM {ASIGNACION_TABLE} a
        LEFT JOIN pagos_validos_contrato p ON CONVERT(varchar(100), a.{c['folio']}) = p.contrato
        LEFT JOIN mejor_gestion mg ON CONVERT(varchar(50), a.{c['rut_asig']}) = mg.rut AND mg.rn = 1
        LEFT JOIN intensidad i ON CONVERT(varchar(50), a.{c['rut_asig']}) = i.rut
        LEFT JOIN {EJECUTIVOS_TABLE} e ON mg.usuario = e.{c['usuario_ej']}
        WHERE 1 = 1
          {f"AND UPPER(CONVERT(varchar(300), a.{c['source_file_asig']})) LIKE UPPER(?)" if c['source_file_asig'] else ""}
    ),
    resumen AS (
        SELECT
            base.mejor_ejecutivo,
            COUNT(*) AS q_folios,
            SUM(base.recupero) AS recupero,
            SUM(base.flag_titular) AS q_titular
        FROM base
        WHERE {where_sql}
        GROUP BY base.mejor_ejecutivo
    ),
    aporte AS (
        SELECT SUM(recupero) AS recupero_total
        FROM resumen
        WHERE mejor_ejecutivo <> 'SIN EJECUTIVO'
    )
    SELECT
        r.mejor_ejecutivo AS ejecutivo,
        r.q_folios,
        r.recupero,
        r.q_titular,
        CASE WHEN r.q_folios = 0 THEN 0 ELSE CAST(r.q_titular AS float) / r.q_folios END AS pct_contacto_titular,
        CASE
            WHEN r.mejor_ejecutivo = 'SIN EJECUTIVO' THEN 0
            WHEN a.recupero_total IS NULL OR a.recupero_total = 0 THEN 0
            ELSE CAST(r.recupero AS float) / a.recupero_total
        END AS pct_aporte
    FROM resumen r
    CROSS JOIN aporte a
    ORDER BY CASE WHEN r.mejor_ejecutivo = 'SIN EJECUTIVO' THEN 1 ELSE 0 END, r.mejor_ejecutivo
    """

    pre_params: list = [month_start, month_end]
    if c["source_file_pago"]:
        pre_params.extend(_source_file_like_values(recuperacion_file, period_month))
    pre_params.extend([month_start, month_end])
    if c["source_file_asig"]:
        pre_params.append(f"%{asignacion_file}%")
    rows = run_query(sql, tuple(pre_params + params))
    total_folios = sum(int(r["q_folios"] or 0) for r in rows)
    total_recupero = sum(float(r["recupero"] or 0) for r in rows)
    total_titular = sum(int(r["q_titular"] or 0) for r in rows)

    total = {
        "ejecutivo": "Total general",
        "q_folios": total_folios,
        "recupero": total_recupero,
        "q_titular": total_titular,
        "pct_contacto_titular": None,
        "pct_aporte": None,
    }

    return {
        "kpis": {
            "q_folios": total_folios,
            "recupero": total_recupero,
            "q_titular": total_titular,
        },
        "rows": rows,
        "total": total,
    }


def get_validacion(periodo: str) -> dict:
    c = _resolved_cols()
    period_month, _period_day, month_start, month_end, file_tokens = _parse_period(periodo)
    asignacion_file, recuperacion_file = file_tokens.split("|")
    payment_type = _norm_payment_expr(c["tipo_pago"])
    sql = f"""
    WITH pagos_validos_contrato AS (
        SELECT
            CONVERT(varchar(100), {c['contrato_pago']}) AS contrato,
            SUM(COALESCE(CAST({c['recupero']} AS float), 0)) AS recupero
        FROM {PAGOS_TABLE} p
        WHERE {payment_type} IN ('E-ACTSEGCES', 'E-MANUAL', 'E-INTER-CC', 'E-CC')
          AND CAST(p.{c['fecha_negocio_pago']} AS date) >= CAST(? AS date)
          AND CAST(p.{c['fecha_negocio_pago']} AS date) <= CAST(? AS date)
          {f"AND (UPPER(CONVERT(varchar(300), p.{c['source_file_pago']})) LIKE UPPER(?) OR UPPER(CONVERT(varchar(300), p.{c['source_file_pago']})) LIKE UPPER(?))" if c['source_file_pago'] else ""}
        GROUP BY CONVERT(varchar(100), {c['contrato_pago']})
    ),
    gestiones_531 AS (
        SELECT CONVERT(varchar(50), {c['rut_gest']}) AS rut,
               CONVERT(varchar(200), {c['usuario_gest']}) AS usuario,
               CONVERT(varchar(200), {c['contacto_gest']}) AS contacto,
               {c['fecha_gest']} AS fecha_gestion,
               CONVERT(varchar(50), {c['hora_gest']}) AS hora_gestion
        FROM {GESTION_TABLE}
        WHERE {c['cartera_gest']} = 531
          AND CAST({c['fecha_gest']} AS date) >= CAST(? AS date)
          AND CAST({c['fecha_gest']} AS date) <= CAST(? AS date)
    ),
    mejor_gestion AS (
        SELECT g.*, ROW_NUMBER() OVER (
            PARTITION BY g.rut
            ORDER BY
                CASE UPPER(LTRIM(RTRIM(COALESCE(g.contacto, ''))))
                    WHEN 'CONTACTO DIRECTO' THEN 1
                    WHEN 'CONTACTO INDIRECTO' THEN 2
                    WHEN 'NO CONTACTADO' THEN 3
                    WHEN 'GESTION DISCADOR' THEN 4
                    ELSE 99
                END,
                g.fecha_gestion DESC,
                g.hora_gestion DESC
        ) AS rn
        FROM gestiones_531 g
    ),
    base AS (
        SELECT
            CONVERT(varchar(50), a.{c['periodo']}) AS periodo,
            COALESCE(CAST(p.recupero AS float), 0) AS recupero,
            CASE WHEN UPPER(LTRIM(RTRIM(COALESCE(mg.contacto, '')))) = 'CONTACTO DIRECTO' THEN 1 ELSE 0 END AS flag_titular,
            CASE WHEN mg.usuario IS NULL OR LTRIM(RTRIM(mg.usuario)) = '' THEN 0 ELSE 1 END AS incluir_en_resumen
        FROM {ASIGNACION_TABLE} a
        LEFT JOIN pagos_validos_contrato p ON CONVERT(varchar(100), a.{c['folio']}) = p.contrato
        LEFT JOIN mejor_gestion mg ON CONVERT(varchar(50), a.{c['rut_asig']}) = mg.rut AND mg.rn = 1
        LEFT JOIN {EJECUTIVOS_TABLE} e ON mg.usuario = e.{c['usuario_ej']}
        WHERE 1 = 1
          {f"AND UPPER(CONVERT(varchar(300), a.{c['source_file_asig']})) LIKE UPPER(?)" if c['source_file_asig'] else ""}
    )
    SELECT
        COUNT(*) AS folios_asignacion,
        SUM(CASE WHEN incluir_en_resumen = 0 THEN 1 ELSE 0 END) AS folios_con_mejor_ejecutivo_vacio,
        SUM(CASE WHEN incluir_en_resumen = 1 THEN 1 ELSE 0 END) AS folios_incluidos_resumen,
        SUM(CASE WHEN incluir_en_resumen = 1 THEN recupero ELSE 0 END) AS recupero_incluido_resumen,
        SUM(CASE WHEN incluir_en_resumen = 1 THEN flag_titular ELSE 0 END) AS q_titular_incluido_resumen
    FROM base
    """
    params: list = [month_start, month_end]
    if c["source_file_pago"]:
        params.extend(_source_file_like_values(recuperacion_file, period_month))
    params.extend([month_start, month_end])
    if c["source_file_asig"]:
        params.append(f"%{asignacion_file}%")
    row = run_query(sql, tuple(params))[0]
    row["tipos_pago_validos"] = ["E-ACTSEGCES", "E-MANUAL", "E-INTER-CC", "E-CC"]
    return row
