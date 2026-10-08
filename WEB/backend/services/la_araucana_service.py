import time
from datetime import datetime, timedelta

from database import run_query, run_query_sets


# La asignacion solo aporta la deuda de cada folio; el recupero sale de pagos y gestiones.
ASIGNACION_TABLE = "dbo.tmp_LA_asignacion"
PAGOS_TABLE = "dbo.tmp_LA_pagos"
GESTION_TABLE = "dbo.tmp_GEST_CRM"
RESPUESTA_RANK_TABLE = "dbo.tmp_LA_respuesta"
# Usuarios del CRM con nombre propio en el resumen; el resto se agrupa en PHOENIX.
EJECUTIVOS_TABLE = "dbo.tmp_ejecutivos"

CARTERA_CRM = 531
TIPOS_PAGO_VALIDOS = ["E-ACTSEGCES", "E-MANUAL", "E-INTER-CC", "E-CC"]
# Los negocios (reprogramaciones) vienen en la misma tabla de pagos con este tipo de pago.
TIPOS_PAGO_NEGOCIO = ["NE-REPRO"]
# Los negocios se separan segun la deuda del folio: hasta este monto o sobre el.
TRAMO_DEUDA_NEGOCIO = 1000000


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


def _norm_payment_expr(col: str) -> str:
    return f"REPLACE(REPLACE(UPPER(LTRIM(RTRIM(CONVERT(varchar(100), {col})))), N'–', '-'), ' ', '')"


def _norm_text_expr(col: str) -> str:
    return (
        "UPPER(REPLACE(REPLACE(REPLACE("
        f"LTRIM(RTRIM(CONVERT(varchar(300), {col}))), "
        "NCHAR(8211), '-'), NCHAR(8212), '-'), ' ', ''))"
    )


def _mes_proceso_where(alias: str = "x") -> str:
    return (
        f"{alias}.v LIKE '[0-1][0-9]-[1-2][0-9][0-9][0-9]' "
        f"AND LEFT({alias}.v, 2) BETWEEN '01' AND '12'"
    )


def _mes_proceso_order_expr(alias: str = "x") -> str:
    return f"CONVERT(date, RIGHT({alias}.v, 4) + LEFT({alias}.v, 2) + '01', 112)"


def _ranking_sql_parts(resp_col: str) -> dict:
    cols = _columns(RESPUESTA_RANK_TABLE)
    respuesta_col = _pick_optional(cols, ["Respuesta", "respuesta", "RESPUESTA", "RespuestaGestion", "respuesta_gestion"])
    rank_col = _pick_optional(cols, ["RANKING", "ranking", "Ranking"])
    if not respuesta_col or not rank_col:
        return {"cte": "", "join": "", "select": "999999"}

    respuesta_expr = _norm_text_expr(f"r.{respuesta_col}")
    return {
        "cte": f"""WITH ranking_respuesta AS (
        SELECT
            {respuesta_expr} AS respuesta_norm,
            MIN(CAST(r.{rank_col} AS int)) AS respuesta_ranking
        FROM {RESPUESTA_RANK_TABLE} r
        WHERE r.{respuesta_col} IS NOT NULL
        GROUP BY {respuesta_expr}
    )""",
        "join": f"LEFT JOIN ranking_respuesta rr ON rr.respuesta_norm = {_norm_text_expr(resp_col)}",
        "select": "COALESCE(rr.respuesta_ranking, 999999)",
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


def _ejecutivas(periodo: str) -> dict[str, str]:
    """Usuario del CRM -> nombre, segun tmp_ejecutivos, para quienes estan vigentes en el mes."""
    e = _columns(EJECUTIVOS_TABLE)
    usuario_col = _pick(e, ["usuario_ejecutivo"], "usuario ejecutivo")
    nombre_col = _pick(e, ["nombre_ejecutivo"], "nombre ejecutivo")
    cartera_col = _pick_optional(e, ["cartera", "Cartera"])
    desde_col = _pick_optional(e, ["periodo_desde"])
    hasta_col = _pick_optional(e, ["periodo_hasta"])
    _period_month, _period_day, month_start, month_end, _file_tokens = _parse_period(_to_mes_proceso(periodo))
    where = [f"{usuario_col} IS NOT NULL", f"LTRIM(RTRIM(CONVERT(varchar(260), {nombre_col}))) <> ''"]
    params: list = []
    if cartera_col:
        where.append(f"{cartera_col} = {CARTERA_CRM}")
    # Vigente en cualquier dia del mes: quien entra o sale a mitad de mes tambien cuenta.
    if desde_col:
        where.append(f"({desde_col} IS NULL OR CAST({desde_col} AS date) <= CAST(? AS date))")
        params.append(month_end)
    if hasta_col:
        where.append(f"({hasta_col} IS NULL OR CAST({hasta_col} AS date) >= CAST(? AS date))")
        params.append(month_start)
    rows = run_query(
        f"""
        SELECT
            UPPER(LTRIM(RTRIM(CONVERT(varchar(200), {usuario_col})))) AS usuario,
            LTRIM(RTRIM(CONVERT(nvarchar(260), {nombre_col}))) AS nombre
        FROM {EJECUTIVOS_TABLE}
        WHERE {" AND ".join(where)}
        ORDER BY {desde_col or usuario_col}
        """,
        tuple(params),
    )
    return {r["usuario"]: r["nombre"] for r in rows if r["usuario"] and r["nombre"]}


def _ejecutivo_expr(alias: str, ejecutivas: dict[str, str]) -> str:
    if not ejecutivas:
        return "'PHOENIX'"
    whens = "\n".join(
        "                WHEN '{}' THEN N'{}'".format(usuario.replace("'", "''"), nombre.replace("'", "''"))
        for usuario, nombre in ejecutivas.items()
    )
    return f"""
            CASE UPPER(LTRIM(RTRIM(CONVERT(varchar(200), {alias}))))
{whens}
                ELSE 'PHOENIX'
            END
    """


def _rut_pago_expr(col: str) -> str:
    # fld_RutAfiliado viene como 12345678-9; el CRM guarda el rut sin digito verificador.
    return f"CONVERT(varchar(20), TRY_CAST(LEFT(LTRIM(RTRIM({col})), CHARINDEX('-', LTRIM(RTRIM({col})) + '-') - 1) AS bigint))"


def _fecha_pago_expr(col: str) -> str:
    value = f"LTRIM(RTRIM(CONVERT(varchar(30), {col})))"
    return f"""NULLIF(CASE
                WHEN {value} LIKE '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]%' THEN TRY_CAST(LEFT({value}, 10) AS date)
                WHEN {value} LIKE '[0-9][0-9]-[0-9][0-9]-[0-9][0-9][0-9][0-9]%' THEN TRY_CAST(SUBSTRING({value}, 7, 4) + SUBSTRING({value}, 4, 2) + LEFT({value}, 2) AS date)
            END, '19000101')"""


def _tipo_cartera_expr(col: str) -> str:
    value = f"UPPER(LTRIM(RTRIM(CONVERT(varchar(100), {col}))))"
    return f"""CASE {value}
                WHEN 'CARTERA VIGENTE' THEN 'VIGENTE'
                WHEN 'CARTERA CASTIGO' THEN 'CASTIGO'
                WHEN 'CARTERA NO VIGENTE' THEN '+365'
                WHEN '365' THEN '+365'
                ELSE {value}
            END"""


def _resolved_cols() -> dict:
    p = _columns(PAGOS_TABLE)
    g = _columns(GESTION_TABLE)
    return {
        "id_pago": _pick(p, ["id", "ID", "Id"], "id pagos"),
        "contrato_pago": _pick(p, ["fld_CONTRATO"], "contrato pagos"),
        "rut_pago": _pick(p, ["fld_RutAfiliado"], "rut pagos"),
        "fecha_pago": _pick(p, ["fld_FechaPago"], "fecha pago"),
        "recupero": _pick(p, ["fld_Recuperacion", "fld_RECUPERACION"], "recuperacion"),
        "tipo_pago": _pick(p, ["fld_TipoPago", "fld_TIPOPAGO"], "tipo pago"),
        "tipo_cartera": _pick(p, ["fld_TIPO_CARTERA"], "tipo cartera"),
        "mes_proceso_pago": _pick_optional(p, ["mes_proceso", "periodo"]),
        "fecha_negocio_pago": _pick_optional(p, ["fecha_negocio", "fld_FECHA_NEGOCIO", "fld_FechaNegocio"]),
        "rut_gest": _pick(g, ["rut", "RUT"], "rut gestion"),
        "usuario_gest": _pick(g, ["UsuarioGestion"], "usuario gestion"),
        "contacto_gest": _pick(g, ["ContactoGestion"], "contacto gestion"),
        "resp_gest": _pick(g, ["RespuestaGestion"], "respuesta gestion"),
        "tel_gest": _pick_optional(g, ["telefono", "Telefono", "TelefonoGestion", "telefono_gestion"]),
        "fecha_gest": _pick(g, ["GestionFecha"], "fecha gestion"),
        "hora_gest": _pick(g, ["GestionHora"], "hora gestion"),
        "id_gest": _pick_optional(g, ["id", "ID", "Id"]),
        "cartera_gest": _pick(g, ["Cartera", "cartera", "fld_CARTERA", "fld_cartera"], "cartera gestion"),
    }


def _asignacion_cols() -> dict:
    a = _columns(ASIGNACION_TABLE)
    return {
        "folio": _pick(a, ["fld_FOLIO_CREDITO"], "folio"),
        "rut": _pick(a, ["fld_RUT_ASIGNADO"], "rut asignado"),
        "tipo_cartera": _pick(a, ["fld_TIPO_CARTERA"], "tipo cartera"),
        "deuda": _pick(a, ["fld_TOTAL_DEUDA"], "deuda"),
        "mes_proceso": _pick(a, ["mes_proceso", "periodo"], "mes proceso asignacion"),
    }


def _pagos_period_sql(c: dict) -> str:
    if not c["mes_proceso_pago"] and not c["fecha_negocio_pago"]:
        raise RuntimeError("No existe columna de mes_proceso/fecha_negocio en pagos para filtrar La Araucana.")
    if c["mes_proceso_pago"]:
        return f"AND LTRIM(RTRIM(CONVERT(varchar(20), p.{c['mes_proceso_pago']}))) = ?"
    return f"AND CAST(p.{c['fecha_negocio_pago']} AS date) >= CAST(? AS date) AND CAST(p.{c['fecha_negocio_pago']} AS date) <= CAST(? AS date)"


def _atribucion_sql(
    c: dict,
    periodo: str,
    tipos_pago_validos: list[str] | None = None,
    solo_ruts_con_pago: bool = False,
) -> tuple[str, list, str]:
    """Lote SQL que deja en #base una fila por pago valido con la gestion que se lo lleva.

    Solo cuentan las gestiones del mes seleccionado (quedan en #gest). Regla: la mejor gestion del
    RUT hasta la fecha de pago (mejor ranking de respuesta segun tmp_LA_respuesta; a igualdad, mejor
    contacto y luego la mas cercana al pago). Si no hay gestion previa, la primera gestion posterior
    al pago.

    Tambien deja #gest_pago (gestiones de los RUT con pago, contra la que se hace el cruce) y
    #mejor_gestion_mes (la mejor gestion de cada RUT en el mes). Ambas salen de la variable de tabla
    @gest y no de #gest: filtrar u ordenar una tabla temporal grande obliga a SQL Server a generar
    estadisticas de cada columna, y eso tardaba mas que la consulta misma.

    Con `solo_ruts_con_pago`, #gest solo guarda las gestiones de los RUT con pago; sirve cuando
    despues no se calcula la deuda por folio.
    """
    ranking_parts = _ranking_sql_parts(f"g.{c['resp_gest']}")
    asig = _asignacion_cols()
    ejecutivas = _ejecutivas(periodo)
    selected_mes_proceso = _to_mes_proceso(periodo)
    period_month, _period_day, month_start, month_end, _file_tokens = _parse_period(selected_mes_proceso)
    tipos_pago = ", ".join(f"'{t}'" for t in (tipos_pago_validos or TIPOS_PAGO_VALIDOS))
    gestion_id_expr = f"g.{c['id_gest']}" if c["id_gest"] else "CAST(NULL AS bigint)"
    solo_ruts_sql = f"AND CONVERT(varchar(50), g.{c['rut_gest']}) IN (SELECT p.rut FROM #pagos p)" if solo_ruts_con_pago else ""
    # Las tablas temporales evitan recalcular pagos y gestiones del mes en cada referencia.
    sql = f"""SET NOCOUNT ON;
    SELECT
        p.{c['id_pago']} AS pago_id,
        CONVERT(varchar(100), p.{c['contrato_pago']}) AS contrato,
        {_rut_pago_expr(f"p.{c['rut_pago']}")} AS rut,
        {_fecha_pago_expr(f"p.{c['fecha_pago']}")} AS fecha_pago,
        {_norm_payment_expr(f"p.{c['tipo_pago']}")} AS tipo_pago,
        COALESCE({_tipo_cartera_expr(f"a.{asig['tipo_cartera']}")}, {_tipo_cartera_expr(f"p.{c['tipo_cartera']}")}) AS tipo_cartera,
        COALESCE(CAST(p.{c['recupero']} AS float), 0) AS recupero,
        CAST(a.{asig['deuda']} AS float) AS deuda
    INTO #pagos
    FROM {PAGOS_TABLE} p
    LEFT JOIN {ASIGNACION_TABLE} a
        ON a.{asig['folio']} = p.{c['contrato_pago']}
       AND a.{asig['mes_proceso']} = ?
    WHERE {_norm_payment_expr(f"p.{c['tipo_pago']}")} IN ({tipos_pago})
      {_pagos_period_sql(c)};

    {ranking_parts["cte"]}
    SELECT
        CONVERT(varchar(50), g.{c['rut_gest']}) AS rut,
        CONVERT(varchar(200), g.{c['usuario_gest']}) AS usuario,
        CONVERT(varchar(200), g.{c['contacto_gest']}) AS contacto,
        CONVERT(varchar(300), g.{c['resp_gest']}) AS respuesta,
        CAST(g.{c['fecha_gest']} AS date) AS fecha_gestion,
        CONVERT(varchar(8), g.{c['hora_gest']}) AS hora_gestion,
        {f"CONVERT(varchar(100), g.{c['tel_gest']})" if c['tel_gest'] else "CAST(NULL AS varchar(100))"} AS telefono,
        {gestion_id_expr} AS id_gestion,
        {ranking_parts["select"]} AS respuesta_ranking
    INTO #gest
    FROM {GESTION_TABLE} g
    {ranking_parts["join"]}
    WHERE g.{c['cartera_gest']} = {CARTERA_CRM}
      AND g.{c['fecha_gest']} >= CAST(? AS date)
      AND g.{c['fecha_gest']} <= CAST(? AS date)
      AND LTRIM(RTRIM(COALESCE(g.{c['usuario_gest']}, ''))) <> ''
      {solo_ruts_sql};

    DECLARE @gest TABLE (
        rut varchar(50),
        usuario varchar(200),
        contacto varchar(200),
        respuesta varchar(300),
        fecha_gestion date,
        hora_gestion varchar(8),
        telefono varchar(100),
        id_gestion bigint,
        respuesta_ranking int
    );
    INSERT INTO @gest (rut, usuario, contacto, respuesta, fecha_gestion, hora_gestion, telefono, id_gestion, respuesta_ranking)
    SELECT rut, usuario, contacto, respuesta, fecha_gestion, hora_gestion, telefono, id_gestion, respuesta_ranking
    FROM #gest;

    SELECT g.*
    INTO #gest_pago
    FROM @gest g
    WHERE g.rut IN (SELECT p.rut FROM #pagos p)
    OPTION (RECOMPILE);

    SELECT x.rut, x.usuario, x.contacto, x.respuesta, x.fecha_gestion, x.telefono
    INTO #mejor_gestion_mes
    FROM (
        SELECT
            g.rut,
            g.usuario,
            g.contacto,
            g.respuesta,
            g.fecha_gestion,
            g.telefono,
            ROW_NUMBER() OVER (
                PARTITION BY g.rut
                ORDER BY
                    g.respuesta_ranking ASC,
                    {_contacto_gestion_order_expr("g.contacto")} ASC,
                    g.fecha_gestion DESC,
                    g.hora_gestion DESC,
                    g.id_gestion DESC
            ) AS rn
        FROM @gest g
    ) x
    WHERE x.rn = 1
    OPTION (RECOMPILE);

    WITH gestiones AS (
        SELECT
            p.pago_id,
            g.*,
            CASE WHEN g.fecha_gestion <= p.fecha_pago THEN 0 ELSE 1 END AS es_posterior
        FROM #pagos p
        INNER JOIN #gest_pago g ON g.rut = p.rut AND p.fecha_pago IS NOT NULL
    ),
    gestion_elegida AS (
        SELECT
            g.*,
            ROW_NUMBER() OVER (
                PARTITION BY g.pago_id
                ORDER BY
                    g.es_posterior ASC,
                    CASE WHEN g.es_posterior = 0 THEN g.respuesta_ranking ELSE 0 END ASC,
                    CASE WHEN g.es_posterior = 0 THEN {_contacto_gestion_order_expr("g.contacto")} ELSE 0 END ASC,
                    CASE WHEN g.es_posterior = 0 THEN g.fecha_gestion END DESC,
                    CASE WHEN g.es_posterior = 0 THEN g.hora_gestion END DESC,
                    CASE WHEN g.es_posterior = 0 THEN g.id_gestion END DESC,
                    g.fecha_gestion ASC,
                    g.hora_gestion ASC,
                    g.id_gestion ASC
            ) AS rn
        FROM gestiones g
    )
    SELECT
        p.pago_id,
        p.contrato,
        p.rut,
        p.fecha_pago,
        p.tipo_pago,
        p.tipo_cartera,
        p.recupero,
        p.deuda,
        g.usuario,
        CASE WHEN g.pago_id IS NULL THEN NULL ELSE {_ejecutivo_expr("g.usuario", ejecutivas)} END AS ejecutivo,
        g.contacto,
        g.respuesta,
        g.fecha_gestion,
        g.hora_gestion,
        g.telefono,
        g.id_gestion,
        g.respuesta_ranking,
        CASE
            WHEN g.pago_id IS NULL THEN 'SIN GESTION'
            WHEN g.es_posterior = 0 THEN 'GESTION ANTES DEL PAGO'
            ELSE 'GESTION DESPUES DEL PAGO'
        END AS criterio,
        CASE WHEN UPPER(LTRIM(RTRIM(COALESCE(g.contacto, '')))) = 'CONTACTO DIRECTO' THEN 1 ELSE 0 END AS flag_titular
    INTO #base
    FROM #pagos p
    LEFT JOIN gestion_elegida g ON g.pago_id = p.pago_id AND g.rn = 1;
    """
    params: list = [selected_mes_proceso]
    params.extend([selected_mes_proceso] if c["mes_proceso_pago"] else [month_start, month_end])
    params.extend([month_start, month_end])
    return sql, params, period_month


def get_filtros(periodo: str | None = None) -> dict:
    p = _columns(PAGOS_TABLE)
    mes_proceso_pago = _pick_optional(p, ["mes_proceso", "periodo"])
    fecha_negocio_pago = _pick_optional(p, ["fecha_negocio", "fld_FECHA_NEGOCIO", "fld_FechaNegocio"])
    tipo_cartera = _pick_optional(p, ["fld_TIPO_CARTERA"])
    period_where = _mes_proceso_where("x")
    period_order = _mes_proceso_order_expr("x")
    if mes_proceso_pago:
        periodos_sql = f"""
            SELECT x.v
            FROM (
                SELECT DISTINCT LTRIM(RTRIM(CONVERT(varchar(20), p.{mes_proceso_pago}))) AS v
                FROM {PAGOS_TABLE} p
                WHERE p.{mes_proceso_pago} IS NOT NULL
            ) x
            WHERE {period_where}
            ORDER BY {period_order} DESC
        """
    elif fecha_negocio_pago:
        periodos_sql = f"""
            SELECT x.v
            FROM (
                SELECT DISTINCT
                    RIGHT('0' + CAST(MONTH({fecha_negocio_pago}) AS varchar(2)), 2) + '-' + CAST(YEAR({fecha_negocio_pago}) AS varchar(4)) AS v
                FROM {PAGOS_TABLE}
                WHERE {fecha_negocio_pago} IS NOT NULL
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
    tipos: list[str] = []
    if tipo_cartera:
        tipos_where = f"WHERE {tipo_cartera} IS NOT NULL"
        tipos_params: list[str] = []
        if selected_period and mes_proceso_pago:
            tipos_where += f" AND LTRIM(RTRIM(CONVERT(varchar(20), {mes_proceso_pago}))) = ?"
            tipos_params.append(selected_period)

        tipos = [
            r["v"]
            for r in run_query(
                f"""
                SELECT DISTINCT {_tipo_cartera_expr(tipo_cartera)} AS v
                FROM {PAGOS_TABLE}
                {tipos_where}
                ORDER BY v
                """,
                tuple(tipos_params),
            )
        ]

    return {
        "periodos": periodos,
        "carteras_crm": [CARTERA_CRM],
        "tipo_cartera": tipos,
        "ejecutivos": sorted(set(_ejecutivas(selected_period).values())) if selected_period else [],
    }


def _deuda_cte(periodo: str) -> tuple[str, list]:
    """CTE `deuda`: deuda asignada por cartera y ejecutivo. Requiere #mejor_gestion_mes y #base.

    El folio va a quien se llevo su pago mas reciente; si no tiene pago, a la mejor gestion del
    RUT en el mes (ranking de respuesta, contacto y la mas reciente). Sin gestion no se cuenta.
    """
    asig = _asignacion_cols()
    ejecutivas = _ejecutivas(periodo)
    sql = f"""
    mejor_gestion_mes AS (
        SELECT g.rut, g.usuario, g.contacto, g.respuesta, g.fecha_gestion, g.telefono, 1 AS rn
        FROM #mejor_gestion_mes g
    ),
    pago_contrato AS (
        SELECT
            base.contrato,
            base.ejecutivo,
            base.usuario,
            base.contacto,
            base.respuesta,
            base.fecha_gestion,
            base.telefono,
            ROW_NUMBER() OVER (PARTITION BY base.contrato ORDER BY base.fecha_pago DESC, base.pago_id DESC) AS rn
        FROM #base base
        WHERE base.ejecutivo IS NOT NULL
    ),
    deuda_folio AS (
        SELECT
            {_tipo_cartera_expr(f"a.{asig['tipo_cartera']}")} AS tipo_cartera,
            COALESCE(pc.ejecutivo, CASE WHEN mg.rut IS NULL THEN NULL ELSE {_ejecutivo_expr("mg.usuario", ejecutivas)} END) AS ejecutivo,
            COALESCE(CAST(a.{asig['deuda']} AS float), 0) AS deuda,
            CONVERT(varchar(100), a.{asig['folio']}) AS folio,
            CONVERT(varchar(50), a.{asig['rut']}) AS rut,
            CASE
                WHEN pc.contrato IS NOT NULL THEN 'PAGO DEL FOLIO'
                WHEN mg.rut IS NOT NULL THEN 'MEJOR GESTION DEL MES'
                ELSE 'SIN GESTION'
            END AS criterio,
            CASE WHEN pc.contrato IS NULL THEN mg.usuario END AS usuario_mejor_gestion,
            CASE WHEN pc.contrato IS NOT NULL THEN pc.usuario ELSE mg.usuario END AS usuario_gestion,
            CASE WHEN pc.contrato IS NOT NULL THEN pc.contacto ELSE mg.contacto END AS contacto_gestion,
            CASE WHEN pc.contrato IS NOT NULL THEN pc.respuesta ELSE mg.respuesta END AS respuesta_gestion,
            CASE WHEN pc.contrato IS NOT NULL THEN pc.fecha_gestion ELSE mg.fecha_gestion END AS fecha_gestion,
            CASE WHEN pc.contrato IS NOT NULL THEN pc.telefono ELSE mg.telefono END AS telefono
        FROM {ASIGNACION_TABLE} a
        LEFT JOIN pago_contrato pc ON pc.contrato = CONVERT(varchar(100), a.{asig['folio']}) AND pc.rn = 1
        LEFT JOIN mejor_gestion_mes mg ON mg.rut = CONVERT(varchar(50), a.{asig['rut']}) AND mg.rn = 1
        WHERE a.{asig['mes_proceso']} = ?
    ),
    deuda AS (
        SELECT d.tipo_cartera, d.ejecutivo, SUM(d.deuda) AS deuda
        FROM deuda_folio d
        WHERE d.ejecutivo IS NOT NULL
        GROUP BY d.tipo_cartera, d.ejecutivo
    )"""
    return sql, [_to_mes_proceso(periodo)]


def get_resumen(filters: dict) -> dict:
    c = _resolved_cols()
    periodo = str(filters.get("periodo") or "")
    base_sql, pre_params, _period_month = _atribucion_sql(c, periodo)
    deuda_sql, deuda_params = _deuda_cte(periodo)
    where = ["1 = 1"]
    params: list = []

    if filters.get("tipo_cartera"):
        where.append("UPPER(LTRIM(RTRIM(k.tipo_cartera))) = UPPER(LTRIM(RTRIM(?)))")
        params.append(str(filters["tipo_cartera"]))
    if filters.get("ejecutivo"):
        where.append("UPPER(LTRIM(RTRIM(k.ejecutivo))) = UPPER(LTRIM(RTRIM(?)))")
        params.append(str(filters["ejecutivo"]))

    where_sql = " AND ".join(where)
    sql = f"""{base_sql}
    WITH base AS (SELECT * FROM #base),{deuda_sql},
    resumen AS (
        SELECT
            base.tipo_cartera,
            base.ejecutivo,
            COUNT(DISTINCT base.contrato) AS q_folios,
            SUM(base.recupero) AS recupero,
            COUNT(DISTINCT CASE WHEN base.flag_titular = 1 THEN base.contrato END) AS q_titular
        FROM base
        WHERE base.ejecutivo IS NOT NULL
        GROUP BY base.tipo_cartera, base.ejecutivo
    ),
    aporte AS (
        SELECT
            base.tipo_cartera,
            SUM(base.recupero) AS recupero_total
        FROM base
        WHERE base.ejecutivo IS NOT NULL
        GROUP BY base.tipo_cartera
    ),
    aporte_final AS (
        SELECT
            base.ejecutivo,
            SUM(base.recupero) AS recupero_ejecutivo,
            SUM(SUM(base.recupero)) OVER () AS recupero_total
        FROM base
        WHERE base.ejecutivo IS NOT NULL
        GROUP BY base.ejecutivo
    ),
    claves AS (
        SELECT tipo_cartera, ejecutivo FROM resumen
        UNION
        SELECT tipo_cartera, ejecutivo FROM deuda
    )
    SELECT
        k.ejecutivo,
        k.tipo_cartera,
        COALESCE(r.q_folios, 0) AS q_folios,
        COALESCE(d.deuda, 0) AS deuda,
        COALESCE(r.recupero, 0) AS recupero,
        COALESCE(r.q_titular, 0) AS q_titular,
        CASE WHEN COALESCE(r.q_folios, 0) = 0 THEN 0 ELSE CAST(r.q_titular AS float) / r.q_folios END AS pct_contacto_titular,
        CASE
            WHEN a.recupero_total IS NULL OR a.recupero_total = 0 THEN 0
            ELSE CAST(COALESCE(r.recupero, 0) AS float) / a.recupero_total
        END AS pct_aporte,
        CASE
            WHEN af.recupero_total IS NULL OR af.recupero_total = 0 THEN 0
            ELSE CAST(af.recupero_ejecutivo AS float) / af.recupero_total
        END AS pct_aporte_final
    FROM claves k
    LEFT JOIN resumen r ON r.tipo_cartera = k.tipo_cartera AND r.ejecutivo = k.ejecutivo
    LEFT JOIN deuda d ON d.tipo_cartera = k.tipo_cartera AND d.ejecutivo = k.ejecutivo
    LEFT JOIN aporte a ON a.tipo_cartera = k.tipo_cartera
    LEFT JOIN aporte_final af ON af.ejecutivo = k.ejecutivo
    WHERE {where_sql}
    ORDER BY
        CASE k.tipo_cartera WHEN '+365' THEN 1 WHEN 'CASTIGO' THEN 2 WHEN 'VIGENTE' THEN 3 ELSE 9 END,
        CASE WHEN k.ejecutivo = 'PHOENIX' THEN 1 ELSE 0 END,
        k.ejecutivo
    """

    rows = run_query_sets(sql, tuple(pre_params + deuda_params + params))[-1]
    total_folios = sum(int(r["q_folios"] or 0) for r in rows)
    total_deuda = sum(float(r["deuda"] or 0) for r in rows)
    total_recupero = sum(float(r["recupero"] or 0) for r in rows)
    total_titular = sum(int(r["q_titular"] or 0) for r in rows)
    # El aporte final se repite en cada cartera del ejecutivo: se suma una vez por ejecutivo.
    total_aporte_final = sum({r["ejecutivo"]: float(r["pct_aporte_final"] or 0) for r in rows}.values())

    total = {
        "ejecutivo": "Total general",
        "q_folios": total_folios,
        "deuda": total_deuda,
        "recupero": total_recupero,
        "q_titular": total_titular,
        "pct_contacto_titular": None,
        "pct_aporte": None,
        "pct_aporte_final": total_aporte_final,
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


def get_negocios(filters: dict) -> dict:
    """Negocios del mes (pagos NE-REPRO) asignados a la ejecutiva de la mejor gestion del RUT.

    Usa la misma regla de atribucion que el recupero. Los negocios sin gestion en el mes se
    cuentan en PHOENIX; `sin_gestion` informa cuantos son.
    """
    c = _resolved_cols()
    periodo = str(filters.get("periodo") or "")
    base_sql, base_params, _period_month = _atribucion_sql(c, periodo, TIPOS_PAGO_NEGOCIO, solo_ruts_con_pago=True)
    where = ["1 = 1"]
    params: list = []
    if filters.get("ejecutivo"):
        where.append("UPPER(LTRIM(RTRIM(b.ejecutivo))) = UPPER(LTRIM(RTRIM(?)))")
        params.append(str(filters["ejecutivo"]))
    where_sql = " AND ".join(where)

    # Tramo segun la deuda asignada del folio; un folio sin asignacion cae en el tramo menor.
    tramo = f"CASE WHEN COALESCE(b.deuda, 0) <= {TRAMO_DEUDA_NEGOCIO} THEN 'MENOR' ELSE 'MAYOR' END"
    negocios = "(SELECT contrato, rut, tipo_cartera, fecha_pago, deuda, recupero, COALESCE(ejecutivo, 'PHOENIX') AS ejecutivo FROM #base)"
    sql = f"""{base_sql}
    SELECT
        b.ejecutivo,
        {tramo} AS tramo_deuda,
        COUNT(*) AS q_negocios,
        SUM(b.recupero) AS recupero
    FROM {negocios} b
    WHERE {where_sql}
    GROUP BY b.ejecutivo, {tramo}
    ORDER BY CASE WHEN b.ejecutivo = 'PHOENIX' THEN 1 ELSE 0 END, b.ejecutivo;

    SELECT
        b.contrato,
        b.rut,
        b.tipo_cartera,
        b.fecha_pago,
        b.deuda,
        b.recupero,
        {tramo} AS tramo_deuda,
        b.ejecutivo
    FROM {negocios} b
    WHERE {where_sql}
    ORDER BY CASE WHEN b.ejecutivo = 'PHOENIX' THEN 1 ELSE 0 END, b.ejecutivo, b.fecha_pago, b.contrato;

    SELECT COUNT(*) AS q_negocios, COALESCE(SUM(b.recupero), 0) AS monto
    FROM #base b
    WHERE b.ejecutivo IS NULL;
    """
    rows, detalle, sin_gestion = run_query_sets(sql, tuple(base_params + params + params))[-3:]
    return {
        "rows": rows,
        "detalle": detalle,
        "sin_gestion": sin_gestion[0] if sin_gestion else {"q_negocios": 0, "monto": 0},
        "tipos_pago": TIPOS_PAGO_NEGOCIO,
    }


# Detalle por folio ya calculado, por mes de proceso: (momento de carga, filas).
# Paginar, buscar o filtrar dentro del mismo mes no vuelve a consultar la base.
_DETALLE_CACHE: dict[str, tuple[float, list[dict]]] = {}
_DETALLE_CACHE_SEGUNDOS = 300


def _detalle_folios(periodo: str) -> list[dict]:
    """Una fila por folio asignado en el mes, con su recupero y la gestion que se lo lleva."""
    mes_proceso = _to_mes_proceso(periodo)
    cached = _DETALLE_CACHE.get(mes_proceso)
    if cached and time.monotonic() - cached[0] < _DETALLE_CACHE_SEGUNDOS:
        return cached[1]

    c = _resolved_cols()
    base_sql, base_params, _period_month = _atribucion_sql(c, periodo)
    deuda_sql, deuda_params = _deuda_cte(periodo)
    sql = f"""{base_sql}
    WITH {deuda_sql.lstrip()},
    recupero_folio AS (
        SELECT base.contrato, SUM(base.recupero) AS recupero
        FROM #base base
        GROUP BY base.contrato
    )
    SELECT
        d.folio,
        d.rut,
        d.tipo_cartera,
        d.deuda,
        COALESCE(r.recupero, 0) AS recupero,
        d.ejecutivo,
        d.usuario_gestion,
        d.contacto_gestion,
        d.respuesta_gestion,
        d.fecha_gestion,
        d.telefono
    FROM deuda_folio d
    LEFT JOIN recupero_folio r ON r.contrato = d.folio
    ORDER BY COALESCE(r.recupero, 0) DESC, d.deuda DESC, d.folio;
    """
    rows = run_query_sets(sql, tuple(base_params + deuda_params))[-1]
    _DETALLE_CACHE[mes_proceso] = (time.monotonic(), rows)
    return rows


def get_detalle(filters: dict) -> dict:
    """Detalle paginado de los folios asignados en el mes. Los filtros se aplican en memoria."""
    rows = _detalle_folios(str(filters.get("periodo") or ""))
    usuarios = sorted({str(r["usuario_gestion"]).strip().upper() for r in rows if r["usuario_gestion"]})

    def norm(value) -> str:
        return str(value or "").strip().upper()

    buscar = norm(filters.get("buscar"))
    tipo_cartera = norm(filters.get("tipo_cartera"))
    ejecutivo = norm(filters.get("ejecutivo"))
    usuario = norm(filters.get("usuario_gestion"))
    con_pago = str(filters.get("con_pago") or "").strip()
    if buscar:
        rows = [r for r in rows if buscar in norm(r["folio"]) or buscar in norm(r["rut"])]
    if tipo_cartera:
        rows = [r for r in rows if norm(r["tipo_cartera"]) == tipo_cartera]
    if ejecutivo:
        rows = [r for r in rows if norm(r["ejecutivo"]) == ejecutivo]
    if usuario:
        rows = [r for r in rows if norm(r["usuario_gestion"]) == usuario]
    if con_pago in ("0", "1"):
        rows = [r for r in rows if (float(r["recupero"] or 0) != 0) == (con_pago == "1")]

    page = max(1, int(filters.get("page") or 1))
    page_size = max(1, min(500, int(filters.get("page_size") or 100)))
    start = (page - 1) * page_size
    return {
        "data": rows[start : start + page_size],
        "total": len(rows),
        "page": page,
        "page_size": page_size,
        "usuarios_gestion": usuarios,
    }


def get_validacion(periodo: str) -> dict:
    c = _resolved_cols()
    base_sql, params, _period_month = _atribucion_sql(c, periodo)
    sql = f"""{base_sql}
    SELECT
        COUNT(*) AS pagos_validos,
        SUM(recupero) AS recupero_pagos_validos,
        SUM(CASE WHEN criterio = 'GESTION ANTES DEL PAGO' THEN 1 ELSE 0 END) AS pagos_gestion_antes,
        SUM(CASE WHEN criterio = 'GESTION ANTES DEL PAGO' THEN recupero ELSE 0 END) AS recupero_gestion_antes,
        SUM(CASE WHEN criterio = 'GESTION DESPUES DEL PAGO' THEN 1 ELSE 0 END) AS pagos_gestion_despues,
        SUM(CASE WHEN criterio = 'GESTION DESPUES DEL PAGO' THEN recupero ELSE 0 END) AS recupero_gestion_despues,
        SUM(CASE WHEN criterio = 'SIN GESTION' THEN 1 ELSE 0 END) AS pagos_sin_gestion,
        SUM(CASE WHEN criterio = 'SIN GESTION' THEN recupero ELSE 0 END) AS recupero_sin_gestion,
        SUM(CASE WHEN criterio <> 'SIN GESTION' THEN recupero ELSE 0 END) AS recupero_incluido_resumen,
        SUM(CASE WHEN fecha_pago IS NULL THEN 1 ELSE 0 END) AS pagos_sin_fecha_pago
    FROM #base
    """
    row = run_query_sets(sql, tuple(params))[-1][0]
    row["tipos_pago_validos"] = TIPOS_PAGO_VALIDOS
    return row
