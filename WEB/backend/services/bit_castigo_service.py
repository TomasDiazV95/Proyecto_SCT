from __future__ import annotations

from datetime import date, timedelta

from database import run_query
from feriados_chile import es_habil


# Cartera Banco Internacional en el CRM de gestiones (dbo.tmp_GEST_CRM).
CRM_CARTERA = 532
DIAS_HABILES_COBERTURA = 4


def _dia_habil_del_mes(periodo: str, n: int) -> str:
    """Fecha ISO del n-esimo dia habil del mes del periodo (YYYY-MM)."""
    cursor = date.fromisoformat(f"{periodo[:7]}-01")
    habiles = 0
    while True:
        if es_habil(cursor):
            habiles += 1
            if habiles == n:
                return cursor.isoformat()
        cursor += timedelta(days=1)


def _clean_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _safe_float(value: object) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_div(num: float, den: float) -> float:
    if den is None or den == 0:
        return 0.0
    return num / den


def _safe_avg(values: list[float]) -> float:
    clean = [float(value) for value in values if value is not None]
    if not clean:
        return 0.0
    return sum(clean) / len(clean)


def _cap_cumpl_meta(value: float) -> float:
    return min(float(value or 0), 1.3)


def _resolve_period(periodo: str | None) -> str:
    text = _clean_text(periodo)
    if text:
        return text[:7]

    rows = run_query(
        """
        SELECT TOP 1 periodo
        FROM dbo.tmp_BIT_castigo
        WHERE periodo IS NOT NULL
          AND LTRIM(RTRIM(periodo)) <> ''
        GROUP BY periodo
        ORDER BY periodo DESC
        """
    )
    resolved = _clean_text(rows[0].get("periodo")) if rows else ""
    if not resolved:
        raise RuntimeError("No hay periodos disponibles para BIT Castigo")
    return resolved


def _list_table_columns(table_name: str) -> list[str]:
    rows = run_query(
        """
        SELECT COLUMN_NAME
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = 'dbo'
          AND TABLE_NAME = ?
        ORDER BY ORDINAL_POSITION
        """,
        (table_name,),
    )
    return [_clean_text(row.get("COLUMN_NAME")) for row in rows if _clean_text(row.get("COLUMN_NAME"))]


def _first_existing_column(table_name: str, candidates: list[str], contains_any: list[str] | None = None) -> str:
    columns = _list_table_columns(table_name)
    existing = {column.upper(): column for column in columns}
    for candidate in candidates:
        match = existing.get(candidate.upper())
        if match:
            return match

    contains_any = [item.upper() for item in (contains_any or [])]
    for column in columns:
        col_upper = column.upper()
        if any(token in col_upper for token in contains_any):
            return column

    expected = ", ".join(candidates + (contains_any or []))
    raise RuntimeError(f"No se encontro ninguna columna esperada en dbo.{table_name}: {expected}")


def _optional_existing_column(table_name: str, candidates: list[str], contains_any: list[str] | None = None) -> str:
    try:
        return _first_existing_column(table_name, candidates, contains_any)
    except RuntimeError:
        return ""


def _rut_key_sql(expr: str) -> str:
    return (
        "UPPER(LTRIM(RTRIM(REPLACE(REPLACE(REPLACE(COALESCE(CONVERT(VARCHAR(50), "
        f"{expr}"
        "), ''), '.', ''), '-', ''), ' ', ''))))"
    )


def _rut_join_key_sql(expr: str) -> str:
    cleaned = (
        "UPPER(LTRIM(RTRIM(REPLACE(REPLACE(COALESCE(CONVERT(VARCHAR(50), "
        f"{expr}"
        "), ''), '.', ''), ' ', ''))))"
    )
    return (
        "CASE "
        f"WHEN CHARINDEX('-', {cleaned}) > 0 THEN LEFT({cleaned}, CHARINDEX('-', {cleaned}) - 1) "
        f"WHEN LEN({cleaned}) >= 9 THEN LEFT({cleaned}, LEN({cleaned}) - 1) "
        f"ELSE {cleaned} "
        "END"
    )


def _cart_config() -> dict[str, str]:
    return {
        "rut_col": _first_existing_column(
            "tmp_BIT_carterizado",
            ["rut", "RUT", "rut_deudor", "rut_asignado", "fld_rut", "fld_rut_asignado"],
            contains_any=["RUT"],
        ),
        "usuario_col": _first_existing_column(
            "tmp_BIT_carterizado",
            ["usuario", "USUARIO", "usuario_ejecutivo", "ejecutivo", "nombre_ejecutivo"],
            contains_any=["USUARIO", "EJECUTIVO"],
        ),
        "cartera_col": _optional_existing_column(
            "tmp_BIT_carterizado",
            ["cartera", "CARTERA"],
            contains_any=["CARTERA"],
        ),
    }


def _castigo_config() -> dict[str, str]:
    return {
        "rut_col": _first_existing_column(
            "tmp_BIT_castigo",
            ["rut", "RUT"],
            contains_any=["RUT"],
        ),
        "total_rut_col": _first_existing_column(
            "tmp_BIT_castigo",
            ["total_rut", "TOTAL_RUT"],
            contains_any=["TOTAL_RUT"],
        ),
        "recupero_col": _first_existing_column(
            "tmp_BIT_castigo",
            ["mto_recupero_final", "MTO_RECUPERO_FINAL"],
            contains_any=["MTO_RECUPERO_FINAL"],
        ),
        "periodo_col": _first_existing_column(
            "tmp_BIT_castigo",
            ["periodo", "PERIODO"],
            contains_any=["PERIODO"],
        ),
        "source_file_col": _first_existing_column(
            "tmp_BIT_castigo",
            ["source_file", "SOURCE_FILE"],
            contains_any=["SOURCE_FILE"],
        ),
        "tipo_col": _optional_existing_column("tmp_BIT_castigo", ["TIPO", "tipo"]),
    }


def _asignacion_table() -> str:
    # Consolidado mensual (todo RUT asignado algun dia del mes, con su ultima deuda); si el ETL aun no lo
    # ha creado en el ambiente, se usa la asignacion de cierre.
    if _list_table_columns("tmp_BIT_asignacion_mensual"):
        return "dbo.tmp_BIT_asignacion_mensual"
    return "dbo.tmp_BIT_asignacion"


def _meta_source_sql() -> str:
    return """
    SELECT
        periodo,
        CAST(meta AS float) AS meta
    FROM (
        SELECT
            periodo,
            tramo,
            meta,
            ROW_NUMBER() OVER (
                PARTITION BY periodo, UPPER(LTRIM(RTRIM(COALESCE(tramo, ''))))
                ORDER BY periodo DESC
            ) AS rn
        FROM [bdphoenixconsultas].[dbo].[tmp_BIT_metas]
        WHERE UPPER(LTRIM(RTRIM(COALESCE(tramo, '')))) = 'CASTIGO'
    ) src
    WHERE rn = 1
    """


def _meta_source_sql_fallback() -> str:
    return """
    SELECT
        periodo,
        CAST(meta AS float) AS meta
    FROM (
        SELECT
            periodo,
            tramo,
            meta,
            ROW_NUMBER() OVER (
                PARTITION BY periodo, UPPER(LTRIM(RTRIM(COALESCE(tramo, ''))))
                ORDER BY periodo DESC
            ) AS rn
        FROM dbo.tmp_BIT_metas
        WHERE UPPER(LTRIM(RTRIM(COALESCE(tramo, '')))) = 'CASTIGO'
    ) src
    WHERE rn = 1
    """


def _hay_gestiones_desde(inicio: str) -> bool:
    # El CRM solo tiene gestiones desde cierta fecha: si no cubre el inicio del mes no hay cobertura que medir.
    rows = run_query(
        "SELECT CONVERT(char(10), MIN(GestionFecha), 126) AS primera FROM dbo.tmp_GEST_CRM WHERE cartera = ?",
        (CRM_CARTERA,),
    )
    primera = _clean_text(rows[0].get("primera")) if rows else ""
    return bool(primera) and primera <= inicio


def _bit_castigo_cte(meta_sql: str, cobertura: tuple[str, str] | None = None) -> str:
    # cobertura = (inicio, corte): ventana de gestiones para la cobertura al dia habil de corte.
    # Las fechas las calcula el servicio (ISO), no vienen del usuario.
    if cobertura:
        gestiones_cte = f"""
), gestiones_rut AS (
    -- RUT con al menos una gestion telefonica o en terreno hasta el dia habil de corte.
    SELECT DISTINCT {_rut_join_key_sql("g.rut")} AS rut_key
    FROM dbo.tmp_GEST_CRM g
    INNER JOIN dbo.kpi_accion_canal ac
        ON ac.valor = UPPER(LTRIM(RTRIM(g.AccionGestion)))
       AND ac.canal IN ('LLAMADA', 'TERRENO')
    WHERE g.cartera = {CRM_CARTERA}
      AND g.GestionFecha >= '{cobertura[0]}'
      AND g.GestionFecha <= '{cobertura[1]}'"""
        gestionado_sql = "CASE WHEN ge.rut_key IS NOT NULL THEN 1 ELSE 0 END"
        gestiones_join = """
    LEFT JOIN gestiones_rut ge
        ON ge.rut_key = k.rut_key"""
    else:
        gestiones_cte = ""
        gestionado_sql = "0"
        gestiones_join = ""
    cart = _cart_config()
    cast = _castigo_config()
    cart_rut = f"c.{cart['rut_col']}"
    cart_usuario = f"c.{cart['usuario_col']}"
    cart_cartera = f"c.{cart['cartera_col']}" if cart.get("cartera_col") else ""
    cast_rut = cast["rut_col"]
    cast_total_rut = cast["total_rut_col"]
    cast_recupero = cast["recupero_col"]
    cast_periodo = cast["periodo_col"]
    # Nuevos convenios: registros del recupero cuyo TIPO es 'Nuevo Convenio'.
    nuevos_convenios_sql = (
        f"SUM(CASE WHEN UPPER(LTRIM(RTRIM(COALESCE(CONVERT(VARCHAR(100), {cast['tipo_col']}), '')))) = 'NUEVO CONVENIO' THEN 1 ELSE 0 END)"
        if cast.get("tipo_col")
        else "0"
    )
    # Abono inicial: recupero de esos mismos registros 'Nuevo Convenio'.
    abono_inicial_sql = (
        f"""SUM(CASE
            WHEN UPPER(LTRIM(RTRIM(COALESCE(CONVERT(VARCHAR(100), {cast['tipo_col']}), '')))) <> 'NUEVO CONVENIO' THEN 0
            WHEN {cast_recupero} IS NULL THEN 0
            WHEN ISNUMERIC(CONVERT(VARCHAR(255), {cast_recupero})) = 1 THEN CAST({cast_recupero} AS float)
            ELSE 0
        END)"""
        if cast.get("tipo_col")
        else "0"
    )
    cartera_filter = (
        f"""
          AND UPPER(LTRIM(RTRIM(COALESCE(CONVERT(VARCHAR(100), {cart_cartera}), '')))) = 'CASTIGO'
        """
        if cart_cartera
        else ""
    )
    return f"""
WITH carterizado_unico AS (
    SELECT
        periodo,
        rut_key,
        usuario,
        ROW_NUMBER() OVER (
            PARTITION BY periodo, rut_key
            ORDER BY id ASC
        ) AS rn
    FROM (
        SELECT
            periodo,
            {cart_usuario} AS usuario,
            {_rut_join_key_sql(cart_rut)} AS rut_key,
            id
        FROM dbo.tmp_BIT_carterizado c
        WHERE {cart_rut} IS NOT NULL
          AND LTRIM(RTRIM(COALESCE(CONVERT(VARCHAR(50), {cart_rut}), ''))) <> ''
          {cartera_filter}
    ) src
), metas_periodo AS (
    {meta_sql}
), castigo_rut AS (
    SELECT
        {cast_periodo} AS periodo,
        {_rut_join_key_sql(cast_rut)} AS rut_key,
        MAX(CASE
            WHEN {cast_total_rut} IS NULL THEN 0
            WHEN ISNUMERIC(CONVERT(VARCHAR(255), {cast_total_rut})) = 1 THEN CAST({cast_total_rut} AS float)
            ELSE 0
        END) AS total_rut,
        SUM(CASE
            WHEN {cast_recupero} IS NULL THEN 0
            WHEN ISNUMERIC(CONVERT(VARCHAR(255), {cast_recupero})) = 1 THEN CAST({cast_recupero} AS float)
            ELSE 0
        END) AS mto_recupero_final,
        {nuevos_convenios_sql} AS nuevos_convenios,
        {abono_inicial_sql} AS abono_inicial
    FROM dbo.tmp_BIT_castigo
    WHERE {cast_periodo} IS NOT NULL
      AND LTRIM(RTRIM({cast_periodo})) <> ''
      AND {cast_rut} IS NOT NULL
      AND LTRIM(RTRIM(COALESCE(CONVERT(VARCHAR(50), {cast_rut}), ''))) <> ''
    GROUP BY
        {cast_periodo},
        {_rut_join_key_sql(cast_rut)}
), asignacion_rut AS (
    SELECT
        periodo,
        {_rut_join_key_sql("RUT")} AS rut_key,
        -- La deuda asignada es solo la de campañas castigo; la cobertura no mira la campaña.
        SUM(CASE WHEN UPPER(LTRIM(RTRIM(COALESCE(CAMPANA, '')))) LIKE 'CASTIGO%' THEN COALESCE(CAST(DEUDA_TOTAL AS float), 0) ELSE 0 END) AS mto_asignado,
        MAX(CASE WHEN UPPER(LTRIM(RTRIM(COALESCE(CAMPANA, '')))) LIKE 'CASTIGO%' THEN 1 ELSE 0 END) AS es_castigo
    FROM {_asignacion_table()}
    WHERE RUT IS NOT NULL
      AND LTRIM(RTRIM(RUT)) <> ''
    GROUP BY
        periodo,
        {_rut_join_key_sql("RUT")}
), bit_castigo_data AS (
    SELECT
        b.periodo,
        b.rut_key AS rut,
        COALESCE(cu.usuario, 'Phoenix') AS carterizado,
        COALESCE(cu.usuario, 'Phoenix') AS ejecutivo,
        COALESCE(m.meta, 0) AS meta,
        b.total_rut AS mto_inicial,
        b.mto_recupero_final AS mto_contenido,
        b.nuevos_convenios,
        b.abono_inicial,
        COALESCE(m.meta, 0) AS meta_final
    FROM castigo_rut b
    LEFT JOIN carterizado_unico cu
        ON cu.periodo = b.periodo
       AND cu.rut_key = b.rut_key
       AND cu.rn = 1
    LEFT JOIN metas_periodo m
        ON m.periodo = b.periodo{gestiones_cte}
), bit_asignacion_data AS (
    -- Efectividad sobre lo asignado: base = asignacion castigo, cruzada por RUT con el recupero y el carterizado.
    -- Cobertura: base = carterizado de castigo (asignacion RIGHT JOIN carterizado), sin filtrar por campaña.
    SELECT
        k.periodo,
        k.rut_key AS rut,
        COALESCE(cu.usuario, 'Phoenix') AS ejecutivo,
        COALESCE(a.mto_asignado, 0) AS mto_asignado,
        CASE WHEN a.es_castigo = 1 THEN COALESCE(r.mto_recupero_final, 0) ELSE 0 END AS mto_recupero_asignado,
        CASE WHEN cu.rut_key IS NOT NULL THEN 1 ELSE 0 END AS rut_asignado,
        CASE WHEN cu.rut_key IS NOT NULL THEN {gestionado_sql} ELSE 0 END AS rut_gestionado,
        COALESCE(m.meta, 0) AS meta_final
    FROM asignacion_rut a
    FULL JOIN (SELECT periodo, rut_key, usuario FROM carterizado_unico WHERE rn = 1) cu
        ON cu.periodo = a.periodo
       AND cu.rut_key = a.rut_key
    CROSS APPLY (SELECT COALESCE(cu.periodo, a.periodo) AS periodo, COALESCE(cu.rut_key, a.rut_key) AS rut_key) k
    LEFT JOIN castigo_rut r
        ON r.periodo = k.periodo
       AND r.rut_key = k.rut_key{gestiones_join}
    LEFT JOIN metas_periodo m
        ON m.periodo = k.periodo
    WHERE a.es_castigo = 1
       OR cu.rut_key IS NOT NULL
)
"""


def _get_source_file(periodo: str) -> str:
    cast = _castigo_config()
    cast_periodo = cast["periodo_col"]
    cast_source_file = cast["source_file_col"]
    rows = run_query(
        """
        SELECT TOP 1 """ + cast_source_file + """
        FROM dbo.tmp_BIT_castigo
        WHERE """ + cast_periodo + """ = ?
          AND """ + cast_source_file + """ IS NOT NULL
          AND LTRIM(RTRIM(""" + cast_source_file + """)) <> ''
        GROUP BY """ + cast_source_file + """
        ORDER BY COUNT(1) DESC, """ + cast_source_file + """ DESC
        """,
        (periodo,),
    )
    return _clean_text(rows[0].get(cast_source_file)) if rows else ""


def _base_where(filters: dict) -> tuple[str, list]:
    clauses = ["periodo = ?"]
    params: list = [_resolve_period(filters.get("periodo"))]

    ejecutivo = _clean_text(filters.get("ejecutivo"))
    if ejecutivo:
        clauses.append("UPPER(LTRIM(RTRIM(ejecutivo))) = UPPER(LTRIM(RTRIM(?)))")
        params.append(ejecutivo)

    return " AND ".join(clauses), params


def get_filter_values(periodo: str | None = None) -> dict:
    cast = _castigo_config()
    cast_periodo = cast["periodo_col"]
    periodos = [
        row["v"]
        for row in run_query(
            """
            SELECT DISTINCT """ + cast_periodo + """ AS v
            FROM dbo.tmp_BIT_castigo
            WHERE """ + cast_periodo + """ IS NOT NULL
              AND LTRIM(RTRIM(""" + cast_periodo + """)) <> ''
            ORDER BY v DESC
            """
        )
        if row.get("v")
    ]

    try:
        sql = f"""
        {_bit_castigo_cte(_meta_source_sql())}
        SELECT DISTINCT LTRIM(RTRIM(ejecutivo)) AS v
        FROM (
            SELECT periodo, ejecutivo FROM bit_castigo_data
            -- UNION ALL: el DISTINCT de afuera ya deduplica, y con UNION el plan pasa de <1s a ~40s.
            UNION ALL
            SELECT periodo, ejecutivo FROM bit_asignacion_data
        ) src
        WHERE ejecutivo IS NOT NULL
          AND LTRIM(RTRIM(ejecutivo)) <> ''
          {"AND periodo = ?" if periodo else ""}
        ORDER BY v
        """
        params = (_resolve_period(periodo),) if periodo else ()
        ejecutivos = [row["v"] for row in run_query(sql, params) if row.get("v")]
    except Exception:
        # Si el cruce con carterizado o dotacion falla por columnas distintas
        # entre ambientes, no bloqueamos la carga inicial de la pantalla.
        ejecutivos = []

    return {"periodos": periodos, "ejecutivos": ejecutivos}


def get_general(filters: dict) -> dict:
    periodo = _resolve_period(filters.get("periodo"))
    where_sql, params = _base_where(filters)
    sql_body = f"""
    SELECT
        ejecutivo,
        SUM(COALESCE(CAST(mto_inicial AS float), 0)) AS monto_inicial,
        SUM(COALESCE(CAST(mto_contenido AS float), 0)) AS monto_contenido,
        MAX(COALESCE(CAST(meta_final AS float), 0)) AS meta_final,
        SUM(COALESCE(CAST(mto_asignado AS float), 0)) AS monto_asignado,
        SUM(COALESCE(CAST(mto_recupero_asignado AS float), 0)) AS recupero_asignado,
        SUM(COALESCE(nuevos_convenios, 0)) AS nuevos_convenios,
        SUM(COALESCE(CAST(abono_inicial AS float), 0)) AS abono_inicial,
        SUM(ruts_asignados) AS ruts_asignados,
        SUM(ruts_gestionados) AS ruts_gestionados
    FROM (
        SELECT periodo, ejecutivo, mto_inicial, mto_contenido, meta_final,
               0 AS mto_asignado, 0 AS mto_recupero_asignado, nuevos_convenios, abono_inicial,
               0 AS ruts_asignados, 0 AS ruts_gestionados
        FROM bit_castigo_data
        UNION ALL
        SELECT periodo, ejecutivo, 0, 0, meta_final,
               mto_asignado, mto_recupero_asignado, 0, 0,
               rut_asignado, rut_gestionado
        FROM bit_asignacion_data
    ) src
    WHERE {where_sql}
    GROUP BY ejecutivo
    ORDER BY CASE WHEN ejecutivo = 'Phoenix' THEN 2 ELSE 1 END, ejecutivo
    """
    corte_cobertura = _dia_habil_del_mes(periodo, DIAS_HABILES_COBERTURA)
    hay_cobertura = _hay_gestiones_desde(f"{periodo[:7]}-01")
    attempts = [
        _meta_source_sql,
        _meta_source_sql_fallback,
    ]
    last_error: Exception | None = None
    agg_rows = None
    for meta_sql_builder in attempts:
        try:
            cte_sql = _bit_castigo_cte(meta_sql_builder(), (f"{periodo[:7]}-01", corte_cobertura))
            agg_rows = run_query(f"{cte_sql}\n{sql_body}", tuple(params))
            last_error = None
            break
        except Exception as exc:
            last_error = exc
    if agg_rows is None:
        raise last_error if last_error is not None else RuntimeError("No se pudo cargar la vista general de BIT Castigo")

    rows: list[dict] = []
    total_inicial = 0.0
    total_contenido = 0.0
    total_asignado = 0.0
    total_recupero_asignado = 0.0
    total_nuevos_convenios = 0
    total_abono_inicial = 0.0
    total_ruts_asignados = 0
    total_ruts_gestionados = 0
    meta_periodo = 0.0

    for row in agg_rows:
        monto_inicial = _safe_float(row.get("monto_inicial"))
        monto_contenido = _safe_float(row.get("monto_contenido"))
        meta_final = _safe_float(row.get("meta_final"))
        monto_asignado = _safe_float(row.get("monto_asignado"))
        recupero_asignado = _safe_float(row.get("recupero_asignado"))
        nuevos_convenios = int(_safe_float(row.get("nuevos_convenios")))
        abono_inicial = _safe_float(row.get("abono_inicial"))
        ruts_asignados = int(_safe_float(row.get("ruts_asignados")))
        ruts_gestionados = int(_safe_float(row.get("ruts_gestionados")))
        pct_contencion = _safe_div(monto_contenido, monto_inicial)
        pct_cumpl_meta = _cap_cumpl_meta(_safe_div(monto_contenido, meta_final))

        rows.append(
            {
                "ejecutivo": row.get("ejecutivo") or "Phoenix",
                "monto_inicial": monto_inicial,
                "monto_contenido": monto_contenido,
                "pct_contencion": pct_contencion,
                "pct_contiene": pct_contencion,
                "pct_cumpl_meta": pct_cumpl_meta,
                "monto_asignado": monto_asignado,
                "recupero_asignado": recupero_asignado,
                "pct_efectividad": _safe_div(recupero_asignado, monto_asignado),
                "nuevos_convenios": nuevos_convenios,
                "abono_inicial": abono_inicial,
                "ruts_asignados": ruts_asignados,
                "ruts_gestionados": ruts_gestionados,
                "pct_cobertura": _safe_div(ruts_gestionados, ruts_asignados) if hay_cobertura else None,
            }
        )

        total_inicial += monto_inicial
        total_contenido += monto_contenido
        total_asignado += monto_asignado
        total_recupero_asignado += recupero_asignado
        total_nuevos_convenios += nuevos_convenios
        total_abono_inicial += abono_inicial
        total_ruts_asignados += ruts_asignados
        total_ruts_gestionados += ruts_gestionados
        meta_periodo = max(meta_periodo, meta_final)

    return {
        "periodo": periodo,
        "corte_cobertura": corte_cobertura,
        "contencion_file": _get_source_file(periodo),
        # Meta de recupero del periodo (tramo CASTIGO en tmp_BIT_metas), en pesos.
        "meta": meta_periodo or None,
        "rows": rows,
        "total": {
            "ejecutivo": "Total general",
            "monto_inicial": total_inicial,
            "monto_contenido": total_contenido,
            "pct_contencion": _safe_div(total_contenido, total_inicial),
            "pct_contiene": _safe_div(total_contenido, total_inicial),
            "pct_cumpl_meta": _cap_cumpl_meta(_safe_div(total_contenido, meta_periodo)),
            "monto_asignado": total_asignado,
            "recupero_asignado": total_recupero_asignado,
            "pct_efectividad": _safe_div(total_recupero_asignado, total_asignado),
            "nuevos_convenios": total_nuevos_convenios,
            "abono_inicial": total_abono_inicial,
            "ruts_asignados": total_ruts_asignados,
            "ruts_gestionados": total_ruts_gestionados,
            "pct_cobertura": _safe_div(total_ruts_gestionados, total_ruts_asignados) if hay_cobertura else None,
        },
    }
