from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta
from functools import lru_cache
import logging
from threading import Lock
from time import monotonic
from typing import Any

from database import run_query, run_query_sets
from feriados_chile import dias_habiles_al_cierre


logger = logging.getLogger(__name__)


TABLES = {
    "contencion": "contencion_itau_vencida",
    "crm": "tmp_GEST_CRM",
    "promesas": "tmp_FECHA_COMPROMISO_CRM",
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
EXPORT_HEADERS = [
    "OP",
    "RUT",
    "DV",
    "NOMBRE",
    "GLOSA TIPO CARTERA",
    "PRODUCTO",
    "CANAL",
    "SEGMENTO",
    "DETALLE MARCA",
    "CAMPAÑA",
    "FECHA GESTION",
    "TIPO GESTION",
    "GESTION",
    "CONTENCION",
    "FECHA PROMESA",
    "PROMESA CUMPLIDA",
]
EXPORT_MAX_ROWS = 200000
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


class PeriodoSinContencion(Exception):
    """El período pedido no tiene ninguna carga de contención."""


def _periodos_disponibles() -> list[str]:
    """Períodos YYYY-MM con al menos una carga de contención, del más reciente al más antiguo."""
    rows = run_query(
        "SELECT DISTINCT CONVERT(char(7), [fecha_carga], 126) AS periodo "
        "FROM [dbo].[contencion_itau_vencida] "
        "WHERE [fecha_carga] IS NOT NULL ORDER BY periodo DESC"
    )
    return [_text(row.get("periodo")) for row in rows if _text(row.get("periodo"))]


def _parse_period(value: Any) -> str:
    """Normaliza la entrada a YYYY-MM. Sin valor, toma el período más reciente con contención."""
    raw = _text(value)
    if not raw:
        periodos = _periodos_disponibles()
        if not periodos:
            raise PeriodoSinContencion("No existe información de contención disponible.")
        return periodos[0]
    for fmt in ("%Y-%m", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw[: len(fmt) + 2], fmt).date().strftime("%Y-%m")
        except ValueError:
            continue
    raise ValueError(f"Período inválido: {value}")


def _period_bounds(period: str) -> tuple[date, date]:
    """Primer día del período y primer día del período siguiente (límite superior exclusivo)."""
    year, month = int(period[:4]), int(period[5:7])
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start, end


def _resolve_contencion_date(period: str) -> str:
    """Última FECHA_CARGA de contención dentro del período. Nunca cae a otro período."""
    start, end = _period_bounds(period)
    rows = run_query(
        "SELECT CONVERT(char(10), MAX([fecha_carga]), 126) AS fecha "
        "FROM [dbo].[contencion_itau_vencida] "
        "WHERE [fecha_carga] >= ? AND [fecha_carga] < ?",
        (start.isoformat(), end.isoformat()),
    )
    fecha = _text(rows[0].get("fecha") if rows else "")
    if not fecha:
        raise PeriodoSinContencion(
            f"No existe información de contención para el período {period}."
        )
    return fecha


def _quote(identifier: str) -> str:
    return "[" + identifier.replace("]", "]]" ) + "]"


def _table(table_key: str) -> str:
    return "[dbo].[" + TABLES[table_key] + "]"


@lru_cache(maxsize=8)
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
        "c_glosa_tipo_cartera": _resolve("contencion", "GLOSA_TIPO_CARTERA", required=False),
        "c_campana": _resolve("contencion", "TIPO_CAMPANA"),
        "c_marca": _resolve("contencion", "DETALLE_MARCA"),
        "c_contencion": _resolve("contencion", "CONTENCION", "SALDO_CONT"),
        "c_nombre": _resolve("contencion", "NOMBRE", required=False),
        "c_dv": _resolve("contencion", "DV1", "DV", required=False),
        "g_rut": _resolve("crm", "RUT", "Rut", "Numero_Cliente", "Cliente"),
        "g_operacion": _resolve("crm", "OPER", "Operacion", "Numero_Cuenta", required=False),
        "g_fecha": _resolve("crm", "GestionFecha", "fecha_gestion", "FECHA_GESTION"),
        "g_accion": _resolve("crm", "AccionGestion", "ACCION_GESTION"),
        "g_contacto": _resolve("crm", "CONTACTOGESTION", "CONTACTO_GESTION"),
        "g_cartera": _resolve("crm", "cartera", "CARTERA"),
        "p_rut": _resolve("promesas", "RutCliente", "RUT", "Rut"),
        "p_fecha_gestion": _resolve("promesas", "FechaGestion", "fecha_gestion"),
        "p_fecha_compromiso": _resolve("promesas", "FechaCompromiso", required=False),
        "p_cartera": _resolve("promesas", "cartera", "CARTERA"),
    }


def _filter_sql_and_params(filters: dict, cols: dict[str, str | None]) -> tuple[str, list[Any]]:
    params: list[Any] = [DEFAULT_GESTOR]
    c = "c"
    parts = [
        f" AND {c}.{_quote(cols['c_gestor'])} = ?",
        _in_filter(f"{c}.{_quote(cols['c_segmento'])}", _clean_list(filters.get("segmento")), params),
        _in_filter(f"{c}.{_quote(cols['c_canal'])}", _clean_list(filters.get("canal")), params),
        _in_filter(f"{c}.{_quote(cols['c_fase'])}", _clean_list(filters.get("fase_cliente")), params),
    ]
    glosa_values = _clean_list(filters.get("glosa_tipo_cartera"))
    if glosa_values and cols.get("c_glosa_tipo_cartera"):
        parts.append(
            _in_filter(
                f"{c}.{_quote(cols['c_glosa_tipo_cartera'])}", glosa_values, params
            )
        )
    parts.extend([
        _in_filter(f"{c}.{_quote(cols['c_producto'])}", _clean_list(filters.get("producto")), params),
        _in_filter(f"{c}.{_quote(cols['c_campana'])}", _clean_list(filters.get("tipo_campana")), params),
        _in_filter(f"{c}.{_quote(cols['c_marca'])}", _clean_list(filters.get("detalle_marca")), params),
    ])
    contencion_state = _clean_list(filters.get("estado_contencion"))
    if contencion_state:
        marks = ",".join("?" for _ in contencion_state)
        parts.append(
            f" AND CASE WHEN ISNULL(TRY_CAST({c}.{_quote(cols['c_contencion'])} AS float), 0) > 0 "
            f"THEN 'SI' ELSE 'NO' END IN ({marks})"
        )
        params.extend(contencion_state)
    return "".join(parts), params


def _build_batch(filters: dict, include_detail: bool) -> tuple[str, list[Any], str, str, dict]:
    cols = _resolved()
    period = _parse_period(filters.get("periodo") or filters.get("fecha_proceso"))
    process_date = _resolve_contencion_date(period)
    start, end = _period_bounds(period)
    filter_sql, params = _filter_sql_and_params(filters, cols)

    c_rut = _value_expr("c", cols["c_rut"])
    c_operation = _value_expr("c", cols["c_operacion"])
    g_rut = _value_expr("g", cols["g_rut"])
    g_operation = _value_expr("g", cols["g_operacion"])
    p_rut = _value_expr("p", cols["p_rut"])
    p_gestion = _value_expr("p", cols["p_fecha_gestion"])
    p_compromiso = (
        f"MAX({_value_expr('p', cols['p_fecha_compromiso'])})"
        if cols["p_fecha_compromiso"]
        else "CAST(NULL AS date)"
    )
    compromiso_not_null = (
        f"AND {_value_expr('p', cols['p_fecha_compromiso'])} IS NOT NULL"
        if cols["p_fecha_compromiso"]
        else ""
    )
    contencion_flag = (
        f"MAX(CASE WHEN ISNULL(TRY_CAST(c.{_quote(cols['c_contencion'])} AS float), 0) > 0 "
        f"THEN 1 ELSE 0 END)"
    )
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
        contact_sql = f" AND estado_contacto IN ({marks})"

    params.insert(0, process_date)
    params.extend([CRM_CARTERA, start.isoformat(), end.isoformat()])
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
        SELECT [rut], [operacion], [ultima_gestion], [tipo_gestion], [contuvo], [fecha_promesa],
               [gestor], [cantidad_gestiones], [estado_contacto],
               COUNT(*) OVER() AS total_rows
        FROM #clasificado
        {detail_where}
        ORDER BY {order_by}
        OFFSET ? ROWS FETCH NEXT ? ROWS ONLY;
        """

    sql = f"""
    SET NOCOUNT ON;

    SELECT {c_rut} AS rut_contencion,
           {c_operation} AS operacion,
           {contencion_flag} AS tiene_contencion
    INTO #contencion_filtrada
    FROM {_table('contencion')} c
    WHERE c.{_quote(cols['c_fecha'])} = ?
      {filter_sql}
    GROUP BY {c_rut}, {c_operation};

    CREATE INDEX IX_tmp_contactabilidad_contencion_operacion
        ON #contencion_filtrada(operacion);

    SELECT rut_contencion AS rut,
           rut_contencion,
           MAX(operacion) AS operacion,
           MAX(tiene_contencion) AS tiene_contencion
    INTO #universo_cliente
    FROM #contencion_filtrada
    GROUP BY rut_contencion;

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
      ;

    CREATE INDEX IX_tmp_contactabilidad_crm_rut_fecha
        ON #crm_base(rut_contencion, gestion_fecha);

    -- Gestión que representa al cliente: la de mejor contacto del período
    -- (Titular > Tercero > resto), desempatando por la más reciente.
    SELECT rut_contencion, accion, contacto
    INTO #mejor_gestion
    FROM (
        SELECT rut_contencion,
               accion,
               contacto,
               ROW_NUMBER() OVER (
                   PARTITION BY rut_contencion
                   ORDER BY CASE
                              WHEN contacto = 'TITULAR' THEN 1
                              WHEN contacto IN ('TERCERO', 'TERCEROS', 'CONTACTO TERCERO') THEN 2
                              ELSE 3
                            END,
                            gestion_fecha DESC,
                            accion,
                            contacto
               ) AS rn
        FROM #crm_base
    ) ranked
    WHERE rn = 1;

    CREATE UNIQUE CLUSTERED INDEX IX_tmp_contactabilidad_mejor_gestion
        ON #mejor_gestion(rut_contencion);

    SELECT {p_rut} AS rut_promesa,
           MAX({p_gestion}) AS ultima_gestion_promesa,
           {p_compromiso} AS ultima_fecha_compromiso
    INTO #promesas
    FROM {_table('promesas')} p
    INNER JOIN #universo_cliente u
            ON u.rut_contencion = TRY_CAST({p_rut} AS decimal(38, 0))
    WHERE p.{_quote(cols['p_cartera'])} = ?
      AND {p_gestion} >= ?
      AND {p_gestion} < ?
      {compromiso_not_null}
    GROUP BY {p_rut};

    CREATE UNIQUE CLUSTERED INDEX IX_tmp_contactabilidad_promesas_rut
        ON #promesas(rut_promesa);

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
           CASE WHEN pr.rut_promesa IS NOT NULL THEN 1 ELSE 0 END AS tiene_promesa,
           CASE WHEN pr.rut_promesa IS NOT NULL AND u.tiene_contencion = 1
                THEN 1 ELSE 0 END AS promesa_cumplida,
           pr.ultima_gestion_promesa,
           pr.ultima_fecha_compromiso AS fecha_promesa,
           mg.accion AS tipo_gestion,
           CASE WHEN u.tiene_contencion = 1 THEN 'SI' ELSE 'NO' END AS contuvo,
           e.tiene_titular AS es_titular,
           CASE WHEN e.tiene_titular = 0 AND e.tiene_tercero = 1
                THEN 1 ELSE 0 END AS es_tercero,
           CASE WHEN e.total_eventos > 0 AND e.tiene_titular = 0 AND e.tiene_tercero = 0
                THEN 1 ELSE 0 END AS es_sin_contacto,
           CASE WHEN e.total_eventos = 0 THEN 1 ELSE 0 END AS es_sin_gestion,
           CASE
             WHEN e.tiene_titular = 1 THEN 'Contacto Titular'
             WHEN e.tiene_tercero = 1 THEN 'Contacto Tercero'
             WHEN e.total_eventos > 0 THEN 'Sin Contacto'
             ELSE 'Sin Gestión'
           END AS estado_contacto,
           e.total_call_terreno AS cantidad_gestiones
    INTO #clasificado_base
    FROM #universo_cliente u
    INNER JOIN #eventos_cliente e ON e.rut = u.rut
    LEFT JOIN #promesas pr ON pr.rut_promesa = u.rut_contencion
    LEFT JOIN #mejor_gestion mg ON mg.rut_contencion = u.rut_contencion;

    SELECT *
    INTO #clasificado
    FROM #clasificado_base
    WHERE 1 = 1
      {contact_sql};

    CREATE UNIQUE CLUSTERED INDEX IX_tmp_contactabilidad_clasificado_rut
        ON #clasificado(rut);

    SELECT COUNT(*) AS total_clientes,
           COALESCE(SUM(total_call_terreno), 0) AS total_gestiones,
           COALESCE(SUM(CASE WHEN total_eventos > 0 THEN 1 ELSE 0 END), 0) AS clientes_gestionados,
           COALESCE(SUM(es_titular), 0) AS contacto_titular,
           COALESCE(SUM(es_tercero), 0) AS contacto_tercero,
           COALESCE(SUM(es_sin_contacto), 0) AS sin_contacto,
           COALESCE(SUM(tiene_call_terreno), 0) AS clientes_call_terreno,
           COALESCE(SUM(es_sin_gestion), 0) AS sin_gestion,
           COALESCE(SUM(tiene_promesa), 0) AS casos_promesa,
           COALESCE(SUM(promesa_cumplida), 0) AS promesas_cumplidas
    INTO #resumen
    FROM #clasificado;

    SELECT total_clientes, total_gestiones, clientes_gestionados, contacto_titular,
           contacto_tercero, sin_contacto, clientes_call_terreno, sin_gestion,
           casos_promesa, promesas_cumplidas
    FROM #resumen;

    SELECT '{DEFAULT_GESTOR}' AS gestor, estado, clientes,
           CASE WHEN total_clientes = 0 THEN 0 ELSE CAST(clientes AS decimal(18,6)) / total_clientes END AS porcentaje
    FROM (
        SELECT 'Contacto Titular' AS estado, contacto_titular AS clientes, total_clientes FROM #resumen
        UNION ALL SELECT 'Contacto Tercero', contacto_tercero, total_clientes FROM #resumen
        UNION ALL SELECT 'Sin Contacto', sin_contacto, total_clientes FROM #resumen
        UNION ALL SELECT 'Sin Gestión', sin_gestion, total_clientes FROM #resumen
    ) estados;

    SELECT '{DEFAULT_GESTOR}' AS gestor,
           CASE WHEN total_clientes = 0 THEN 0 ELSE CAST(total_gestiones AS decimal(18,6)) / total_clientes END AS recurrencia,
           total_clientes AS casos_asignados,
           clientes_gestionados AS casos_con_gestion,
           CASE WHEN total_clientes = 0 THEN 0 ELSE CAST(clientes_gestionados AS decimal(18,6)) / total_clientes END AS porcentaje_gestionado,
           contacto_titular AS casos_contacto_titular,
           CASE WHEN total_clientes = 0 THEN 0 ELSE CAST(contacto_titular AS decimal(18,6)) / total_clientes END AS porcentaje_contacto_titular,
           contacto_tercero AS casos_contacto_tercero,
           CASE WHEN total_clientes = 0 THEN 0 ELSE CAST(contacto_tercero AS decimal(18,6)) / total_clientes END AS porcentaje_contacto_tercero,
           sin_contacto AS casos_sin_contacto,
           CASE WHEN total_clientes = 0 THEN 0 ELSE CAST(sin_contacto AS decimal(18,6)) / total_clientes END AS porcentaje_sin_contacto,
           casos_promesa,
           CASE WHEN total_clientes = 0 THEN 0 ELSE CAST(casos_promesa AS decimal(18,6)) / total_clientes END AS porcentaje_promesa,
           promesas_cumplidas,
           CASE WHEN casos_promesa = 0 THEN 0 ELSE CAST(promesas_cumplidas AS decimal(18,6)) / casos_promesa END AS porcentaje_promesa_cumplida
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
    return sql, params, period, process_date, {"page": page, "page_size": page_size}


def _execute_dashboard(filters: dict, include_detail: bool = True) -> tuple[str, str, list[list[dict]], dict]:
    sql, params, period, process_date, pagination = _build_batch(filters, include_detail)
    started = monotonic()
    result_sets = run_query_sets(sql, tuple(params))
    logger.info(
        "Contactabilidad Itaú Vencida procesada: periodo=%s contencion=%s detalle=%s tiempo=%.3fs",
        period,
        process_date,
        include_detail,
        monotonic() - started,
    )
    return period, process_date, result_sets, pagination


def _summary_response(row: dict, period: str, process_date: str) -> dict:
    total = int(row.get("total_clientes") or 0)
    managed = int(row.get("clientes_gestionados") or 0)
    gestures = int(row.get("total_gestiones") or 0)
    titular = int(row.get("contacto_titular") or 0)
    tercero = int(row.get("contacto_tercero") or 0)
    sin_contacto = int(row.get("sin_contacto") or 0)
    sin_gestion = int(row.get("sin_gestion") or 0)
    promesas = int(row.get("casos_promesa") or 0)
    cumplidas = int(row.get("promesas_cumplidas") or 0)
    return {
        "periodo": period,
        "fecha_contencion": process_date,
        "fecha_proceso": process_date,
        "total_gestiones": gestures,
        "total_clientes": total,
        "clientes_gestionados": managed,
        "recurrencia": _safe_div(gestures, total),
        "porcentaje_gestionado": _safe_div(managed, total),
        "contacto_titular": titular,
        "porcentaje_contacto_titular": _safe_div(titular, total),
        "contacto_tercero": tercero,
        "porcentaje_contacto_tercero": _safe_div(tercero, total),
        "sin_contacto": sin_contacto,
        "porcentaje_sin_contacto": _safe_div(sin_contacto, total),
        "clientes_call_terreno": int(row.get("clientes_call_terreno") or 0),
        "sin_gestion": sin_gestion,
        "porcentaje_sin_gestion": _safe_div(sin_gestion, total),
        "casos_promesa": promesas,
        "porcentaje_promesa": _safe_div(promesas, total),
        "promesas_cumplidas": cumplidas,
        "porcentaje_promesa_cumplida": _safe_div(cumplidas, promesas),
    }


def _dashboard_response(filters: dict, include_detail: bool = True) -> dict:
    period, process_date, result_sets, pagination = _execute_dashboard(filters, include_detail)
    summary = _summary_response(
        result_sets[0][0] if result_sets and result_sets[0] else {}, period, process_date
    )
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
        "periodo": period,
        "fecha_contencion": process_date,
        "fecha_proceso": process_date,
    }
    return {
        "periodo": period,
        "fecha_contencion": process_date,
        "resumen": summary,
        "estado": {"rows": state_rows, "total_clientes": total},
        "estado_contacto": {"rows": state_rows, "total_clientes": total},
        "tubo": {"rows": tube_rows},
        "evolucion": get_evolucion_comparativa(filters),
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
    return get_evolucion_comparativa(filters)


def get_detalle(filters: dict) -> dict:
    return _dashboard_response(filters, include_detail=True)["detalle"]


def _previous_period(period: str) -> str:
    year, month = int(period[:4]), int(period[5:7])
    return f"{year - 1}-12" if month == 1 else f"{year}-{month - 1:02d}"


def _period_title(period: str) -> str:
    meses = ("Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
             "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre")
    return f"{meses[int(period[5:7]) - 1]} {period[:4]}"


def _calendario_habiles(period: str) -> dict[str, int]:
    """Fecha ISO -> días hábiles al cierre, en negativo (0 = último día hábil del mes).

    Se calcula con el catálogo de feriados de Chile en vez de leer
    dbo.tmp_BENCH_CONTROL_DIARIO: esa tabla sólo trae los días que el Excel BENCH
    alcanzó a cargar (a junio de 2026 le falta el día 1, que es hábil). Para agosto y
    julio de 2026 ambos criterios dan exactamente el mismo resultado.
    """
    start, end = _period_bounds(period)
    return dias_habiles_al_cierre(start, end)


def _serie_titular_diaria(filters: dict, period: str) -> dict | None:
    """Universo y contacto titular por día del período. None si el mes no tiene contención."""
    try:
        process_date = _resolve_contencion_date(period)
    except PeriodoSinContencion:
        return None

    cols = _resolved()
    start, end = _period_bounds(period)
    filter_sql, params = _filter_sql_and_params(filters, cols)
    c_rut = _value_expr("c", cols["c_rut"])
    g_rut = _value_expr("g", cols["g_rut"])

    params.insert(0, process_date)
    params.extend([CRM_CARTERA, start.isoformat(), end.isoformat()])

    sql = f"""
    SET NOCOUNT ON;

    SELECT {c_rut} AS rut
    INTO #universo_periodo
    FROM {_table('contencion')} c
    WHERE c.{_quote(cols['c_fecha'])} = ?
      {filter_sql}
    GROUP BY {c_rut};

    CREATE UNIQUE CLUSTERED INDEX IX_tmp_contactabilidad_evol_rut
        ON #universo_periodo(rut);

    SELECT COUNT(*) AS total_casos FROM #universo_periodo;

    -- COUNT(DISTINCT rut) por fecha: un RUT cuenta una sola vez por día,
    -- aunque tenga varias gestiones TITULAR ese mismo día.
    SELECT CONVERT(char(10), g.{_quote(cols['g_fecha'])}, 126) AS fecha,
           COUNT(DISTINCT {g_rut}) AS casos_titular
    FROM {_table('crm')} g
    INNER JOIN #universo_periodo u ON u.rut = {g_rut}
    WHERE g.{_quote(cols['g_cartera'])} = ?
      AND g.{_quote(cols['g_fecha'])} >= ?
      AND g.{_quote(cols['g_fecha'])} < ?
      AND UPPER(LTRIM(RTRIM(g.{_quote(cols['g_contacto'])}))) = 'TITULAR'
    GROUP BY CONVERT(char(10), g.{_quote(cols['g_fecha'])}, 126)
    ORDER BY fecha;
    """
    result_sets = run_query_sets(sql, tuple(params))
    total = int(result_sets[0][0].get("total_casos") or 0) if result_sets and result_sets[0] else 0
    por_fecha = {
        _text(row.get("fecha")): int(row.get("casos_titular") or 0)
        for row in (result_sets[1] if len(result_sets) > 1 else [])
    }
    return {
        "periodo": period,
        "etiqueta": _period_title(period),
        "fecha_contencion": process_date,
        "total_casos": total,
        "por_fecha": por_fecha,
    }


def get_evolucion_comparativa(filters: dict) -> dict:
    """% Contacto Titular DIARIO del período contra el mes anterior, alineados por
    días hábiles al cierre. Cada mes usa su propia contención como denominador."""
    period = _parse_period(filters.get("periodo") or filters.get("fecha_proceso"))
    actual = _serie_titular_diaria(filters, period)
    if actual is None:
        raise PeriodoSinContencion(
            f"No existe información de contención para el período {period}."
        )
    anterior = _serie_titular_diaria(filters, _previous_period(period))

    hoy = date.today().isoformat()

    def puntos(serie: dict | None) -> dict[int, dict]:
        if not serie:
            return {}
        salida: dict[int, dict] = {}
        for fecha, dias in _calendario_habiles(serie["periodo"]).items():
            # Un día que todavía no ocurre no genera punto; uno que ya pasó sin
            # contacto titular vale 0%.
            if fecha > hoy:
                continue
            casos = serie["por_fecha"].get(fecha, 0)
            salida[dias] = {
                "fecha": fecha,
                "casos_titular": casos,
                "porcentaje_titular": _safe_div(casos, serie["total_casos"]),
            }
        return salida

    puntos_actual, puntos_anterior = puntos(actual), puntos(anterior)
    rows = []
    for dias in sorted(set(puntos_actual) | set(puntos_anterior)):
        a, b = puntos_actual.get(dias), puntos_anterior.get(dias)
        rows.append({
            "dias_habiles_cierre": dias,
            "actual": a,
            "anterior": b,
            "diferencia_pp": (
                round((a["porcentaje_titular"] - b["porcentaje_titular"]) * 100, 2)
                if a and b else None
            ),
        })

    def meta(serie: dict | None) -> dict | None:
        return None if not serie else {
            "periodo": serie["periodo"],
            "etiqueta": serie["etiqueta"],
            "fecha_contencion": serie["fecha_contencion"],
            "total_casos": serie["total_casos"],
        }

    return {
        "periodo_actual": meta(actual),
        "periodo_anterior": meta(anterior),
        "rows": rows,
    }


def _max_text(alias: str, column: str | None) -> str:
    return f"MAX({alias}.{_quote(column)})" if column else "CAST(NULL AS nvarchar(255))"


def _build_export_batch(filters: dict) -> tuple[str, list[Any], str]:
    """Detalle a grano operación para el Excel.

    El universo son TODAS las operaciones de la contención que pasan los filtros,
    la misma base que usan los indicadores del dashboard.
    """
    cols = _resolved()
    period = _parse_period(filters.get("periodo") or filters.get("fecha_proceso"))
    process_date = _resolve_contencion_date(period)
    start, end = _period_bounds(period)
    filter_sql, params = _filter_sql_and_params(filters, cols)

    c_rut = _value_expr("c", cols["c_rut"])
    c_operation = _value_expr("c", cols["c_operacion"])
    g_rut = _value_expr("g", cols["g_rut"])
    p_rut = _value_expr("p", cols["p_rut"])
    p_gestion = _value_expr("p", cols["p_fecha_gestion"])
    p_compromiso = (
        f"MAX({_value_expr('p', cols['p_fecha_compromiso'])})"
        if cols["p_fecha_compromiso"]
        else "CAST(NULL AS date)"
    )
    compromiso_not_null = (
        f"AND {_value_expr('p', cols['p_fecha_compromiso'])} IS NOT NULL"
        if cols["p_fecha_compromiso"]
        else ""
    )

    contact_filter = _clean_list(filters.get("estado_contacto"))

    params.insert(0, process_date)
    params.extend([CRM_CARTERA, start.isoformat(), end.isoformat()])
    params.extend([CRM_CARTERA, start.isoformat(), end.isoformat()])

    # El filtro y la búsqueda se aplican sobre el cliente ya clasificado, igual que en
    # el dashboard, para que la descarga traiga exactamente lo que muestra la pantalla.
    conditions = []
    if contact_filter:
        marks = ",".join("?" for _ in contact_filter)
        conditions.append(f"estado_contacto IN ({marks})")
        params.extend(contact_filter)

    search = _text(filters.get("search"))
    if search:
        conditions.append(
            "(CONVERT(nvarchar(255), rut_contencion) LIKE ? OR COALESCE(operacion, '') LIKE ?)"
        )
        params.extend([f"%{search}%", f"%{search}%"])

    search_sql = (" WHERE " + " AND ".join(conditions)) if conditions else ""

    sql = f"""
    SET NOCOUNT ON;

    SELECT {c_rut} AS rut_contencion,
           {c_operation} AS operacion,
           {_max_text('c', cols['c_dv'])} AS dv,
           {_max_text('c', cols['c_nombre'])} AS nombre,
           {_max_text('c', cols['c_glosa_tipo_cartera'])} AS glosa_tipo_cartera,
           {_max_text('c', cols['c_producto'])} AS producto,
           {_max_text('c', cols['c_canal'])} AS canal,
           {_max_text('c', cols['c_segmento'])} AS segmento,
           {_max_text('c', cols['c_marca'])} AS detalle_marca,
           {_max_text('c', cols['c_campana'])} AS campana,
           MAX(TRY_CAST(c.{_quote(cols['c_contencion'])} AS float)) AS contencion
    INTO #contencion_export
    FROM {_table('contencion')} c
    WHERE c.{_quote(cols['c_fecha'])} = ?
      {filter_sql}
    GROUP BY {c_rut}, {c_operation};

    CREATE INDEX IX_tmp_contactabilidad_export_rut
        ON #contencion_export(rut_contencion);

    SELECT DISTINCT rut_contencion
    INTO #universo_rut
    FROM #contencion_export;

    SELECT {g_rut} AS rut_contencion,
           g.{_quote(cols['g_fecha'])} AS gestion_fecha,
           UPPER(LTRIM(RTRIM(g.{_quote(cols['g_accion'])}))) AS accion,
           UPPER(LTRIM(RTRIM(g.{_quote(cols['g_contacto'])}))) AS contacto
    INTO #crm_base
    FROM {_table('crm')} g
    INNER JOIN #universo_rut u ON u.rut_contencion = {g_rut}
    WHERE g.{_quote(cols['g_cartera'])} = ?
      AND g.{_quote(cols['g_fecha'])} >= ?
      AND g.{_quote(cols['g_fecha'])} < ?
      AND {g_rut} IS NOT NULL
      AND CONVERT(nvarchar(255), {g_rut}) <> '';

    SELECT rut_contencion, gestion_fecha, accion, contacto
    INTO #mejor_gestion
    FROM (
        SELECT rut_contencion,
               gestion_fecha,
               accion,
               contacto,
               ROW_NUMBER() OVER (
                   PARTITION BY rut_contencion
                   ORDER BY CASE
                              WHEN contacto = 'TITULAR' THEN 1
                              WHEN contacto IN ('TERCERO', 'TERCEROS', 'CONTACTO TERCERO') THEN 2
                              ELSE 3
                            END,
                            gestion_fecha DESC,
                            accion,
                            contacto
               ) AS rn
        FROM #crm_base
    ) ranked
    WHERE rn = 1;

    CREATE UNIQUE CLUSTERED INDEX IX_tmp_contactabilidad_export_gestion
        ON #mejor_gestion(rut_contencion);

    SELECT {p_rut} AS rut_promesa,
           {p_compromiso} AS fecha_promesa
    INTO #promesas_export
    FROM {_table('promesas')} p
    INNER JOIN #universo_rut u
            ON u.rut_contencion = TRY_CAST({p_rut} AS decimal(38, 0))
    WHERE p.{_quote(cols['p_cartera'])} = ?
      AND {p_gestion} >= ?
      AND {p_gestion} < ?
      {compromiso_not_null}
    GROUP BY {p_rut};

    CREATE UNIQUE CLUSTERED INDEX IX_tmp_contactabilidad_export_promesas
        ON #promesas_export(rut_promesa);

    SELECT TOP {EXPORT_MAX_ROWS}
           operacion AS [OP],
           rut_contencion AS [RUT],
           dv AS [DV],
           nombre AS [NOMBRE],
           glosa_tipo_cartera AS [GLOSA TIPO CARTERA],
           producto AS [PRODUCTO],
           canal AS [CANAL],
           segmento AS [SEGMENTO],
           detalle_marca AS [DETALLE MARCA],
           campana AS [CAMPAÑA],
           gestion_fecha AS [FECHA GESTION],
           accion AS [TIPO GESTION],
           contacto AS [GESTION],
           contencion AS [CONTENCION],
           fecha_promesa AS [FECHA PROMESA],
           promesa_cumplida AS [PROMESA CUMPLIDA]
    FROM (
        SELECT ce.operacion, ce.rut_contencion, ce.dv, ce.nombre, ce.glosa_tipo_cartera,
               ce.producto, ce.canal, ce.segmento, ce.detalle_marca, ce.campana,
               ce.contencion, mg.gestion_fecha, mg.accion, mg.contacto,
               pe.fecha_promesa,
               -- Misma regla que el dashboard: la contención se evalúa a nivel CLIENTE,
               -- así que basta una operación del RUT con saldo contenido mayor que cero.
               CASE
                 WHEN pe.rut_promesa IS NULL THEN ''
                 WHEN MAX(CASE WHEN ISNULL(ce.contencion, 0) > 0 THEN 1 ELSE 0 END)
                        OVER (PARTITION BY ce.rut_contencion) = 1 THEN 'SI'
                 ELSE 'NO'
               END AS promesa_cumplida,
               CASE
                 WHEN mg.contacto = 'TITULAR' THEN 'Contacto Titular'
                 WHEN mg.contacto IN ('TERCERO', 'TERCEROS', 'CONTACTO TERCERO') THEN 'Contacto Tercero'
                 WHEN mg.rut_contencion IS NOT NULL THEN 'Sin Contacto'
                 ELSE 'Sin Gestión'
               END AS estado_contacto
        FROM #contencion_export ce
        LEFT JOIN #mejor_gestion mg ON mg.rut_contencion = ce.rut_contencion
        LEFT JOIN #promesas_export pe ON pe.rut_promesa = ce.rut_contencion
    ) detalle
    {search_sql}
    ORDER BY rut_contencion, operacion;
    """
    return sql, params, period, process_date


def get_detalle_export_rows(filters: dict) -> tuple[str, str, list[str], list[dict]]:
    sql, params, period, process_date = _build_export_batch(filters)
    started = monotonic()
    result_sets = run_query_sets(sql, tuple(params))
    rows = result_sets[-1] if result_sets else []
    logger.info(
        "Export Contactabilidad Itaú Vencida: periodo=%s contencion=%s filas=%s tiempo=%.3fs",
        period,
        process_date,
        len(rows),
        monotonic() - started,
    )
    return period, process_date, EXPORT_HEADERS, rows


def _filter_values_uncached(period: str, process_date: str) -> dict:
    cols = _resolved()
    statements = []
    value_columns = [
        ("segmentos", cols["c_segmento"]),
        ("canales", cols["c_canal"]),
        ("fases_cliente", cols["c_fase"]),
        ("sub_productos", cols["c_producto"]),
        ("tipos_campana", cols["c_campana"]),
        ("detalles_marca", cols["c_marca"]),
    ]
    if cols.get("c_glosa_tipo_cartera"):
        value_columns.insert(3, ("glosas_tipo_cartera", cols["c_glosa_tipo_cartera"]))
    for _, column in value_columns:
        statements.append(
            f"SELECT DISTINCT LTRIM(RTRIM(CONVERT(nvarchar(255), {_quote(column)}))) AS valor "
            f"FROM {_table('contencion')} "
            f"WHERE {_quote(cols['c_fecha'])} = ? AND {_quote(cols['c_gestor'])} = ? "
            f"AND {_quote(column)} IS NOT NULL "
            f"AND LTRIM(RTRIM(CONVERT(nvarchar(255), {_quote(column)}))) <> '' "
            f"ORDER BY valor"
        )
    params: list[Any] = []
    for _ in value_columns:
        params.extend([process_date, DEFAULT_GESTOR])
    result_sets = run_query_sets("SET NOCOUNT ON;\n" + ";\n".join(statements), tuple(params))

    def values(index: int) -> list[str]:
        return [_text(row.get("valor")) for row in result_sets[index] if _text(row.get("valor"))]

    option_values = {
        key: values(index)
        for index, (key, _) in enumerate(value_columns)
    }
    return {
        "periodos": _periodos_disponibles(),
        "periodo": period,
        "fecha_contencion": process_date,
        "fecha_proceso": process_date,
        "segmentos": option_values["segmentos"],
        "canales": option_values["canales"],
        "gestores": [DEFAULT_GESTOR],
        "fases_cliente": option_values["fases_cliente"],
        "glosas_tipo_cartera": option_values.get("glosas_tipo_cartera", []),
        "sub_productos": option_values["sub_productos"],
        "productos": option_values["sub_productos"],
        "tipos_campana": option_values["tipos_campana"],
        "detalles_marca": option_values["detalles_marca"],
        "estados_contencion": ["SI", "NO"],
        "estados_contacto": ["Contacto Titular", "Contacto Tercero", "Sin Contacto", "Sin Gestión"],
    }


def get_filter_values(filters: dict | None = None) -> dict:
    source = filters or {}
    period = _parse_period(source.get("periodo") or source.get("fecha_proceso"))
    process_date = _resolve_contencion_date(period)
    now = monotonic()
    with _filter_cache_lock:
        cached = _filter_cache.get(period)
        if cached and now - cached[0] < FILTER_CACHE_TTL_SECONDS:
            return deepcopy(cached[1])
    result = _filter_values_uncached(period, process_date)
    logger.info(
        "Filtros Contactabilidad Itaú Vencida obtenidos: periodo=%s contencion=%s",
        period,
        process_date,
    )
    with _filter_cache_lock:
        _filter_cache[period] = (monotonic(), deepcopy(result))
        expired = [key for key, (created, _) in _filter_cache.items() if monotonic() - created >= FILTER_CACHE_TTL_SECONDS]
        for key in expired:
            _filter_cache.pop(key, None)
    return result
