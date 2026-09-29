"""KPI Operacional: lee las tablas consolidadas que arma dbo.sp_kpi_operacional_cargar (sql/007_kpi_operacional.sql).

Universo:
  - Casos = RUT unico por mandante (dentro de un mandante, un RUT en dos carteras cuenta una vez).
  - Gestiones y compromisos solo cuentan para RUT asignados.
  - Pagos incluyen todo lo pagado/contenido; los de RUT fuera de la asignacion quedan con tramo
    'Sin asignación' y no entran al % de recuperacion.
"""

from __future__ import annotations

import re
from datetime import date

from database import run_query


SIN_PRODUCTO = "Sin producto"
SIN_ASIGNACION = "Sin asignación"
TIPOS_CONTACTO = ["DIRECTO", "INDIRECTO", "SIN CONTACTO"]


def _clean(value: object) -> str:
    return str(value or "").strip()


def _safe_div(num: float, den: float) -> float | None:
    return num / den if den else None


def _periodo(value: object) -> str | None:
    text = _clean(value)
    return text if re.fullmatch(r"\d{4}-\d{2}", text) else None


def _periodos_disponibles() -> list[str]:
    rows = run_query(
        """
        SELECT periodo FROM dbo.kpi_asignacion
        UNION
        SELECT periodo FROM dbo.kpi_pagos
        ORDER BY periodo DESC
        """
    )
    return [row["periodo"] for row in rows if row.get("periodo")]


def _resolve_periodo(filters: dict) -> str | None:
    periodo = _periodo(filters.get("periodo"))
    if periodo:
        return periodo
    periodos = _periodos_disponibles()
    return periodos[0] if periodos else None


def _dimension_filters(filters: dict, alias: str, include: tuple[str, ...] = ("mandante", "cartera", "tramo", "producto")) -> tuple[str, list]:
    """Filtros de mandante/cartera/tramo/producto sobre kpi_asignacion o kpi_pagos (mismas columnas)."""
    clauses: list[str] = []
    params: list = []
    for field in include:
        value = _clean(filters.get(field))
        if not value:
            continue
        if field == "producto" and value == SIN_PRODUCTO:
            clauses.append(f"{alias}.producto IS NULL")
            continue
        clauses.append(f"{alias}.{field} = ?")
        params.append(value)
    return "".join(f" AND {c}" for c in clauses), params


# CTE con los RUT asignados del filtro y sus gestiones del mes (mejor contacto por mandante + RUT).
def _asignados_cte(filters: dict, periodo: str) -> tuple[str, list]:
    dim_sql, dim_params = _dimension_filters(filters, "a")
    sql = f"""
    asig AS (
        SELECT DISTINCT a.mandante, a.cartera, a.rut
        FROM dbo.kpi_asignacion a
        WHERE a.periodo = ?{dim_sql}
    ),
    casos AS (
        SELECT DISTINCT mandante, rut FROM asig
    ),
    gest AS (
        SELECT s.mandante, s.rut,
               MIN(CASE g.tipo_contacto WHEN 'DIRECTO' THEN 1 WHEN 'INDIRECTO' THEN 2 ELSE 3 END) AS mejor,
               MIN(g.fecha_primera_gestion) AS f_gestion,
               MIN(g.fecha_primer_directo) AS f_directo,
               SUM(g.n_gestiones) AS n_gestiones
        FROM asig s
        INNER JOIN dbo.kpi_crm_cartera k
            ON k.mandante = s.mandante AND (k.cartera IS NULL OR k.cartera = s.cartera)
        INNER JOIN dbo.kpi_gestiones_rut g
            ON g.periodo = ? AND g.crm_cartera = k.crm_cartera AND g.rut = s.rut
        GROUP BY s.mandante, s.rut
    )
    """
    return sql, [periodo, *dim_params, periodo]


def get_filter_values(filters: dict | None = None) -> dict:
    filters = filters or {}
    periodos = _periodos_disponibles()
    periodo = _periodo(filters.get("periodo")) or (periodos[0] if periodos else None)
    if not periodo:
        return {"periodos": [], "periodo": None, "mandantes": [], "carteras": [], "tramos": [], "productos": []}

    def distinct(field: str, include: tuple[str, ...]) -> list[str]:
        dim_sql, dim_params = _dimension_filters(filters, "a", include)
        expr = f"ISNULL(a.producto, '{SIN_PRODUCTO}')" if field == "producto" else f"a.{field}"
        rows = run_query(
            f"SELECT DISTINCT {expr} AS valor FROM dbo.kpi_asignacion a WHERE a.periodo = ?{dim_sql} ORDER BY valor",
            (periodo, *dim_params),
        )
        return [row["valor"] for row in rows if row.get("valor")]

    # Cada filtro solo ofrece lo disponible en el periodo y en los filtros superiores.
    return {
        "periodos": periodos,
        "periodo": periodo,
        "mandantes": distinct("mandante", ()),
        "carteras": distinct("cartera", ("mandante",)),
        "tramos": distinct("tramo", ("mandante", "cartera")),
        "productos": distinct("producto", ("mandante", "cartera", "tramo")),
    }


def _fecha_corte(periodo: str) -> date:
    """Hoy si el periodo esta en curso; si no, el ultimo dia del periodo."""
    year, month = (int(x) for x in periodo.split("-"))
    fin = date(year + (month == 12), month % 12 + 1, 1)
    hoy = date.today()
    return hoy if hoy < fin else date.fromordinal(fin.toordinal() - 1)


def get_dashboard(filters: dict) -> dict:
    periodo = _resolve_periodo(filters)
    if not periodo:
        return {"periodo": None, "vacio": True}

    corte = _fecha_corte(periodo)
    dim_a_sql, dim_a_params = _dimension_filters(filters, "a")
    dim_p_sql, dim_p_params = _dimension_filters(filters, "p")

    # --- Asignacion ---
    asig = run_query(
        f"""
        SELECT COUNT(DISTINCT CONCAT(a.mandante, '|', a.rut)) AS casos,
               COUNT(*) AS operaciones,
               SUM(CAST(a.saldo_asignado AS float)) AS saldo,
               MAX(a.fecha_corte) AS fecha_corte
        FROM dbo.kpi_asignacion a
        WHERE a.periodo = ?{dim_a_sql}
        """,
        (periodo, *dim_a_params),
    )[0]

    por_tramo = run_query(
        f"""
        SELECT a.mandante, a.cartera, a.tramo,
               COUNT(DISTINCT CONCAT(a.mandante, '|', a.rut)) AS casos,
               COUNT(*) AS operaciones,
               SUM(CAST(a.saldo_asignado AS float)) AS saldo
        FROM dbo.kpi_asignacion a
        WHERE a.periodo = ?{dim_a_sql}
        GROUP BY a.mandante, a.cartera, a.tramo
        """,
        (periodo, *dim_a_params),
    )

    # RUT unico por mandante y cartera (sumar los tramos contaria dos veces un RUT con operaciones en dos tramos).
    por_cartera = run_query(
        f"""
        SELECT a.mandante, a.cartera,
               COUNT(DISTINCT a.rut) AS casos,
               COUNT(*) AS operaciones,
               SUM(CAST(a.saldo_asignado AS float)) AS saldo
        FROM dbo.kpi_asignacion a
        WHERE a.periodo = ?{dim_a_sql}
        GROUP BY a.mandante, a.cartera
        ORDER BY a.mandante, a.cartera
        """,
        (periodo, *dim_a_params),
    )

    # --- Pagos ---
    pagos_tramo = run_query(
        f"""
        SELECT p.mandante, p.cartera, ISNULL(p.tramo, '{SIN_ASIGNACION}') AS tramo, p.tipo_monto,
               COUNT(DISTINCT p.rut) AS ruts,
               SUM(CAST(p.monto AS float)) AS monto
        FROM dbo.kpi_pagos p
        WHERE p.periodo = ?{dim_p_sql}
        GROUP BY p.mandante, p.cartera, ISNULL(p.tramo, '{SIN_ASIGNACION}'), p.tipo_monto
        """,
        (periodo, *dim_p_params),
    )

    contacto = _contacto(filters, periodo)
    compromisos = _compromisos(filters, periodo, corte)

    evolucion_mensual = _evolucion_mensual(filters, periodo, contacto, compromisos)

    response = _build_response(periodo, corte, asig, por_tramo, pagos_tramo, contacto, compromisos, evolucion_mensual)
    response["carteras"] = [
        {"mandante": r["mandante"], "cartera": r["cartera"], "casos": int(r.get("casos") or 0),
         "operaciones": int(r.get("operaciones") or 0), "saldo": float(r.get("saldo") or 0)}
        for r in por_cartera
    ]
    return response


def _contacto(filters: dict, periodo: str) -> dict:
    """Mejor contacto del mes por RUT asignado (Directo > Indirecto > Sin contacto)."""
    cte_sql, cte_params = _asignados_cte(filters, periodo)
    return run_query(
        f"""
        ;WITH {cte_sql}
        SELECT (SELECT COUNT(*) FROM casos) AS asignados,
               COUNT(g.rut) AS gestionados,
               SUM(CASE WHEN g.mejor = 1 THEN 1 ELSE 0 END) AS directo,
               SUM(CASE WHEN g.mejor = 2 THEN 1 ELSE 0 END) AS indirecto,
               SUM(CASE WHEN g.mejor = 3 THEN 1 ELSE 0 END) AS sin_contacto,
               SUM(CAST(g.n_gestiones AS bigint)) AS gestiones
        FROM gest g
        """,
        tuple(cte_params),
    )[0]


def _compromisos(filters: dict, periodo: str, corte: date) -> list[dict]:
    """Compromisos del mes de RUT asignados, por dia de gestion y estado.

    Cumplido = hubo compromiso y el cliente pago (pago efectivo del mes en la cartera, con fecha de pago
    o de archivo igual o posterior a la gestion). Incumplido = vencido y sin pago. Pendiente = aun no vence.
    """
    cte_sql, cte_params = _asignados_cte(filters, periodo)
    return run_query(
        f"""
        ;WITH {cte_sql},
        comp AS (
            SELECT DISTINCT c.id, k.mandante, k.cartera AS crm_cartera_kpi, c.rut, c.fecha_gestion, c.fecha_compromiso,
                   c.monto_compromiso
            FROM dbo.kpi_compromisos c
            INNER JOIN dbo.kpi_crm_cartera k ON k.crm_cartera = c.crm_cartera
            INNER JOIN asig s
                ON s.mandante = k.mandante AND s.rut = c.rut AND (k.cartera IS NULL OR k.cartera = s.cartera)
            WHERE c.periodo = ?
        ),
        estado AS (
            SELECT c.*,
                   CASE
                       WHEN EXISTS (
                           SELECT 1 FROM dbo.kpi_pagos p
                           WHERE p.periodo = ? AND p.mandante = c.mandante AND p.rut = c.rut
                             AND p.pago_efectivo = 1
                             AND (c.crm_cartera_kpi IS NULL OR p.cartera = c.crm_cartera_kpi)
                             -- Sin fecha de pago (contencion), se usa la fecha del archivo.
                             AND ISNULL(p.fecha_pago, p.fecha_corte) >= CAST(c.fecha_gestion AS date)
                       ) THEN 'CUMPLIDO'
                       WHEN c.fecha_compromiso < ? THEN 'INCUMPLIDO'
                       ELSE 'PENDIENTE'
                   END AS estado
            FROM comp c
        )
        SELECT CAST(fecha_gestion AS date) AS dia, estado, COUNT(*) AS n,
               SUM(CAST(monto_compromiso AS float)) AS monto
        FROM estado
        GROUP BY CAST(fecha_gestion AS date), estado
        ORDER BY dia
        """,
        (*cte_params, periodo, periodo, corte),
    )


def _compromisos_totales(rows: list[dict]) -> dict:
    out = {"CUMPLIDO": 0, "INCUMPLIDO": 0, "PENDIENTE": 0}
    for row in rows:
        out[row["estado"]] = out.get(row["estado"], 0) + int(row.get("n") or 0)
    return out


MESES_EVOLUCION = 6


def _evolucion_mensual(filters: dict, periodo_actual: str, contacto_actual: dict, compromisos_actual: list[dict]) -> list[dict]:
    """Ultimos meses hasta el periodo seleccionado: casos, saldo, pagos, contactabilidad y compromisos."""
    dim_a_sql, dim_a_params = _dimension_filters(filters, "a")
    dim_p_sql, dim_p_params = _dimension_filters(filters, "p")
    asig = run_query(
        f"""
        SELECT a.periodo, COUNT(DISTINCT CONCAT(a.mandante, '|', a.rut)) AS casos,
               SUM(CAST(a.saldo_asignado AS float)) AS saldo
        FROM dbo.kpi_asignacion a
        WHERE 1 = 1{dim_a_sql}
        GROUP BY a.periodo
        """,
        tuple(dim_a_params),
    )
    pagos = run_query(
        f"""
        SELECT p.periodo, SUM(CAST(p.monto AS float)) AS monto,
               SUM(CASE WHEN ISNULL(p.tramo, '{SIN_ASIGNACION}') <> '{SIN_ASIGNACION}' THEN CAST(p.monto AS float) ELSE 0 END) AS monto_asignados
        FROM dbo.kpi_pagos p
        WHERE 1 = 1{dim_p_sql}
        GROUP BY p.periodo
        """,
        tuple(dim_p_params),
    )
    by_periodo: dict[str, dict] = {}
    for row in asig:
        by_periodo.setdefault(row["periodo"], {})["casos"] = int(row.get("casos") or 0)
        by_periodo[row["periodo"]]["saldo"] = float(row.get("saldo") or 0)
    for row in pagos:
        item = by_periodo.setdefault(row["periodo"], {})
        item["pagos"] = float(row.get("monto") or 0)
        item["pagos_asignados"] = float(row.get("monto_asignados") or 0)

    out = []
    periodos = [p for p in sorted(by_periodo) if p <= periodo_actual][-MESES_EVOLUCION:]
    for periodo in periodos:
        item = by_periodo[periodo]
        saldo = item.get("saldo", 0.0)
        if periodo == periodo_actual:
            contacto, compromisos = contacto_actual, compromisos_actual
        else:
            contacto = _contacto(filters, periodo)
            compromisos = _compromisos(filters, periodo, _fecha_corte(periodo))
        asignados = int(contacto.get("asignados") or 0)
        comp = _compromisos_totales(compromisos)
        out.append(
            {
                "periodo": periodo,
                "casos": item.get("casos", 0),
                "saldo": saldo,
                "pagos": item.get("pagos", 0.0),
                "recuperacion": _safe_div(item.get("pagos_asignados", 0.0), saldo),
                "contacto_directo": int(contacto.get("directo") or 0),
                "contactabilidad_asignacion": _safe_div(int(contacto.get("directo") or 0), asignados),
                "contactabilidad": _safe_div(int(contacto.get("directo") or 0), int(contacto.get("gestionados") or 0)),
                "compromisos": sum(comp.values()),
                "cumplidos": comp["CUMPLIDO"],
                "incumplidos": comp["INCUMPLIDO"],
                "pendientes": comp["PENDIENTE"],
            }
        )
    return out


def _build_response(periodo, corte, asig, por_tramo, pagos_tramo, contacto, compromisos, evolucion_mensual) -> dict:
    saldo_total = float(asig.get("saldo") or 0)

    # Tramos: asignacion y pagos en una sola lista (mandante/cartera/tramo).
    tramos: dict[tuple, dict] = {}
    for row in por_tramo:
        key = (row["mandante"], row["cartera"], row["tramo"])
        tramos[key] = {
            "mandante": row["mandante"],
            "cartera": row["cartera"],
            "tramo": row["tramo"],
            "casos": int(row.get("casos") or 0),
            "operaciones": int(row.get("operaciones") or 0),
            "saldo": float(row.get("saldo") or 0),
            "pagos": 0.0,
            "ruts_pago": 0,
        }
    pagos_total = 0.0
    pagos_asignados = 0.0
    pagos_por_tipo: dict[str, float] = {}
    for row in pagos_tramo:
        key = (row["mandante"], row["cartera"], row["tramo"])
        item = tramos.setdefault(
            key,
            {"mandante": row["mandante"], "cartera": row["cartera"], "tramo": row["tramo"],
             "casos": 0, "operaciones": 0, "saldo": 0.0, "pagos": 0.0, "ruts_pago": 0},
        )
        monto = float(row.get("monto") or 0)
        item["pagos"] += monto
        item["ruts_pago"] += int(row.get("ruts") or 0)
        pagos_total += monto
        if row["tramo"] != SIN_ASIGNACION:
            pagos_asignados += monto
        pagos_por_tipo[row["tipo_monto"]] = pagos_por_tipo.get(row["tipo_monto"], 0.0) + monto

    tramo_rows = []
    for item in tramos.values():
        item["recuperacion"] = None if item["tramo"] == SIN_ASIGNACION else _safe_div(item["pagos"], item["saldo"])
        tramo_rows.append(item)
    tramo_rows.sort(key=lambda x: (x["mandante"], x["cartera"], x["tramo"] == SIN_ASIGNACION, x["tramo"]))

    asignados = int(contacto.get("asignados") or 0)
    gestionados = int(contacto.get("gestionados") or 0)
    directo = int(contacto.get("directo") or 0)
    indirecto = int(contacto.get("indirecto") or 0)
    sin_contacto = int(contacto.get("sin_contacto") or 0)

    comp_totales = {"CUMPLIDO": 0, "INCUMPLIDO": 0, "PENDIENTE": 0}
    comp_monto = 0.0
    comp_por_dia: dict[str, dict] = {}
    for row in compromisos:
        n = int(row.get("n") or 0)
        comp_totales[row["estado"]] = comp_totales.get(row["estado"], 0) + n
        comp_monto += float(row.get("monto") or 0)
        dia = row["dia"].isoformat() if hasattr(row["dia"], "isoformat") else str(row["dia"])
        comp_por_dia.setdefault(dia, {"dia": dia, "generados": 0, "cumplidos": 0, "incumplidos": 0})
        comp_por_dia[dia]["generados"] += n
        if row["estado"] == "CUMPLIDO":
            comp_por_dia[dia]["cumplidos"] += n
        elif row["estado"] == "INCUMPLIDO":
            comp_por_dia[dia]["incumplidos"] += n
    comp_total = sum(comp_totales.values())
    comp_vencidos = comp_totales["CUMPLIDO"] + comp_totales["INCUMPLIDO"]

    fecha_corte_asig = asig.get("fecha_corte")
    return {
        "periodo": periodo,
        "fecha_corte": corte.isoformat(),
        "fecha_asignacion": fecha_corte_asig.isoformat() if hasattr(fecha_corte_asig, "isoformat") else fecha_corte_asig,
        "resumen": {
            "casos": int(asig.get("casos") or 0),
            "operaciones": int(asig.get("operaciones") or 0),
            "saldo_asignado": saldo_total,
            "pagos": pagos_total,
            "pagos_asignados": pagos_asignados,
            "pagos_fuera_asignacion": pagos_total - pagos_asignados,
            "pagos_por_tipo": pagos_por_tipo,
            "recuperacion": _safe_div(pagos_asignados, saldo_total),
            "gestionados": gestionados,
            "contacto_directo": directo,
            "contactabilidad": _safe_div(directo, gestionados),
            "cobertura": _safe_div(gestionados, asignados),
            "contacto_sobre_asignacion": _safe_div(directo, asignados),
            "gestiones": int(contacto.get("gestiones") or 0),
        },
        "tramos": tramo_rows,
        "tipos_contacto": [
            {"tipo": "DIRECTO", "ruts": directo, "pct": _safe_div(directo, gestionados)},
            {"tipo": "INDIRECTO", "ruts": indirecto, "pct": _safe_div(indirecto, gestionados)},
            {"tipo": "SIN CONTACTO", "ruts": sin_contacto, "pct": _safe_div(sin_contacto, gestionados)},
        ],
        "compromisos": {
            "total": comp_total,
            "cumplidos": comp_totales["CUMPLIDO"],
            "incumplidos": comp_totales["INCUMPLIDO"],
            "pendientes": comp_totales["PENDIENTE"],
            "monto": comp_monto,
            "cumplimiento": _safe_div(comp_totales["CUMPLIDO"], comp_vencidos),
        },
        "evolucion_compromisos": sorted(comp_por_dia.values(), key=lambda x: x["dia"]),
        "evolucion_mensual": evolucion_mensual,
    }
