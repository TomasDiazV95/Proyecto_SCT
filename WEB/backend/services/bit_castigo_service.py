from __future__ import annotations

from datetime import date, timedelta

from cache import cached, cached_view
from database import run_query, run_query_sets
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
    return cached(("bit_castigo", "columnas", table_name), lambda: _query_table_columns(table_name))


def _query_table_columns(table_name: str) -> list[str]:
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


def _meta_periodo(periodo: str) -> float:
    """Meta de recupero del periodo (tramo CASTIGO en tmp_BIT_metas), en pesos."""
    sql = """
    SELECT TOP 1 CAST(meta AS float) AS meta
    FROM {tabla}
    WHERE periodo = ?
      AND UPPER(LTRIM(RTRIM(COALESCE(tramo, '')))) = 'CASTIGO'
    """
    last_error: Exception | None = None
    for tabla in ("[bdphoenixconsultas].[dbo].[tmp_BIT_metas]", "dbo.tmp_BIT_metas"):
        try:
            rows = run_query(sql.format(tabla=tabla), (periodo,))
            return _safe_float(rows[0].get("meta")) if rows else 0.0
        except Exception as exc:
            last_error = exc
    raise last_error if last_error is not None else RuntimeError("No se pudo cargar la meta de BIT Castigo")


def _hay_gestiones_desde(inicio: str) -> bool:
    # El CRM solo tiene gestiones desde cierta fecha: si no cubre el inicio del mes no hay cobertura que medir.
    rows = run_query(
        "SELECT CONVERT(char(10), MIN(GestionFecha), 126) AS primera FROM dbo.tmp_GEST_CRM WHERE cartera = ?",
        (CRM_CARTERA,),
    )
    primera = _clean_text(rows[0].get("primera")) if rows else ""
    return bool(primera) and primera <= inicio


def _numero_sql(expr: str) -> str:
    return (
        f"CASE WHEN {expr} IS NULL THEN 0 "
        f"WHEN ISNUMERIC(CONVERT(VARCHAR(255), {expr})) = 1 THEN CAST({expr} AS float) ELSE 0 END"
    )


def _periodo_sql(cobertura: tuple[str, str]) -> str:
    """Lote del periodo: deja el carterizado, el recupero, la asignacion y las gestiones en tablas
    temporales (una fila por RUT) y devuelve tres resultados: totales por ejecutivo, RUT con nuevos
    convenios y ejecutivos del periodo.

    Va por etapas porque como una sola consulta el optimizador repetia los cruces por RUT y demoraba minutos.
    cobertura = (inicio, corte): ventana de gestiones para la cobertura al dia habil de corte; las fechas
    las calcula el servicio (ISO), no vienen del usuario. Parametros: el periodo, tres veces.
    """
    cart = _cart_config()
    cast = _castigo_config()
    cart_rut = f"c.{cart['rut_col']}"
    cast_rut = cast["rut_col"]
    cast_recupero = cast["recupero_col"]
    es_nuevo_convenio = (
        f"UPPER(LTRIM(RTRIM(COALESCE(CONVERT(VARCHAR(100), {cast['tipo_col']}), '')))) = 'NUEVO CONVENIO'"
        if cast.get("tipo_col")
        else "1 = 0"
    )
    cartera_filter = (
        f"AND UPPER(LTRIM(RTRIM(COALESCE(CONVERT(VARCHAR(100), c.{cart['cartera_col']}), '')))) = 'CASTIGO'"
        if cart.get("cartera_col")
        else ""
    )
    es_castigo = "UPPER(LTRIM(RTRIM(COALESCE(CAMPANA, '')))) LIKE 'CASTIGO%'"
    ejecutivo = "COALESCE(cu.usuario, 'Phoenix')"
    return f"""SET NOCOUNT ON;

    -- Carterizado de castigo: un ejecutivo por RUT.
    SELECT rut_key, usuario
    INTO #cart
    FROM (
        SELECT
            {_rut_join_key_sql(cart_rut)} COLLATE DATABASE_DEFAULT AS rut_key,
            c.{cart['usuario_col']} COLLATE DATABASE_DEFAULT AS usuario,
            ROW_NUMBER() OVER (PARTITION BY {_rut_join_key_sql(cart_rut)} ORDER BY id ASC) AS rn
        FROM dbo.tmp_BIT_carterizado c
        WHERE c.periodo = ?
          AND {cart_rut} IS NOT NULL
          AND LTRIM(RTRIM(COALESCE(CONVERT(VARCHAR(50), {cart_rut}), ''))) <> ''
          {cartera_filter}
    ) src
    WHERE rn = 1;

    -- Recupero por RUT. Nuevos convenios: registros cuyo TIPO es 'Nuevo Convenio'; su recupero es el abono inicial.
    SELECT
        {_rut_join_key_sql(cast_rut)} COLLATE DATABASE_DEFAULT AS rut_key,
        MAX({_numero_sql(cast['total_rut_col'])}) AS total_rut,
        SUM({_numero_sql(cast_recupero)}) AS mto_recupero_final,
        SUM(CASE WHEN {es_nuevo_convenio} THEN 1 ELSE 0 END) AS nuevos_convenios,
        SUM(CASE WHEN {es_nuevo_convenio} THEN {_numero_sql(cast_recupero)} ELSE 0 END) AS abono_inicial
    INTO #cast
    FROM dbo.tmp_BIT_castigo
    WHERE {cast['periodo_col']} = ?
      AND {cast_rut} IS NOT NULL
      AND LTRIM(RTRIM(COALESCE(CONVERT(VARCHAR(50), {cast_rut}), ''))) <> ''
    GROUP BY {_rut_join_key_sql(cast_rut)};

    -- La deuda asignada es solo la de campañas castigo; la cobertura no mira la campaña.
    SELECT
        {_rut_join_key_sql("RUT")} COLLATE DATABASE_DEFAULT AS rut_key,
        SUM(CASE WHEN {es_castigo} THEN COALESCE(CAST(DEUDA_TOTAL AS float), 0) ELSE 0 END) AS mto_asignado,
        MAX(CASE WHEN {es_castigo} THEN 1 ELSE 0 END) AS es_castigo
    INTO #asig
    FROM {_asignacion_table()}
    WHERE periodo = ?
      AND RUT IS NOT NULL
      AND LTRIM(RTRIM(RUT)) <> ''
    GROUP BY {_rut_join_key_sql("RUT")};

    -- RUT con al menos una gestion telefonica o en terreno hasta el dia habil de corte.
    SELECT DISTINCT {_rut_join_key_sql("g.rut")} COLLATE DATABASE_DEFAULT AS rut_key
    INTO #gest
    FROM dbo.tmp_GEST_CRM g
    INNER JOIN dbo.kpi_accion_canal ac
        ON ac.valor = UPPER(LTRIM(RTRIM(g.AccionGestion)))
       AND ac.canal IN ('LLAMADA', 'TERRENO')
    WHERE g.cartera = {CRM_CARTERA}
      AND g.GestionFecha >= '{cobertura[0]}'
      AND g.GestionFecha <= '{cobertura[1]}';

    -- Recupero del mes: una fila por RUT con recupero, con su ejecutivo ('Phoenix' si no esta carterizado).
    SELECT
        b.rut_key AS rut,
        {ejecutivo} AS ejecutivo,
        b.total_rut AS mto_inicial,
        b.mto_recupero_final AS mto_contenido,
        b.nuevos_convenios,
        b.abono_inicial
    INTO #recupero
    FROM #cast b
    LEFT JOIN #cart cu ON cu.rut_key = b.rut_key;

    -- Efectividad sobre lo asignado: base = asignacion castigo, cruzada por RUT con el recupero y el carterizado.
    -- Cobertura: base = carterizado de castigo, este o no en la asignacion.
    SELECT
        {ejecutivo} AS ejecutivo,
        COALESCE(a.mto_asignado, 0) AS mto_asignado,
        CASE WHEN a.es_castigo = 1 THEN COALESCE(r.mto_recupero_final, 0) ELSE 0 END AS mto_recupero_asignado,
        CASE WHEN cu.rut_key IS NOT NULL THEN 1 ELSE 0 END AS rut_asignado,
        CASE WHEN cu.rut_key IS NOT NULL AND ge.rut_key IS NOT NULL THEN 1 ELSE 0 END AS rut_gestionado
    INTO #asignado
    FROM #asig a
    FULL JOIN #cart cu ON cu.rut_key = a.rut_key
    LEFT JOIN #cast r ON r.rut_key = COALESCE(cu.rut_key, a.rut_key)
    LEFT JOIN #gest ge ON ge.rut_key = COALESCE(cu.rut_key, a.rut_key)
    WHERE a.es_castigo = 1
       OR cu.rut_key IS NOT NULL;

    SELECT
        ejecutivo,
        SUM(mto_inicial) AS monto_inicial,
        SUM(mto_contenido) AS monto_contenido,
        SUM(mto_asignado) AS monto_asignado,
        SUM(mto_recupero_asignado) AS recupero_asignado,
        SUM(nuevos_convenios) AS nuevos_convenios,
        SUM(abono_inicial) AS abono_inicial,
        SUM(ruts_asignados) AS ruts_asignados,
        SUM(ruts_gestionados) AS ruts_gestionados
    FROM (
        SELECT ejecutivo, mto_inicial, mto_contenido, 0 AS mto_asignado, 0 AS mto_recupero_asignado,
               nuevos_convenios, abono_inicial, 0 AS ruts_asignados, 0 AS ruts_gestionados
        FROM #recupero
        UNION ALL
        SELECT ejecutivo, 0, 0, mto_asignado, mto_recupero_asignado, 0, 0, rut_asignado, rut_gestionado
        FROM #asignado
    ) src
    GROUP BY ejecutivo
    ORDER BY CASE WHEN ejecutivo = 'Phoenix' THEN 2 ELSE 1 END, ejecutivo;

    SELECT rut, ejecutivo, nuevos_convenios, mto_inicial AS deuda, abono_inicial
    FROM #recupero
    WHERE nuevos_convenios > 0
    ORDER BY CASE WHEN ejecutivo = 'Phoenix' THEN 2 ELSE 1 END, ejecutivo, rut;

    SELECT DISTINCT LTRIM(RTRIM(ejecutivo)) AS v
    FROM (
        SELECT ejecutivo FROM #recupero
        UNION ALL
        SELECT ejecutivo FROM #asignado
    ) src
    WHERE LTRIM(RTRIM(ejecutivo)) <> ''
    ORDER BY v;
    """


def _load_periodo(periodo: str) -> dict:
    corte_cobertura = _dia_habil_del_mes(periodo, DIAS_HABILES_COBERTURA)
    inicio = f"{periodo[:7]}-01"
    general, convenios, ejecutivos = run_query_sets(_periodo_sql((inicio, corte_cobertura)), (periodo,) * 3)[-3:]
    return {
        "general": general,
        "convenios": convenios,
        "ejecutivos": [row["v"] for row in ejecutivos if row.get("v")],
        "corte_cobertura": corte_cobertura,
        "hay_cobertura": _hay_gestiones_desde(inicio),
        "contencion_file": _get_source_file(periodo),
        "meta": _meta_periodo(periodo),
    }


def _periodo_data(periodo: str) -> dict:
    """Datos del periodo para todos los ejecutivos; el filtro de ejecutivo se aplica en memoria."""
    return cached(("bit_castigo", "periodo", periodo), lambda: _load_periodo(periodo))


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


def _del_ejecutivo(rows: list[dict], ejecutivo: object) -> list[dict]:
    buscado = _clean_text(ejecutivo).upper()
    if not buscado:
        return rows
    return [row for row in rows if _clean_text(row.get("ejecutivo")).upper() == buscado]


@cached_view
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
        # Sin periodo se ofrecen los ejecutivos del mas reciente, que es el que abre la pagina.
        ejecutivos = list(_periodo_data(_resolve_period(periodo or (periodos[0] if periodos else None)))["ejecutivos"])
    except Exception:
        # Si el cruce con carterizado o dotacion falla por columnas distintas
        # entre ambientes, no bloqueamos la carga inicial de la pantalla.
        ejecutivos = []

    return {"periodos": periodos, "ejecutivos": ejecutivos}


@cached_view
def get_general(filters: dict) -> dict:
    periodo = _resolve_period(filters.get("periodo"))
    data = _periodo_data(periodo)
    agg_rows = _del_ejecutivo(data["general"], filters.get("ejecutivo"))
    corte_cobertura = data["corte_cobertura"]
    hay_cobertura = data["hay_cobertura"]
    # La meta es del periodo, la misma para todos los ejecutivos.
    meta_final = data["meta"]

    rows: list[dict] = []
    total_inicial = 0.0
    total_contenido = 0.0
    total_asignado = 0.0
    total_recupero_asignado = 0.0
    total_nuevos_convenios = 0
    total_abono_inicial = 0.0
    total_ruts_asignados = 0
    total_ruts_gestionados = 0
    meta_periodo = meta_final if agg_rows else 0.0

    for row in agg_rows:
        monto_inicial = _safe_float(row.get("monto_inicial"))
        monto_contenido = _safe_float(row.get("monto_contenido"))
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

    return {
        "periodo": periodo,
        "corte_cobertura": corte_cobertura,
        "contencion_file": data["contencion_file"],
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


@cached_view
def get_nuevos_convenios(filters: dict) -> list[dict]:
    """Detalle de los nuevos convenios del mes: una fila por RUT con su ejecutivo, la deuda castigada,
    el abono inicial y las operaciones castigo que tiene asignadas (el recupero no trae numero de operacion)."""
    periodo = _resolve_period(filters.get("periodo"))
    rows = _del_ejecutivo(_periodo_data(periodo)["convenios"], filters.get("ejecutivo"))

    operaciones: dict[str, list[str]] = {}
    for row in run_query(
        f"""
        SELECT DISTINCT {_rut_join_key_sql("RUT")} AS rut, LTRIM(RTRIM(NRO_OPERACION)) AS operacion
        FROM {_asignacion_table()}
        WHERE periodo = ?
          AND UPPER(LTRIM(RTRIM(COALESCE(CAMPANA, '')))) LIKE 'CASTIGO%'
          AND NRO_OPERACION IS NOT NULL
        ORDER BY 2
        """,
        (periodo,),
    ):
        operaciones.setdefault(str(row["rut"]), []).append(str(row["operacion"]))

    return [
        {
            "rut": row["rut"],
            "ejecutivo": row["ejecutivo"],
            "nuevos_convenios": int(row["nuevos_convenios"] or 0),
            "deuda": float(row["deuda"] or 0),
            "abono_inicial": float(row["abono_inicial"] or 0),
            "operaciones": operaciones.get(str(row["rut"]), []),
        }
        for row in rows
    ]
