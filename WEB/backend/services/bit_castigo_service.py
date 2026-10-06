from __future__ import annotations

from database import run_query


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


def _bit_castigo_cte(meta_sql: str) -> str:
    cart = _cart_config()
    cast = _castigo_config()
    cart_rut = f"c.{cart['rut_col']}"
    cart_usuario = f"c.{cart['usuario_col']}"
    cart_cartera = f"c.{cart['cartera_col']}" if cart.get("cartera_col") else ""
    cast_rut = cast["rut_col"]
    cast_total_rut = cast["total_rut_col"]
    cast_recupero = cast["recupero_col"]
    cast_periodo = cast["periodo_col"]
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
        END) AS mto_recupero_final
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
        SUM(COALESCE(CAST(DEUDA_TOTAL AS float), 0)) AS mto_asignado
    FROM {_asignacion_table()}
    WHERE UPPER(LTRIM(RTRIM(COALESCE(CAMPANA, '')))) LIKE 'CASTIGO%'
      AND RUT IS NOT NULL
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
        COALESCE(m.meta, 0) AS meta_final
    FROM castigo_rut b
    LEFT JOIN carterizado_unico cu
        ON cu.periodo = b.periodo
       AND cu.rut_key = b.rut_key
       AND cu.rn = 1
    LEFT JOIN metas_periodo m
        ON m.periodo = b.periodo
), bit_asignacion_data AS (
    -- Efectividad sobre lo asignado: base = asignacion castigo, cruzada por RUT con el recupero y el carterizado.
    SELECT
        a.periodo,
        a.rut_key AS rut,
        COALESCE(cu.usuario, 'Phoenix') AS ejecutivo,
        a.mto_asignado,
        COALESCE(r.mto_recupero_final, 0) AS mto_recupero_asignado,
        COALESCE(m.meta, 0) AS meta_final
    FROM asignacion_rut a
    LEFT JOIN castigo_rut r
        ON r.periodo = a.periodo
       AND r.rut_key = a.rut_key
    LEFT JOIN carterizado_unico cu
        ON cu.periodo = a.periodo
       AND cu.rut_key = a.rut_key
       AND cu.rn = 1
    LEFT JOIN metas_periodo m
        ON m.periodo = a.periodo
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
            UNION
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
        SUM(COALESCE(CAST(mto_recupero_asignado AS float), 0)) AS recupero_asignado
    FROM (
        SELECT periodo, ejecutivo, mto_inicial, mto_contenido, meta_final,
               0 AS mto_asignado, 0 AS mto_recupero_asignado
        FROM bit_castigo_data
        UNION ALL
        SELECT periodo, ejecutivo, 0, 0, meta_final,
               mto_asignado, mto_recupero_asignado
        FROM bit_asignacion_data
    ) src
    WHERE {where_sql}
    GROUP BY ejecutivo
    ORDER BY CASE WHEN ejecutivo = 'Phoenix' THEN 2 ELSE 1 END, ejecutivo
    """
    attempts = [
        _meta_source_sql,
        _meta_source_sql_fallback,
    ]
    last_error: Exception | None = None
    agg_rows = None
    for meta_sql_builder in attempts:
        try:
            cte_sql = _bit_castigo_cte(meta_sql_builder())
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
    meta_periodo = 0.0

    for row in agg_rows:
        monto_inicial = _safe_float(row.get("monto_inicial"))
        monto_contenido = _safe_float(row.get("monto_contenido"))
        meta_final = _safe_float(row.get("meta_final"))
        monto_asignado = _safe_float(row.get("monto_asignado"))
        recupero_asignado = _safe_float(row.get("recupero_asignado"))
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
            }
        )

        total_inicial += monto_inicial
        total_contenido += monto_contenido
        total_asignado += monto_asignado
        total_recupero_asignado += recupero_asignado
        meta_periodo = max(meta_periodo, meta_final)

    return {
        "periodo": periodo,
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
        },
    }
