import re
from datetime import datetime, timedelta

from database import run_query


ASIGNACION_TABLE = "dbo.tmp_LA_asignacion"
PAGOS_TABLE = "dbo.tmp_LA_pagos"
GESTION_TABLE = "dbo.tmp_GEST_CRM"
EJECUTIVOS_TABLE = "dbo.tmp_ejecutivos"
RESPUESTA_RANK_TABLE = "dbo.tmp_LA_respuesta"


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


def _table_exists(table_name: str) -> bool:
    schema, table = table_name.split(".", 1)
    sql = """
    SELECT 1
    FROM sys.tables t
    INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
    WHERE s.name = ? AND t.name = ?
    """
    return bool(run_query(sql, (schema, table)))


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
    for fmt in ("%m-%Y", "%Y-%m", "%Y-%m-%d", "%d-%m-%Y"):
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


def _to_mes_proceso(periodo: str) -> str:
    _period_month, _period_day, month_start, _month_end, _tokens = _parse_period(periodo)
    return datetime.strptime(month_start, "%Y-%m-%d").strftime("%m-%Y")


def _source_file_like_values(file_name: str, period_month: str) -> list[str]:
    compact = period_month.replace("-", "")
    return [f"%{file_name}%", f"%{compact}%"]


def _norm_payment_expr(col: str) -> str:
    return f"REPLACE(REPLACE(UPPER(LTRIM(RTRIM(CONVERT(varchar(100), {col})))), N'–', '-'), ' ', '')"


def _norm_text_expr(col: str) -> str:
    return (
        "UPPER(REPLACE(REPLACE(REPLACE("
        f"LTRIM(RTRIM(CONVERT(varchar(300), {col}))), "
        "NCHAR(8211), '-'), NCHAR(8212), '-'), ' ', ''))"
    )


def _safe_int_expr(col: str, sql_type: str = "int") -> str:
    value = f"LTRIM(RTRIM(CONVERT(varchar(50), {col})))"
    return (
        "CASE "
        f"WHEN {col} IS NULL THEN NULL "
        f"WHEN {value} = '' THEN NULL "
        f"WHEN {value} LIKE '%[^0-9]%' THEN NULL "
        f"ELSE CAST({value} AS {sql_type}) "
        "END"
    )


def _mes_proceso_where(alias: str = "x") -> str:
    return (
        f"{alias}.v LIKE '[0-1][0-9]-[1-2][0-9][0-9][0-9]' "
        f"AND LEFT({alias}.v, 2) BETWEEN '01' AND '12'"
    )


def _mes_proceso_order_expr(alias: str = "x") -> str:
    return f"CONVERT(date, RIGHT({alias}.v, 4) + LEFT({alias}.v, 2) + '01', 112)"


def _resolve_ranking_config() -> dict:
    if not _table_exists(RESPUESTA_RANK_TABLE):
        return {"enabled": False}

    cols = _columns(RESPUESTA_RANK_TABLE)
    respuesta_col = _pick_optional(
        cols,
        [
            "respuesta_gestion",
            "RespuestaGestion",
            "Respuesta",
            "respuesta",
            "RESPUESTA",
            "fld_respuesta_gestion",
            "fld_RespuestaGestion",
        ],
    )
    rank_col = _pick_optional(
        cols,
        [
            "ranking",
            "RANKING",
            "rank",
            "RANK",
            "prioridad",
            "PRIORIDAD",
            "orden",
            "ORDEN",
        ],
    )

    if not respuesta_col or not rank_col:
        return {"enabled": False}

    return {
        "enabled": True,
        "table": RESPUESTA_RANK_TABLE,
        "respuesta_col": respuesta_col,
        "rank_col": rank_col,
    }


def _ranking_sql_parts(ranking: dict) -> dict:
    if not ranking.get("enabled"):
        return {
            "cte": "",
            "join": "",
            "select": "999999 AS respuesta_ranking",
            "order": "CASE WHEN g.rut IS NULL THEN 999999 ELSE 999999 END",
        }

    respuesta_expr = _norm_text_expr(f"r.{ranking['respuesta_col']}")
    rank_expr = _safe_int_expr(f"r.{ranking['rank_col']}")
    return {
        "cte": f""",
    ranking_respuesta AS (
        SELECT
            {respuesta_expr} AS respuesta_norm,
            MIN({rank_expr}) AS respuesta_ranking
        FROM {ranking['table']} r
        WHERE r.{ranking['respuesta_col']} IS NOT NULL
        GROUP BY {respuesta_expr}
    )""",
        "join": "LEFT JOIN ranking_respuesta rr ON rr.respuesta_norm = g.respuesta_norm",
        "select": "COALESCE(rr.respuesta_ranking, 999999) AS respuesta_ranking",
        "order": "COALESCE(rr.respuesta_ranking, 999999)",
    }


def _contacto_gestion_order_expr(alias: str = "g.contacto") -> str:
    return f"""
                    CASE UPPER(LTRIM(RTRIM(COALESCE({alias}, ''))))
                        WHEN 'CONTACTO DIRECTO' THEN 1
                        WHEN 'CONTACTO INDIRECTO' THEN 2
                        WHEN 'NO CONTACTADO' THEN 3
                        WHEN 'GESTION DISCADOR' THEN 4
                        ELSE 99
                    END
    """


def _usuario_final_expr(alias: str = "mg.usuario") -> str:
    return f"""
            CASE UPPER(LTRIM(RTRIM(CONVERT(varchar(200), {alias}))))
                WHEN 'GTRASLAVINA' THEN 'Gloria Traslaviña'
                WHEN 'IOVIEDO' THEN 'Isabel Oviedo'
                WHEN 'MTOVAR' THEN 'Miglen Tovar'
                WHEN 'PPENA' THEN 'Priscilla Peña'
                ELSE 'PHOENIX'
            END
    """


def _nombre_ejecutivo_expr(nombre_col: str) -> str:
    return f"COALESCE(CONVERT(varchar(260), {nombre_col}), 'PHOENIX')"


def _resolved_cols() -> dict:
    a = _columns(ASIGNACION_TABLE)
    p = _columns(PAGOS_TABLE)
    g = _columns(GESTION_TABLE)
    e = _columns(EJECUTIVOS_TABLE)
    return {
        "periodo": _pick(a, ["mes_proceso", "periodo", "fld_PERIODO", "fld_FECHA", "fecha_carga"], "periodo"),
        "mes_proceso_asig": _pick_optional(a, ["mes_proceso", "periodo"]),
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
        "mes_proceso_pago": _pick_optional(p, ["mes_proceso", "periodo"]),
        "fecha_negocio_pago": _pick_optional(p, ["fecha_negocio", "fld_FECHA_NEGOCIO", "fld_FechaNegocio"]),
        "source_file_pago": _pick_optional(p, ["source_file", "archivo_origen", "file_name"]),
        "rut_gest": _pick(g, ["rut", "RUT"], "rut gestion"),
        "usuario_gest": _pick(g, ["UsuarioGestion"], "usuario gestion"),
        "contacto_gest": _pick(g, ["ContactoGestion"], "contacto gestion"),
        "resp_gest": _pick(g, ["RespuestaGestion"], "respuesta gestion"),
        "obs_gest": _pick(g, ["observaciones", "Observaciones"], "observaciones"),
        "tel_gest": _pick_optional(g, ["telefono", "Telefono", "TelefonoGestion", "telefono_gestion"]),
        "fecha_gest": _pick(g, ["GestionFecha"], "fecha gestion"),
        "hora_gest": _pick(g, ["GestionHora"], "hora gestion"),
        "id_gest": _pick_optional(g, ["id", "ID", "Id"]),
        "cartera_gest": _pick(g, ["Cartera", "cartera", "fld_CARTERA", "fld_cartera"], "cartera gestion"),
        "usuario_ej": _pick(e, ["usuario_ejecutivo"], "usuario ejecutivo"),
        "nombre_ej": _pick(e, ["nombre_ejecutivo"], "nombre ejecutivo"),
        "periodo_desde_ej": _pick_optional(e, ["periodo_desde"]),
        "periodo_hasta_ej": _pick_optional(e, ["periodo_hasta"]),
    }


def _resolved_cols_filtros() -> dict:
    a = _columns(ASIGNACION_TABLE)
    p = _columns(PAGOS_TABLE)
    e = _columns(EJECUTIVOS_TABLE)
    return {
        "mes_proceso_asig": _pick_optional(a, ["mes_proceso", "periodo"]),
        "tipo_cartera": _pick_optional(a, ["fld_TIPO_CARTERA"]),
        "mes_proceso_pago": _pick_optional(p, ["mes_proceso", "periodo"]),
        "fecha_negocio_pago": _pick_optional(p, ["fecha_negocio", "fld_FECHA_NEGOCIO", "fld_FechaNegocio"]),
        "nombre_ej": _pick_optional(e, ["nombre_ejecutivo"]),
        "periodo_desde_ej": _pick_optional(e, ["periodo_desde"]),
        "periodo_hasta_ej": _pick_optional(e, ["periodo_hasta"]),
    }


def get_filtros(periodo: str | None = None) -> dict:
    c = _resolved_cols_filtros()
    periodos_sql = ""
    period_where = _mes_proceso_where("x")
    period_order = _mes_proceso_order_expr("x")
    if c["mes_proceso_pago"] and c["mes_proceso_asig"]:
        periodos_sql = f"""
            SELECT x.v
            FROM (
                SELECT DISTINCT LTRIM(RTRIM(CONVERT(varchar(20), p.{c['mes_proceso_pago']}))) AS v
                FROM {PAGOS_TABLE} p
                WHERE p.{c['mes_proceso_pago']} IS NOT NULL
                UNION
                SELECT DISTINCT LTRIM(RTRIM(CONVERT(varchar(20), a.{c['mes_proceso_asig']}))) AS v
                FROM {ASIGNACION_TABLE} a
                WHERE a.{c['mes_proceso_asig']} IS NOT NULL
            ) x
            WHERE {period_where}
            ORDER BY {period_order} DESC
        """
    elif c["mes_proceso_pago"]:
        periodos_sql = f"""
            SELECT x.v
            FROM (
                SELECT DISTINCT LTRIM(RTRIM(CONVERT(varchar(20), p.{c['mes_proceso_pago']}))) AS v
                FROM {PAGOS_TABLE} p
                WHERE p.{c['mes_proceso_pago']} IS NOT NULL
            ) x
            WHERE {period_where}
            ORDER BY {period_order} DESC
        """
    elif c["fecha_negocio_pago"]:
        periodos_sql = f"""
            SELECT x.v
            FROM (
                SELECT DISTINCT
                    RIGHT('0' + CAST(MONTH({c['fecha_negocio_pago']}) AS varchar(2)), 2) + '-' + CAST(YEAR({c['fecha_negocio_pago']}) AS varchar(4)) AS v
                FROM {PAGOS_TABLE}
                WHERE {c['fecha_negocio_pago']} IS NOT NULL
            ) x
            ORDER BY {period_order} DESC
        """
    else:
        periodos_sql = "SELECT CAST(NULL AS varchar(20)) AS v WHERE 1 = 0"

    periodos_norm: list[str] = []
    for r in run_query(periodos_sql):
        raw = str(r.get("v") or "").strip()
        if not raw:
            continue
        try:
            periodos_norm.append(_to_mes_proceso(raw))
        except Exception:
            continue
    periodos = sorted(
        set(periodos_norm),
        key=lambda s: datetime.strptime(s, "%m-%Y"),
        reverse=True,
    )
    selected_period = _to_mes_proceso(periodo) if periodo else (periodos[0] if periodos else "")
    _period_month, _period_day, month_start, _month_end, _tokens = _parse_period(selected_period) if selected_period else ("", "", "", "", "")
    tipos: list[str] = []
    if c["tipo_cartera"]:
        tipos_where = f"WHERE {c['tipo_cartera']} IS NOT NULL"
        tipos_params: list[str] = []
        if selected_period and c["mes_proceso_asig"]:
            tipos_where += f" AND LTRIM(RTRIM(CONVERT(varchar(20), {c['mes_proceso_asig']}))) = ?"
            tipos_params.append(selected_period)

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
                {tipos_where}
                ORDER BY v
                """,
                tuple(tipos_params),
            )
        ]
    executive_conditions: list[str] = []
    executive_params: list[str] = []
    if selected_period:
        if c["periodo_desde_ej"]:
            executive_conditions.append(f"({c['periodo_desde_ej']} IS NULL OR CAST({c['periodo_desde_ej']} AS date) <= CAST(? AS date))")
            executive_params.append(month_start)
        if c["periodo_hasta_ej"]:
            executive_conditions.append(f"({c['periodo_hasta_ej']} IS NULL OR CAST({c['periodo_hasta_ej']} AS date) >= CAST(? AS date))")
            executive_params.append(month_start)

    executive_where = ""
    if executive_conditions:
        executive_where = "\n                  AND " + "\n                  AND ".join(executive_conditions)

    return {
        "periodos": periodos,
        "carteras_crm": [531],
        "tipo_cartera": tipos,
        "ejecutivos": (
            [
                r["v"]
                for r in run_query(
                    f"""
                    SELECT DISTINCT CONVERT(varchar(260), {c['nombre_ej']}) AS v
                    FROM {EJECUTIVOS_TABLE}
                    WHERE {c['nombre_ej']} IS NOT NULL
                      AND LTRIM(RTRIM(CONVERT(varchar(260), {c['nombre_ej']}))) <> ''
                      {executive_where}
                    ORDER BY v
                    """,
                    tuple(executive_params),
                )
                if r["v"]
            ]
            if c["nombre_ej"]
            else []
        ),
    }


def get_resumen(filters: dict) -> dict:
    c = _resolved_cols()
    if not c["mes_proceso_pago"] and not c["fecha_negocio_pago"]:
        raise RuntimeError("No existe columna de mes_proceso/fecha_negocio en pagos para filtrar La Araucana.")
    gestion_id_expr = _safe_int_expr(c["id_gest"], "bigint") if c["id_gest"] else "CAST(NULL AS bigint)"
    gestion_id_order = ", g.id_gestion DESC" if c["id_gest"] else ""
    contacto_order_expr = _contacto_gestion_order_expr("g.contacto")
    ranking_parts = _ranking_sql_parts(_resolve_ranking_config())
    nombre_ejecutivo_expr = _nombre_ejecutivo_expr(f"e.{c['nombre_ej']}")
    selected_mes_proceso = _to_mes_proceso(str(filters.get("periodo") or ""))
    period_month, _period_day, month_start, month_end, _file_tokens = _parse_period(selected_mes_proceso)
    payment_type = _norm_payment_expr(c["tipo_pago"])
    pagos_period_sql = (
        f"AND LTRIM(RTRIM(CONVERT(varchar(20), p.{c['mes_proceso_pago']}))) = ?"
        if c["mes_proceso_pago"]
        else f"AND CAST(p.{c['fecha_negocio_pago']} AS date) >= CAST(? AS date) AND CAST(p.{c['fecha_negocio_pago']} AS date) <= CAST(? AS date)"
    )
    asignacion_period_sql = (
        f"AND LTRIM(RTRIM(CONVERT(varchar(20), a.{c['mes_proceso_asig']}))) = ?"
        if c["mes_proceso_asig"]
        else (f"AND UPPER(CONVERT(varchar(300), a.{c['source_file_asig']})) LIKE UPPER(?)" if c["source_file_asig"] else "")
    )
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
          {pagos_period_sql}
        GROUP BY CONVERT(varchar(100), {c['contrato_pago']})
    ),
    gestiones_531 AS (
        SELECT
            CONVERT(varchar(50), {c['rut_gest']}) AS rut,
            CONVERT(varchar(200), {c['usuario_gest']}) AS usuario,
            CONVERT(varchar(200), {c['contacto_gest']}) AS contacto,
            CONVERT(varchar(300), {c['resp_gest']}) AS respuesta,
            {_norm_text_expr(c['resp_gest'])} AS respuesta_norm,
            CONVERT(varchar(500), {c['obs_gest']}) AS observaciones,
            {c['fecha_gest']} AS fecha_gestion,
            CONVERT(varchar(50), {c['hora_gest']}) AS hora_gestion,
            {gestion_id_expr} AS id_gestion
        FROM {GESTION_TABLE}
        WHERE {c['cartera_gest']} = 531
          AND CAST({c['fecha_gest']} AS date) >= CAST(? AS date)
          AND CAST({c['fecha_gest']} AS date) <= CAST(? AS date)
    ){ranking_parts["cte"]},
    intensidad AS (
        SELECT rut, COUNT(*) AS intensidad
        FROM gestiones_531
        GROUP BY rut
    ),
    mejor_gestion AS (
        SELECT
            g.*,
            {ranking_parts["select"]},
            ROW_NUMBER() OVER (
                PARTITION BY g.rut
                ORDER BY
                    {contacto_order_expr} ASC,
                    {ranking_parts["order"]} ASC,
                    g.fecha_gestion DESC,
                    g.hora_gestion DESC
                    {gestion_id_order}
            ) AS rn
        FROM gestiones_531 g
        {ranking_parts["join"]}
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
            COALESCE(CAST(a.{c['capital']} AS float), 0) AS capital,
            COALESCE(CAST(a.{c['deuda']} AS float), 0) AS deuda,
            COALESCE(CAST(p.recupero AS float), 0) AS recupero,
            COALESCE(i.intensidad, 0) AS intensidad,
            mg.usuario,
            CASE
                WHEN mg.usuario IS NULL OR LTRIM(RTRIM(mg.usuario)) = '' THEN NULL
                ELSE {nombre_ejecutivo_expr}
            END AS mejor_ejecutivo,
            CASE WHEN UPPER(LTRIM(RTRIM(COALESCE(mg.contacto, '')))) = 'CONTACTO DIRECTO' THEN 1 ELSE 0 END AS flag_titular,
            CASE WHEN mg.usuario IS NULL OR LTRIM(RTRIM(mg.usuario)) = '' THEN 0 ELSE 1 END AS incluir_en_resumen
        FROM {ASIGNACION_TABLE} a
        LEFT JOIN pagos_validos_contrato p ON CONVERT(varchar(100), a.{c['folio']}) = p.contrato
        LEFT JOIN mejor_gestion mg ON CONVERT(varchar(50), a.{c['rut_asig']}) = mg.rut AND mg.rn = 1
        LEFT JOIN intensidad i ON CONVERT(varchar(50), a.{c['rut_asig']}) = i.rut
        LEFT JOIN {EJECUTIVOS_TABLE} e ON mg.usuario = e.{c['usuario_ej']}
          {f"AND ({c['periodo_desde_ej']} IS NULL OR CAST({c['periodo_desde_ej']} AS date) <= CAST(? AS date))" if c['periodo_desde_ej'] else ''}
          {f"AND ({c['periodo_hasta_ej']} IS NULL OR CAST({c['periodo_hasta_ej']} AS date) >= CAST(? AS date))" if c['periodo_hasta_ej'] else ''}
        WHERE 1 = 1
          {asignacion_period_sql}
    ),
    resumen AS (
        SELECT
            base.tipo_cartera,
            base.mejor_ejecutivo,
            COUNT(*) AS q_folios,
            SUM(base.deuda) AS deuda,
            SUM(base.recupero) AS recupero,
            SUM(base.flag_titular) AS q_titular
        FROM base
        WHERE {where_sql}
        GROUP BY base.tipo_cartera, base.mejor_ejecutivo
    ),
    aporte AS (
        SELECT
            base.tipo_cartera,
            SUM(base.recupero) AS recupero_total
        FROM base
        WHERE base.incluir_en_resumen = 1
        GROUP BY base.tipo_cartera
    )
    SELECT
        r.mejor_ejecutivo AS ejecutivo,
        r.tipo_cartera,
        r.q_folios,
        r.deuda,
        r.recupero,
        r.q_titular,
        CASE WHEN r.q_folios = 0 THEN 0 ELSE CAST(r.q_titular AS float) / r.q_folios END AS pct_contacto_titular,
        CASE
            WHEN a.recupero_total IS NULL OR a.recupero_total = 0 THEN 0
            ELSE CAST(r.recupero AS float) / a.recupero_total
        END AS pct_aporte
    FROM resumen r
    LEFT JOIN aporte a ON a.tipo_cartera = r.tipo_cartera
    ORDER BY
        CASE r.tipo_cartera WHEN '+365' THEN 1 WHEN 'CASTIGO' THEN 2 WHEN 'VIGENTE' THEN 3 ELSE 9 END,
        CASE WHEN r.mejor_ejecutivo = 'PHOENIX' THEN 1 ELSE 0 END,
        r.mejor_ejecutivo
    """

    pre_params: list = [selected_mes_proceso] if c["mes_proceso_pago"] else [month_start, month_end]
    pre_params.extend([month_start, month_end])
    if c["periodo_desde_ej"]:
        pre_params.append(month_start)
    if c["periodo_hasta_ej"]:
        pre_params.append(month_start)
    if c["mes_proceso_asig"]:
        pre_params.append(selected_mes_proceso)
    elif c["source_file_asig"]:
        pre_params.append(f"%ASIGNACION_{period_month}.csv%")
    rows = run_query(sql, tuple(pre_params + params))
    total_folios = sum(int(r["q_folios"] or 0) for r in rows)
    total_deuda = sum(float(r["deuda"] or 0) for r in rows)
    total_recupero = sum(float(r["recupero"] or 0) for r in rows)
    total_titular = sum(int(r["q_titular"] or 0) for r in rows)

    total = {
        "ejecutivo": "Total general",
        "q_folios": total_folios,
        "deuda": total_deuda,
        "recupero": total_recupero,
        "q_titular": total_titular,
        "pct_contacto_titular": None,
        "pct_aporte": None,
    }

    return {
        "kpis": {
            "q_folios": total_folios,
            "deuda": total_deuda,
            "recupero": total_recupero,
            "q_titular": total_titular,
        },
        "rows": rows,
        "total": total,
    }


def get_validacion(periodo: str) -> dict:
    c = _resolved_cols()
    if not c["mes_proceso_pago"] and not c["fecha_negocio_pago"]:
        raise RuntimeError("No existe columna de mes_proceso/fecha_negocio en pagos para filtrar La Araucana.")
    gestion_id_expr = _safe_int_expr(c["id_gest"], "bigint") if c["id_gest"] else "CAST(NULL AS bigint)"
    gestion_id_order = ", g.id_gestion DESC" if c["id_gest"] else ""
    contacto_order_expr = _contacto_gestion_order_expr("g.contacto")
    ranking_parts = _ranking_sql_parts(_resolve_ranking_config())
    selected_mes_proceso = _to_mes_proceso(periodo)
    period_month, _period_day, month_start, month_end, _file_tokens = _parse_period(selected_mes_proceso)
    payment_type = _norm_payment_expr(c["tipo_pago"])
    pagos_period_sql = (
        f"AND LTRIM(RTRIM(CONVERT(varchar(20), p.{c['mes_proceso_pago']}))) = ?"
        if c["mes_proceso_pago"]
        else f"AND CAST(p.{c['fecha_negocio_pago']} AS date) >= CAST(? AS date) AND CAST(p.{c['fecha_negocio_pago']} AS date) <= CAST(? AS date)"
    )
    asignacion_period_sql = (
        f"AND LTRIM(RTRIM(CONVERT(varchar(20), a.{c['mes_proceso_asig']}))) = ?"
        if c["mes_proceso_asig"]
        else (f"AND UPPER(CONVERT(varchar(300), a.{c['source_file_asig']})) LIKE UPPER(?)" if c["source_file_asig"] else "")
    )
    sql = f"""
    WITH pagos_validos_contrato AS (
        SELECT
            CONVERT(varchar(100), {c['contrato_pago']}) AS contrato,
            SUM(COALESCE(CAST({c['recupero']} AS float), 0)) AS recupero
        FROM {PAGOS_TABLE} p
        WHERE {payment_type} IN ('E-ACTSEGCES', 'E-MANUAL', 'E-INTER-CC', 'E-CC')
          {pagos_period_sql}
        GROUP BY CONVERT(varchar(100), {c['contrato_pago']})
    ),
    gestiones_531 AS (
        SELECT CONVERT(varchar(50), {c['rut_gest']}) AS rut,
               CONVERT(varchar(200), {c['usuario_gest']}) AS usuario,
               CONVERT(varchar(200), {c['contacto_gest']}) AS contacto,
               CONVERT(varchar(300), {c['resp_gest']}) AS respuesta,
               {_norm_text_expr(c['resp_gest'])} AS respuesta_norm,
               {c['fecha_gest']} AS fecha_gestion,
               CONVERT(varchar(50), {c['hora_gest']}) AS hora_gestion,
               {gestion_id_expr} AS id_gestion
        FROM {GESTION_TABLE}
        WHERE {c['cartera_gest']} = 531
          AND CAST({c['fecha_gest']} AS date) >= CAST(? AS date)
          AND CAST({c['fecha_gest']} AS date) <= CAST(? AS date)
    ){ranking_parts["cte"]},
    mejor_gestion AS (
        SELECT g.*, {ranking_parts["select"]}, ROW_NUMBER() OVER (
            PARTITION BY g.rut
            ORDER BY
                {contacto_order_expr} ASC,
                {ranking_parts["order"]} ASC,
                g.fecha_gestion DESC,
                g.hora_gestion DESC
                {gestion_id_order}
        ) AS rn
        FROM gestiones_531 g
        {ranking_parts["join"]}
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
        WHERE 1 = 1
          {asignacion_period_sql}
    )
    SELECT
        COUNT(*) AS folios_asignacion,
        SUM(CASE WHEN incluir_en_resumen = 0 THEN 1 ELSE 0 END) AS folios_con_mejor_ejecutivo_vacio,
        SUM(CASE WHEN incluir_en_resumen = 1 THEN 1 ELSE 0 END) AS folios_incluidos_resumen,
        SUM(CASE WHEN incluir_en_resumen = 1 THEN recupero ELSE 0 END) AS recupero_incluido_resumen,
        SUM(CASE WHEN incluir_en_resumen = 1 THEN flag_titular ELSE 0 END) AS q_titular_incluido_resumen
    FROM base
    """
    params: list = [selected_mes_proceso] if c["mes_proceso_pago"] else [month_start, month_end]
    params.extend([month_start, month_end])
    if c["mes_proceso_asig"]:
        params.append(selected_mes_proceso)
    elif c["source_file_asig"]:
        params.append(f"%ASIGNACION_{period_month}.csv%")
    row = run_query(sql, tuple(params))[0]
    row["tipos_pago_validos"] = ["E-ACTSEGCES", "E-MANUAL", "E-INTER-CC", "E-CC"]
    return row


def get_export_rows(filters: dict) -> tuple[str, list[dict]]:
    c = _resolved_cols()
    if not c["mes_proceso_pago"] and not c["fecha_negocio_pago"]:
        raise RuntimeError("No existe columna de mes_proceso/fecha_negocio en pagos para filtrar La Araucana.")
    gestion_id_expr = _safe_int_expr(c["id_gest"], "bigint") if c["id_gest"] else "CAST(NULL AS bigint)"
    gestion_id_order = ", g.id_gestion DESC" if c["id_gest"] else ""
    contacto_order_expr = _contacto_gestion_order_expr("g.contacto")
    nombre_ejecutivo_expr = _nombre_ejecutivo_expr(f"e.{c['nombre_ej']}")
    ranking_parts = _ranking_sql_parts(_resolve_ranking_config())
    selected_mes_proceso = _to_mes_proceso(str(filters.get("periodo") or ""))
    period_month, _period_day, month_start, month_end, _file_tokens = _parse_period(selected_mes_proceso)
    payment_type = _norm_payment_expr(c["tipo_pago"])
    pagos_period_sql = (
        f"AND LTRIM(RTRIM(CONVERT(varchar(20), p.{c['mes_proceso_pago']}))) = ?"
        if c["mes_proceso_pago"]
        else f"AND CAST(p.{c['fecha_negocio_pago']} AS date) >= CAST(? AS date) AND CAST(p.{c['fecha_negocio_pago']} AS date) <= CAST(? AS date)"
    )
    asignacion_period_sql = (
        f"AND LTRIM(RTRIM(CONVERT(varchar(20), a.{c['mes_proceso_asig']}))) = ?"
        if c["mes_proceso_asig"]
        else (f"AND UPPER(CONVERT(varchar(300), a.{c['source_file_asig']})) LIKE UPPER(?)" if c["source_file_asig"] else "")
    )

    where_sql = "1 = 1"
    params: list = []
    sql = f"""
    WITH pagos_validos_contrato AS (
        SELECT
            CONVERT(varchar(100), {c['contrato_pago']}) AS contrato,
            SUM(COALESCE(CAST({c['recupero']} AS float), 0)) AS recupero
        FROM {PAGOS_TABLE} p
        WHERE {payment_type} IN ('E-ACTSEGCES', 'E-MANUAL', 'E-INTER-CC', 'E-CC')
          {pagos_period_sql}
        GROUP BY CONVERT(varchar(100), {c['contrato_pago']})
    ),
    gestiones_531 AS (
        SELECT
            CONVERT(varchar(50), {c['rut_gest']}) AS rut,
            CONVERT(varchar(200), {c['usuario_gest']}) AS usuario,
            CONVERT(varchar(200), {c['contacto_gest']}) AS contacto,
            CONVERT(varchar(300), {c['resp_gest']}) AS respuesta,
            {_norm_text_expr(c['resp_gest'])} AS respuesta_norm,
            {c['fecha_gest']} AS fecha_gestion,
            CONVERT(varchar(50), {c['hora_gest']}) AS hora_gestion,
            {f"CONVERT(varchar(100), {c['tel_gest']})" if c['tel_gest'] else "NULL"} AS telefono,
            {gestion_id_expr} AS id_gestion
        FROM {GESTION_TABLE}
        WHERE {c['cartera_gest']} = 531
          AND CAST({c['fecha_gest']} AS date) >= CAST(? AS date)
          AND CAST({c['fecha_gest']} AS date) <= CAST(? AS date)
    ){ranking_parts["cte"]},
    mejor_gestion AS (
        SELECT
            g.*,
            {ranking_parts["select"]},
            ROW_NUMBER() OVER (
                PARTITION BY g.rut
                ORDER BY
                    {contacto_order_expr} ASC,
                    {ranking_parts["order"]} ASC,
                    g.fecha_gestion DESC,
                    g.hora_gestion DESC
                    {gestion_id_order}
            ) AS rn
        FROM gestiones_531 g
        {ranking_parts["join"]}
    ),
    base AS (
        SELECT
            CONVERT(varchar(100), a.{c['folio']}) AS folio_credito,
            CONVERT(varchar(50), a.{c['rut_asig']}) AS rut,
            CONVERT(varchar(100), a.{c['tramo']}) AS tramo_mora,
            COALESCE(CAST(a.{c['capital']} AS float), 0) AS capital,
            COALESCE(CAST(a.{c['deuda']} AS float), 0) AS total_deuda,
            COALESCE(CAST(p.recupero AS float), 0) AS recupero,
            CASE
                WHEN LTRIM(RTRIM(CONVERT(varchar(100), a.{c['tipo_cartera']}))) = '365' THEN '+365'
                ELSE LTRIM(RTRIM(CONVERT(varchar(100), a.{c['tipo_cartera']})))
            END AS tipo_cartera,
            {nombre_ejecutivo_expr} AS nombre_ejecutivo,
            mg.usuario AS usuariogestion,
            mg.contacto AS contactogestion,
            mg.respuesta AS respuestagestion,
            CONVERT(varchar(10), CAST(mg.fecha_gestion AS date), 23) AS gestionfecha,
            mg.hora_gestion AS gestionhora,
            mg.telefono AS telefono
        FROM {ASIGNACION_TABLE} a
        LEFT JOIN mejor_gestion mg ON CONVERT(varchar(50), a.{c['rut_asig']}) = mg.rut AND mg.rn = 1
        LEFT JOIN {EJECUTIVOS_TABLE} e ON mg.usuario = e.{c['usuario_ej']}
          {f"AND ({c['periodo_desde_ej']} IS NULL OR CAST({c['periodo_desde_ej']} AS date) <= CAST(? AS date))" if c['periodo_desde_ej'] else ''}
          {f"AND ({c['periodo_hasta_ej']} IS NULL OR CAST({c['periodo_hasta_ej']} AS date) >= CAST(? AS date))" if c['periodo_hasta_ej'] else ''}
        LEFT JOIN pagos_validos_contrato p ON CONVERT(varchar(100), a.{c['folio']}) = p.contrato
        WHERE 1 = 1
          AND mg.usuario IS NOT NULL
          AND LTRIM(RTRIM(mg.usuario)) <> ''
          {asignacion_period_sql}
    )
    SELECT
        folio_credito,
        rut,
        tramo_mora,
        capital,
        total_deuda,
        recupero,
        tipo_cartera,
        usuariogestion,
        CASE WHEN contactogestion IS NULL THEN '' ELSE 'CONTACTO DIRECTO' END AS contactogestion,
        respuestagestion,
        gestionfecha,
        gestionhora,
        telefono
    FROM base
    WHERE {where_sql}
    ORDER BY tipo_cartera, tramo_mora, rut
    """

    pre_params: list = [selected_mes_proceso] if c["mes_proceso_pago"] else [month_start, month_end]
    pre_params.extend([month_start, month_end])
    if c["periodo_desde_ej"]:
        pre_params.append(month_start)
    if c["periodo_hasta_ej"]:
        pre_params.append(month_start)
    if c["mes_proceso_asig"]:
        pre_params.append(selected_mes_proceso)
    elif c["source_file_asig"]:
        pre_params.append(f"%ASIGNACION_{period_month}.csv%")

    rows = run_query(sql, tuple(pre_params + params))
    return period_month, rows
