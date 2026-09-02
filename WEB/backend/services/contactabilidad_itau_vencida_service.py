from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta
from functools import lru_cache
import logging
from threading import Lock
from time import monotonic
from typing import Any

from database import run_query, run_query_sets


logger = logging.getLogger(__name__)


TABLES = {
    "contencion": "contencion_itau_vencida",
    "asignacion": "asignacion_itau_vencida",
    "crm": "tmp_GEST_CRM",
}
DEFAULT_GESTOR = "PHOENIX"
CRM_CARTERA = 523
CALL_ACTIONS = ("TELEFONICA", "TERRENO")
SORT_COLUMNS = {
    "rut": "rut",
    "operacion": "operacion",
    "gestor": "gestor",
    "segmento": "segmento",
    "cantidad_gestiones": "cantidad_gestiones",
    "ultima_gestion": "ultima_gestion",
    "estado_contacto": "estado_contacto",
}
FILTER_CACHE_TTL_SECONDS = 300
_filter_cache: dict[str, tuple[float, dict]] = {}
_filter_cache_lock = Lock()


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _clean_list(value: Any) -> list[str]:
    if value is None:
        return []
    values = value if isinstance(value, (list, tuple)) else [value]
    return [_text(item) for item in values if _text(item)]


def _safe_div(num: float, den: float) -> float:
    return 0.0 if not den else num / den


def _parse_date(value: Any, default: str | None = None) -> str:
    raw = _text(value) or _text(default)
    if not raw:
        rows = run_query(
            "SELECT CONVERT(char(10), MAX([fecha_carga]), 126) AS fecha "
            "FROM [dbo].[contencion_itau_vencida]"
        )
        raw = _text(rows[0].get("fecha") if rows else "")
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw[:10], fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"Fecha de proceso invÃ¡lida: {value}")


def _month_start(process_date: str) -> date:
    return date.fromisoformat(process_date).replace(day=1)


def _quote(identifier: str) -> str:
    return "[" + identifier.replace("]", "]]" ) + "]"


def _table(table_key: str) -> str:
    return "[dbo].[" + TABLES[table_key] + "]"


@lru_cache(maxsize=4)
def _columns(table_key: str) -> dict[str, str]:
    rows = run_query(
        """
        SELECT COLUMN_NAME
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?
        ORDER BY ORDINAL_POSITION
        """,
        ("dbo", TABLES[table_key]),
    )
    return {str(row["COLUMN_NAME"]).lower(): str(row["COLUMN_NAME"]) for row in rows}


def _resolve(table_key: str, *names: str, required: bool = True) -> str | None:
    columns = _columns(table_key)
    for name in names:
        if name.lower() in columns:
            return columns[name.lower()]
    if required:
        raise RuntimeError(f"No se encontrÃ³ columna {names} en {TABLES[table_key]}")
    return None


def _value_expr(alias: str, column: str | None) -> str:
    return f"{alias}.{_quote(column)}" if column else "NULL"


def _in_filter(column_expr: str, values: list[str], params: list[Any]) -> str:
    if not values:
        return ""
    params.extend(values)
    marks = ",".join("?" for _ in values)
    return (
        f" AND UPPER(LTRIM(RTRIM(CONVERT(nvarchar(255), {column_expr})))) "
        f"IN ({marks})"
    )


def _resolved() -> dict[str, str | None]:
    return {
        "c_rut": _resolve("contencion", "RUT"),
        "c_operacion": _resolve("contencion", "OPER"),
        "c_fecha": _resolve("contencion", "fecha_carga", "FECHA_CARGA"),
        "c_segmento": _resolve("contencion", "SEGMENTO"),
        "c_canal": _resolve("contencion", "CANAL"),
        "c_gestor": _resolve("contencion", "GESTOR"),
        "c_fase": _resolve("contencion", "FASE_PROY_MAX"),
        "c_producto": _resolve("contencion", "PRODUCTO"),
        "c_campana": _resolve("contencion", "TIPO_CAMPANA"),
        "c_marca": _resolve("contencion", "DETALLE_MARCA"),
        "c_contencion": _resolve("contencion", "CONTENCION", "SALDO_CONT"),
        "a_rut": _resolve("asignacion", "RUT", "Rut"),
        "a_fecha": _resolve("asignacion", "fecha_carga", "FECHA_CARGA"),
        "a_operacion": _resolve("asignacion", "Numero_Cuenta"),
        "g_rut": _resolve("crm", "RUT", "Rut", "Numero_Cliente", "Cliente"),
        "g_operacion": _resolve("crm", "OPER", "Operacion", "Numero_Cuenta", required=False),
        "g_fecha": _resolve("crm", "GestionFecha", "fecha_gestion", "FECHA_GESTION"),
        "g_accion": _resolve("crm", "AccionGestion", "ACCION_GESTION"),
        "g_contacto": _resolve("crm", "CONTACTOGESTION", "CONTACTO_GESTION"),
        "g_cartera": _resolve("crm", "cartera", "CARTERA"),
    }


def _filter_sql_and_params(filters: dict, cols: dict[str, str | None]) -> tuple[str, list[Any]]:
    params: list[Any] = [DEFAULT_GESTOR]
    c = "c"
    parts = [
        f" AND {c}.{_quote(cols['c_gestor'])} = ?",
        _in_filter(f"{c}.{_quote(cols['c_segmento'])}", _clean_list(filters.get("segmento")), params),
        _in_filter(f"{c}.{_quote(cols['c_canal'])}", _clean_list(filters.get("canal")), params),
        _in_filter(f"{c}.{_quote(cols['c_fase'])}", _clean_list(filters.get("fase_cliente")), params),
        _in_filter(f"{c}.{_quote(cols['c_producto'])}", _clean_list(filters.get("producto")), params),
        _in_filter(f"{c}.{_quote(cols['c_campana'])}", _clean_list(filters.get("tipo_campana")), params),
        _in_filter(f"{c}.{_quote(cols['c_marca'])}", _clean_list(filters.get("detalle_marca")), params),
    ]
    contencion_state = _clean_list(filters.get("estado_contencion"))
    if contencion_state:
        marks = ",".join("?" for _ in contencion_state)
        parts.append(
            f" AND CASE WHEN ISNULL(TRY_CONVERT(float, {c}.{_quote(cols['c_contencion'])}), 0) > 0 "
            f"THEN 'SI' ELSE 'NO' END IN ({marks})"
        )
        params.extend(contencion_state)
    return "".join(parts), params


def _build_batch(filters: dict, include_detail: bool) -> tuple[str, list[Any], str, dict]:
    cols = _resolved()
    process_date = _parse_date(filters.get("fecha_proceso"))
    start = _month_start(process_date)
    end = date.fromisoformat(process_date) + timedelta(days=1)
    filter_sql, params = _filter_sql_and_params(filters, cols)

    c_rut = _value_expr("c", cols["c_rut"])
    c_operation = _value_expr("c", cols["c_operacion"])
    a_rut = _value_expr("a", cols["a_rut"])
    a_operation = _value_expr("a", cols["a_operacion"])
    g_rut = _value_expr("g", cols["g_rut"])
    g_operation = _value_expr("g", cols["g_operacion"])
    search = _text(filters.get("search"))
    page = max(1, int(filters.get("page") or 1))
    page_size = min(500, max(1, int(filters.get("page_size") or 100)))
    sort = SORT_COLUMNS.get(_text(filters.get("sort_by")), "rut")
    direction = "DESC" if _text(filters.get("sort_direction")).upper() == "DESC" else "ASC"
    order_by = f"[{sort}] {direction}" + (", [rut]" if sort != "rut" else "")

    contact_filter = _clean_list(filters.get("estado_contacto"))
    contact_sql = ""
    if contact_filter:
        marks = ",".join("?" for _ in contact_filter)
        contact_sql = f" AND UPPER(LTRIM(RTRIM(g.{_quote(cols['g_contacto'])}))) IN ({marks})"

    params.insert(0, process_date)
    params.append(process_date)
    params.extend([CRM_CARTERA, start.isoformat(), end.isoformat()])
    params.extend(contact_filter)

    detail_sql = ""
    if include_detail:
        detail_where = ""
        if search:
            detail_where = " WHERE [rut] LIKE ? OR COALESCE([operacion], '') LIKE ?"
            params.extend([f"%{search}%", f"%{search}%"])
        params.extend([(page - 1) * page_size, page_size])
        detail_sql = f"""
        SELECT [rut], [operacion], [gestor], [cantidad_gestiones], [ultima_gestion], [estado_contacto],
               COUNT(*) OVER() AS total_rows
        FROM #clasificado
        {detail_where}
        ORDER BY {order_by}
        OFFSET ? ROWS FETCH NEXT ? ROWS ONLY;
        """

    sql = f"""
    SET NOCOUNT ON;

    SELECT DISTINCT
           {c_rut} AS rut_contencion,
           {c_operation} AS operacion
    INTO #contencion_filtrada
    FROM {_table('contencion')} c
    WHERE c.{_quote(cols['c_fecha'])} = ?
      {filter_sql};

    CREATE INDEX IX_tmp_contactabilidad_contencion_operacion
        ON #contencion_filtrada(operacion);

    SELECT DISTINCT
           {a_rut} AS rut,
           c.rut_contencion,
           {a_operation} AS operacion
    INTO #universo_operacion
    FROM {_table('asignacion')} a
    INNER JOIN #contencion_filtrada c ON c.operacion = {a_operation}
    WHERE a.{_quote(cols['a_fecha'])} = ?
      AND {a_rut} IS NOT NULL
      AND CONVERT(nvarchar(255), {a_rut}) <> '';

    CREATE INDEX IX_tmp_contactabilidad_universo_rut
        ON #universo_operacion(rut);
    CREATE INDEX IX_tmp_contactabilidad_universo_operacion
        ON #universo_operacion(operacion);

    SELECT rut, MAX(rut_contencion) AS rut_contencion, MAX(operacion) AS operacion
    INTO #universo_cliente
    FROM #universo_operacion
    GROUP BY rut;

    CREATE UNIQUE CLUSTERED INDEX IX_tmp_contactabilidad_cliente_rut
        ON #universo_cliente(rut);

    SELECT
           {g_rut} AS rut_contencion,
           {g_operation} AS operacion,
           g.{_quote(cols['g_fecha'])} AS gestion_fecha,
           UPPER(LTRIM(RTRIM(g.{_quote(cols['g_accion'])}))) AS accion,
           UPPER(LTRIM(RTRIM(g.{_quote(cols['g_contacto'])}))) AS contacto
    INTO #crm_base
    FROM {_table('crm')} g
    INNER JOIN #universo_cliente u ON u.rut_contencion = {g_rut}
    WHERE g.{_quote(cols['g_cartera'])} = ?
      AND g.{_quote(cols['g_fecha'])} >= ?
      AND g.{_quote(cols['g_fecha'])} < ?
      AND {g_rut} IS NOT NULL
      AND CONVERT(nvarchar(255), {g_rut}) <> ''
      {contact_sql};

    CREATE INDEX IX_tmp_contactabilidad_crm_rut_fecha
        ON #crm_base(rut_contencion, gestion_fecha);

    SELECT u.rut,
           COUNT(crm.rut_contencion) AS total_eventos,
           SUM(CASE WHEN crm.accion IN ('TELEFONICA', 'TERRENO') THEN 1 ELSE 0 END) AS total_call_terreno,
           MAX(CASE WHEN crm.contacto = 'TITULAR' THEN 1 ELSE 0 END) AS tiene_titular,
           MAX(CASE WHEN crm.contacto IN ('TERCERO', 'TERCEROS', 'CONTACTO TERCERO') THEN 1 ELSE 0 END) AS tiene_tercero,
           MAX(CASE WHEN crm.accion IN ('TELEFONICA', 'TERRENO') THEN 1 ELSE 0 END) AS tiene_call_terreno,
           MAX(CASE WHEN crm.accion NOT IN ('TELEFONICA', 'TERRENO') THEN 1 ELSE 0 END) AS tiene_otra,
           MAX(crm.gestion_fecha) AS ultima_gestion
    INTO #eventos_cliente
    FROM #universo_cliente u
    LEFT JOIN #crm_base crm ON crm.rut_contencion = u.rut_contencion
    GROUP BY u.rut;

    SELECT u.rut,
           u.operacion,
           '{DEFAULT_GESTOR}' AS gestor,
           e.total_eventos,
           e.total_call_terreno,
           e.tiene_titular,
           e.tiene_tercero,
           e.tiene_call_terreno,
           e.tiene_otra,
           e.ultima_gestion,
           CASE
             WHEN e.tiene_titular = 1 THEN 'Contacto Titular'
             WHEN e.tiene_tercero = 1 THEN 'Contacto Tercero'
             WHEN e.tiene_call_terreno = 1 THEN 'Gestión Call-Terreno'
             WHEN e.tiene_otra = 1 THEN 'Otras Gestiones'
             ELSE 'Sin GestiÃ³n'
           END AS estado_contacto,
           e.total_call_terreno AS cantidad_gestiones
    INTO #clasificado
    FROM #universo_cliente u
    INNER JOIN #eventos_cliente e ON e.rut = u.rut;

    CREATE UNIQUE CLUSTERED INDEX IX_tmp_contactabilidad_clasificado_rut
        ON #clasificado(rut);

    SELECT COUNT(*) AS total_clientes,
           COALESCE(SUM(total_call_terreno), 0) AS total_gestiones,
           COALESCE(SUM(CASE WHEN total_eventos > 0 THEN 1 ELSE 0 END), 0) AS clientes_gestionados,
           COALESCE(SUM(tiene_titular), 0) AS contacto_titular,
           COALESCE(SUM(tiene_tercero), 0) AS contacto_tercero,
           COALESCE(SUM(tiene_call_terreno), 0) AS clientes_call_terreno,
           COALESCE(SUM(tiene_otra), 0) AS otras_gestiones,
           COALESCE(SUM(CASE WHEN total_eventos = 0 THEN 1 ELSE 0 END), 0) AS sin_gestion
    INTO #resumen
    FROM #clasificado;

    SELECT total_clientes, total_gestiones, clientes_gestionados, contacto_titular,
           contacto_tercero, clientes_call_terreno, otras_gestiones, sin_gestion
    FROM #resumen;

    SELECT '{DEFAULT_GESTOR}' AS gestor, estado, clientes,
           CASE WHEN total_clientes = 0 THEN 0 ELSE CAST(clientes AS decimal(18,6)) / total_clientes END AS porcentaje
    FROM (
        SELECT 'Contacto Titular' AS estado, contacto_titular AS clientes, total_clientes FROM #resumen
        UNION ALL SELECT 'Contacto Tercero', contacto_tercero, total_clientes FROM #resumen
        UNION ALL SELECT 'Gestión Call-Terreno', clientes_call_terreno, total_clientes FROM #resumen
        UNION ALL SELECT 'Otras Gestiones', otras_gestiones, total_clientes FROM #resumen
        UNION ALL SELECT 'Sin GestiÃ³n', sin_gestion, total_clientes FROM #resumen
    ) estados;

    SELECT '{DEFAULT_GESTOR}' AS gestor,
           CASE WHEN total_clientes = 0 THEN 0 ELSE CAST(total_gestiones AS decimal(18,6)) / total_clientes END AS recurrencia,
           total_clientes AS casos_asignados,
           clientes_gestionados AS casos_con_gestion,
           CASE WHEN total_clientes = 0 THEN 0 ELSE CAST(clientes_gestionados AS decimal(18,6)) / total_clientes END AS porcentaje_gestionado,
           contacto_titular AS casos_contacto_titular,
           CASE WHEN clientes_gestionados = 0 THEN 0 ELSE CAST(contacto_titular AS decimal(18,6)) / clientes_gestionados END AS porcentaje_contacto_titular
    FROM #resumen;

    SELECT CONVERT(char(10), gestion_fecha, 126) AS fecha,
           COUNT(*) AS total_gestiones,
           COUNT(DISTINCT CASE WHEN accion IN ('TELEFONICA', 'TERRENO') THEN rut_contencion END) AS clientes_gestionados,
           COUNT(DISTINCT CASE WHEN contacto = 'TITULAR' THEN rut_contencion END) AS contacto_titular
    FROM #crm_base
    GROUP BY CONVERT(char(10), gestion_fecha, 126)
    ORDER BY fecha;

    {detail_sql}
    """
    return sql, params, process_date, {"page": page, "page_size": page_size}


def _execute_dashboard(filters: dict, include_detail: bool = True) -> tuple[str, list[list[dict]], dict]:
    sql, params, process_date, pagination = _build_batch(filters, include_detail)
    started = monotonic()
    result_sets = run_query_sets(sql, tuple(params))
    logger.info(
        "Contactabilidad Itaú Vencida procesada: fecha=%s detalle=%s tiempo=%.3fs",
        process_date,
        include_detail,
        monotonic() - started,
    )
    return process_date, result_sets, pagination


def _summary_response(row: dict, process_date: str) -> dict:
    total = int(row.get("total_clientes") or 0)
    managed = int(row.get("clientes_gestionados") or 0)
    gestures = int(row.get("total_gestiones") or 0)
    titular = int(row.get("contacto_titular") or 0)
    return {
        "fecha_proceso": process_date,
        "periodo": _month_start(process_date).isoformat(),
        "total_gestiones": gestures,
        "total_clientes": total,
        "clientes_gestionados": managed,
        "recurrencia": _safe_div(gestures, total),
        "porcentaje_gestionado": _safe_div(managed, total),
        "contacto_titular": titular,
        "porcentaje_contacto_titular": _safe_div(titular, managed),
        "contacto_tercero": int(row.get("contacto_tercero") or 0),
        "clientes_call_terreno": int(row.get("clientes_call_terreno") or 0),
        "otras_gestiones": int(row.get("otras_gestiones") or 0),
        "sin_gestion": int(row.get("sin_gestion") or 0),
    }


def _dashboard_response(filters: dict, include_detail: bool = True) -> dict:
    process_date, result_sets, pagination = _execute_dashboard(filters, include_detail)
    summary = _summary_response(result_sets[0][0] if result_sets and result_sets[0] else {}, process_date)
    state_rows = result_sets[1] if len(result_sets) > 1 else []
    tube_rows = result_sets[2] if len(result_sets) > 2 else []
    evolution_rows = result_sets[3] if len(result_sets) > 3 else []
    total = summary["total_clientes"]
    for row in evolution_rows:
        managed = int(row.get("clientes_gestionados") or 0)
        row["porcentaje_gestionado"] = _safe_div(managed, total)
        row["porcentaje_contacto_titular"] = _safe_div(
            int(row.get("contacto_titular") or 0), managed
        )

    detail_rows = result_sets[4] if include_detail and len(result_sets) > 4 else []
    detail_total = int(detail_rows[0].get("total_rows") or 0) if detail_rows else 0
    for row in detail_rows:
        row.pop("total_rows", None)
    detalle = {
        "rows": detail_rows,
        "items": detail_rows,
        "page": pagination["page"],
        "page_size": pagination["page_size"],
        "total": detail_total,
        "fecha_proceso": process_date,
    }
    return {
        "resumen": summary,
        "estado": {"rows": state_rows, "total_clientes": total},
        "estado_contacto": {"rows": state_rows, "total_clientes": total},
        "tubo": {"rows": tube_rows},
        "evolucion": {"fecha_proceso": process_date, "rows": evolution_rows},
        "detalle": detalle,
    }


def get_dashboard(filters: dict) -> dict:
    return _dashboard_response(filters, include_detail=True)


def get_resumen(filters: dict) -> dict:
    return _dashboard_response(filters, include_detail=False)["resumen"]


def get_estado_contacto(filters: dict) -> dict:
    return _dashboard_response(filters, include_detail=False)["estado"]


def get_tubo(filters: dict) -> dict:
    return _dashboard_response(filters, include_detail=False)["tubo"]


def get_evolucion(filters: dict) -> dict:
    return _dashboard_response(filters, include_detail=False)["evolucion"]


def get_detalle(filters: dict) -> dict:
    return _dashboard_response(filters, include_detail=True)["detalle"]


def _filter_values_uncached(process_date: str) -> dict:
    cols = _resolved()
    statements = [
        f"SELECT DISTINCT CONVERT(char(10), {_quote(cols['c_fecha'])}, 126) AS fecha "
        f"FROM {_table('contencion')} "
        f"WHERE {_quote(cols['c_fecha'])} IS NOT NULL ORDER BY fecha DESC",
    ]
    value_columns = (
        ("segmentos", cols["c_segmento"]),
        ("canales", cols["c_canal"]),
        ("fases_cliente", cols["c_fase"]),
        ("productos", cols["c_producto"]),
        ("tipos_campana", cols["c_campana"]),
        ("detalles_marca", cols["c_marca"]),
    )
    for _, column in value_columns:
        statements.append(
            f"SELECT DISTINCT LTRIM(RTRIM(CONVERT(nvarchar(255), {_quote(column)}))) AS valor "
            f"FROM {_table('contencion')} "
            f"WHERE {_quote(cols['c_fecha'])} = ? AND {_quote(cols['c_gestor'])} = ? "
            f"AND {_quote(column)} IS NOT NULL "
            f"AND LTRIM(RTRIM(CONVERT(nvarchar(255), {_quote(column)}))) <> '' "
            f"ORDER BY valor"
        )
    statements.append(
        f"SELECT DISTINCT UPPER(LTRIM(RTRIM(CONVERT(nvarchar(255), {_quote(cols['g_contacto'])})))) AS valor "
        f"FROM {_table('crm')} WHERE {_quote(cols['g_cartera'])} = ? "
        f"AND {_quote(cols['g_contacto'])} IS NOT NULL ORDER BY valor"
    )
    params: list[Any] = []
    for _ in value_columns:
        params.extend([process_date, DEFAULT_GESTOR])
    params.append(CRM_CARTERA)
    result_sets = run_query_sets("SET NOCOUNT ON;\n" + ";\n".join(statements), tuple(params))

    def values(index: int) -> list[str]:
        return [_text(row.get("valor")) for row in result_sets[index] if _text(row.get("valor"))]

    fechas = [_text(row.get("fecha")) for row in result_sets[0] if _text(row.get("fecha"))]
    return {
        "fechas_proceso": fechas,
        "fecha_proceso": process_date,
        "segmentos": values(1),
        "canales": values(2),
        "gestores": [DEFAULT_GESTOR],
        "fases_cliente": values(3),
        "productos": values(4),
        "tipos_campana": values(5),
        "detalles_marca": values(6),
        "estados_contencion": ["SI", "NO"],
        "estados_contacto": values(7),
    }


def get_filter_values(filters: dict | None = None) -> dict:
    process_date = _parse_date((filters or {}).get("fecha_proceso"))
    now = monotonic()
    with _filter_cache_lock:
        cached = _filter_cache.get(process_date)
        if cached and now - cached[0] < FILTER_CACHE_TTL_SECONDS:
            return deepcopy(cached[1])
    result = _filter_values_uncached(process_date)
    logger.info("Filtros Contactabilidad Itaú Vencida obtenidos: fecha=%s", process_date)
    with _filter_cache_lock:
        _filter_cache[process_date] = (monotonic(), deepcopy(result))
        expired = [key for key, (created, _) in _filter_cache.items() if monotonic() - created >= FILTER_CACHE_TTL_SECONDS]
        for key in expired:
            _filter_cache.pop(key, None)
    return result
