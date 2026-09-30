"""KPI Operacional: lee las tablas consolidadas que arma dbo.sp_kpi_operacional_cargar (sql/007_kpi_operacional.sql).

Sin filtro de periodo: compara el mes en curso (hasta hoy) con el cierre de los 3 meses anteriores
(la ultima informacion disponible de cada mes).

Universo:
  - Casos = RUT unico por mandante (dentro de un mandante, un RUT en dos carteras cuenta una vez).
  - Asignacion = la final de cada mes (no se corta por dia).
  - Gestiones: contacto al corte segun la fecha del primer contacto de cada tipo.
  - Pagos: meses cerrados = la ultima foto disponible del mes; mes actual = la ultima foto hasta hoy
    (y fecha de pago <= corte cuando la fuente la trae).
    Solo cuentan los pagos de la asignacion; los de RUT fuera de ella quedan con tramo 'Sin asignación'.
  - Compromisos generados hasta el corte, de RUT asignados.
"""

from __future__ import annotations

import calendar
from datetime import date

from database import run_query, run_query_sets


SIN_PRODUCTO = "Sin producto"
SIN_ASIGNACION = "Sin asignación"
MESES_COMPARACION = 4  # mes actual + 3 anteriores
DIMENSIONES = ("mandante", "cartera", "tramo", "producto", "zona")

# Segmentacion de cada mandante (orden de despliegue). Los valores son los que guarda el SP de carga.
SEGMENTACION: dict[str, dict] = {
    "GM": {
        "tramo_label": "Bucket",
        "tramos": ["6-30", "31-60", "61-90", "91-150"],
    },
    "SANTANDER": {
        "cartera_label": "Producto",
        "carteras": ["Hipoteca", "Consumo", "Pyme", "TC"],
        "tramo_label": "Ciclo",
        "tramos_por_cartera": {
            "Hipoteca": ["C1", "C2", "C3"],
            "Consumo": ["C1", "C2"],
            "Pyme": ["C1", "C2", "C3"],
            "TC": ["C0", "Multiciclo"],
        },
    },
    "SC TELEFONÍA": {
        "tramo_label": "Ciclo",
        "tramos": ["C1", "C2", "C3"],
    },
    "BANCO INTERNACIONAL": {
        "carteras": ["VIGENTE", "CASTIGO"],
        "tramo_label": "Tramo",
        "tramos_por_cartera": {"VIGENTE": ["30-90", "90+"], "CASTIGO": ["Castigo"]},
    },
    "SC TERRENO": {
        "tramo_label": "Segmento",
        "tramos": ["C3", "Susc. CV", "C5", "C6", "Pre Castigo", "Castigo"],
        "zonas": ["Norte", "Metropolitana", "Sur"],
    },
    "ITAÚ": {
        "carteras": ["VENCIDA", "CASTIGO"],
        "tramo_label": "Fase / tipo",
        "tramos_por_cartera": {"VENCIDA": ["Fase 4", "Fase 5", "Fase 6", "Fase 7"], "CASTIGO": ["Stock", "MCV"]},
        "productos_por_cartera": {"VENCIDA": ["Consumo", "Hipoteca"]},
    },
    "LA ARAUCANA": {
        "carteras": ["VIGENTE", "CASTIGO", "+365"],
    },
}

TIPO_KPI = {
    "casos": ("int", "pct"),
    "saldo": ("money", "pct"),
    "contactabilidad": ("pct", "pp"),
    "cobertura": ("pct", "pp"),
    "pagos": ("money", "pct"),
    "recuperacion": ("pct", "pp"),
    "gestionados": ("int", "pct"),
    "contacto_directo": ("int", "pct"),
    "contacto_indirecto": ("int", "pct"),
    "sin_contacto": ("int", "pct"),
    "compromisos": ("int", "pct"),
    "cumplidos": ("int", "pct"),
    "incumplidos": ("int", "pct"),
    "pendientes": ("int", "pct"),
    "cumplimiento": ("pct", "pp"),
    "intensidad": ("dec", "pct"),
    "sin_gestion": ("pct", "pp"),
    "no_gestionados": ("int", "pct"),
    "monto_comprometido": ("money", "pct"),
    "cumplimiento_monto": ("pct", "pp"),
}


def _clean(value: object) -> str:
    return str(value or "").strip()


def _safe_div(num: float, den: float) -> float | None:
    return num / den if den else None


def _iso(value) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else value


# ------------------------------------------------------------
# Cortes
# ------------------------------------------------------------
def _cortes(hoy: date) -> list[tuple[str, date]]:
    """Mes actual hasta hoy y los 3 anteriores completos (cortados a su ultimo dia)."""
    out = [(f"{hoy.year:04d}-{hoy.month:02d}", hoy)]
    year, month = hoy.year, hoy.month
    for _ in range(MESES_COMPARACION - 1):
        year, month = (year - 1, 12) if month == 1 else (year, month - 1)
        out.append((f"{year:04d}-{month:02d}", date(year, month, calendar.monthrange(year, month)[1])))
    return out


# ------------------------------------------------------------
# Filtros
# ------------------------------------------------------------
def _dimension_filters(filters: dict, alias: str, include: tuple[str, ...] = DIMENSIONES) -> tuple[str, list]:
    """Filtros de mandante/cartera/tramo/producto/zona (mismas columnas en asignacion y pagos)."""
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


def _ordered(opciones: list[str], disponibles: set[str]) -> list[dict]:
    """Opciones de la configuracion en su orden; las que no tienen datos en el mes actual van deshabilitadas.
    Valores con datos que no estan en la configuracion se agregan al final."""
    out = [{"valor": v, "con_datos": v in disponibles} for v in opciones]
    out += [{"valor": v, "con_datos": True} for v in sorted(disponibles - set(opciones))]
    return out


def _union(listas) -> list[str]:
    out: list[str] = []
    for lista in listas:
        out += [v for v in lista if v not in out]
    return out


def get_filter_values(filters: dict | None = None, hoy: date | None = None) -> dict:
    filters = filters or {}
    periodo_actual = _cortes(hoy or date.today())[0][0]

    def distinct(field: str, include: tuple[str, ...]) -> set[str]:
        dim_sql, dim_params = _dimension_filters(filters, "a", include)
        expr = f"ISNULL(a.producto, '{SIN_PRODUCTO}')" if field == "producto" else f"a.{field}"
        rows = run_query(
            f"SELECT DISTINCT {expr} AS valor FROM dbo.kpi_asignacion a WHERE a.periodo = ?{dim_sql}",
            (periodo_actual, *dim_params),
        )
        return {row["valor"] for row in rows if row.get("valor")}

    mandante = _clean(filters.get("mandante"))
    cartera = _clean(filters.get("cartera"))
    out = {
        "periodo_actual": periodo_actual,
        "mandantes": _ordered(list(SEGMENTACION), distinct("mandante", ())),
        "labels": {"cartera": "Cartera", "tramo": "Tramo", "producto": "Producto", "zona": "Zona"},
        "visibles": {"cartera": False, "tramo": False, "producto": False, "zona": False},
        "carteras": [],
        "tramos": [],
        "productos": [],
        "zonas": [],
    }
    config = SEGMENTACION.get(mandante)
    if not config:
        return out

    out["labels"]["cartera"] = config.get("cartera_label", "Cartera")
    out["labels"]["tramo"] = config.get("tramo_label", "Tramo")

    if config.get("carteras"):
        out["visibles"]["cartera"] = True
        out["carteras"] = _ordered(config["carteras"], distinct("cartera", ("mandante",)))

    if config.get("tramos_por_cartera"):
        por_cartera = config["tramos_por_cartera"]
        tramos = por_cartera.get(cartera, []) if cartera else _union(por_cartera.values())
    else:
        tramos = config.get("tramos", [])
    if tramos:
        out["visibles"]["tramo"] = True
        out["tramos"] = _ordered(tramos, distinct("tramo", ("mandante", "cartera")) & set(tramos))

    productos = config.get("productos_por_cartera", {}).get(cartera, []) if cartera else []
    if productos:
        out["visibles"]["producto"] = True
        out["productos"] = _ordered(productos, distinct("producto", ("mandante", "cartera", "tramo")) & set(productos))

    if config.get("zonas"):
        out["visibles"]["zona"] = True
        out["zonas"] = _ordered(config["zonas"], distinct("zona", ("mandante", "cartera", "tramo", "producto")) & set(config["zonas"]))
    return out


# ------------------------------------------------------------
# Dashboard
# ------------------------------------------------------------
def get_dashboard(filters: dict, hoy: date | None = None) -> dict:
    hoy = hoy or date.today()
    cortes = _cortes(hoy)
    filters = {k: _clean(filters.get(k)) for k in DIMENSIONES}
    mandante = filters["mandante"]

    dim_a_sql, dim_a_params = _dimension_filters(filters, "a")
    dim_p_sql, dim_p_params = _dimension_filters(filters, "p")
    mand_sql, mand_params = _dimension_filters(filters, "p", ("mandante",))
    cortes_values = ", ".join("(?, ?)" for _ in cortes)
    # Fechas como texto ISO: el driver ODBC "SQL Server" no enlaza parametros date.
    cortes_params = [v for periodo, corte in cortes for v in (periodo, corte.isoformat())]
    # Con mandante se desglosa por cartera y tramo; sin mandante, por mandante.
    seg_cols = "mandante, cartera, tramo" if mandante else "mandante"
    seg_cols_a = ", ".join(f"a.{c}" for c in seg_cols.split(", "))
    seg_cols_p = ", ".join(f"p.{c}" for c in seg_cols.split(", "))

    sql = f"""
    SET NOCOUNT ON;

    CREATE TABLE #cortes (periodo CHAR(7) NOT NULL PRIMARY KEY, corte DATE NOT NULL);
    INSERT INTO #cortes (periodo, corte) VALUES {cortes_values};

    -- Asignacion final de cada mes con los filtros.
    SELECT a.periodo, a.mandante, a.cartera, a.tramo, a.rut, CAST(a.saldo_asignado AS float) AS saldo
    INTO #asig
    FROM dbo.kpi_asignacion a
    INNER JOIN #cortes c ON c.periodo = a.periodo
    WHERE 1 = 1{dim_a_sql};
    CREATE INDEX IX_asig ON #asig(periodo, mandante, rut);

    -- Foto de pagos de cada fuente: meses cerrados = la ultima foto disponible del mes (aunque llegue despues
    -- del cierre); mes actual = la ultima <= hoy (si no hay, la primera).
    SELECT d.periodo, d.fuente,
           MAX(CASE WHEN d.fecha_foto <= c.corte OR c.periodo <> ? THEN d.fecha_foto END) AS f_ok,
           MIN(d.fecha_foto) AS f_min
    INTO #fotos
    FROM (
        SELECT DISTINCT p.periodo, p.fuente, p.fecha_foto
        FROM dbo.kpi_pagos_diario p
        WHERE p.periodo IN (SELECT periodo FROM #cortes){mand_sql}
    ) d
    INNER JOIN #cortes c ON c.periodo = d.periodo
    GROUP BY d.periodo, d.fuente;

    -- Pagos al corte (con todos los segmentos del mandante: los compromisos se cruzan por RUT).
    SELECT p.periodo, p.mandante, p.cartera, p.tramo, p.producto, p.zona, p.rut, CAST(p.monto AS float) AS monto,
           p.pago_efectivo, ISNULL(p.fecha_pago, p.fecha_foto) AS f_pago, p.fecha_foto,
           CASE WHEN f.f_ok IS NULL AND p.fecha_pago IS NULL THEN 1 ELSE 0 END AS aprox
    INTO #pagos
    FROM dbo.kpi_pagos_diario p
    INNER JOIN #fotos f ON f.periodo = p.periodo AND f.fuente = p.fuente AND p.fecha_foto = ISNULL(f.f_ok, f.f_min)
    INNER JOIN #cortes c ON c.periodo = p.periodo
    WHERE (p.fecha_pago IS NULL OR p.fecha_pago <= c.corte){mand_sql};
    CREATE INDEX IX_pagos ON #pagos(periodo, mandante, rut);

    -- 1) Asignacion por mes.
    SELECT c.periodo, COUNT(DISTINCT a.mandante + '|' + CAST(a.rut AS varchar(20))) AS casos,
           COUNT(a.rut) AS operaciones, SUM(a.saldo) AS saldo
    FROM #cortes c
    LEFT JOIN #asig a ON a.periodo = c.periodo
    GROUP BY c.periodo;

    -- 2) Contacto al corte por mes (mejor contacto por mandante + RUT asignado).
    ;WITH casos AS (
        SELECT periodo, COUNT(*) AS n FROM (SELECT DISTINCT periodo, mandante, rut FROM #asig) x GROUP BY periodo
    ),
    gest AS (
        SELECT s.periodo, s.mandante, s.rut,
               MIN(g.fecha_primera_gestion) AS f_gest,
               MIN(g.fecha_primer_directo) AS f_dir,
               MIN(g.fecha_primer_indirecto) AS f_ind,
               SUM(CAST(ISNULL(g.n_llamadas, 0) AS bigint)) AS n_llamadas
        FROM (SELECT DISTINCT periodo, mandante, cartera, rut FROM #asig) s
        INNER JOIN dbo.kpi_crm_cartera k
            ON k.mandante = s.mandante AND (k.cartera IS NULL OR k.cartera = s.cartera)
        INNER JOIN dbo.kpi_gestiones_rut g
            ON g.periodo = s.periodo AND g.crm_cartera = k.crm_cartera AND g.rut = s.rut
        GROUP BY s.periodo, s.mandante, s.rut
    )
    SELECT c.periodo, ISNULL(MAX(cs.n), 0) AS asignados,
           SUM(CASE WHEN g.f_gest <= c.corte THEN 1 ELSE 0 END) AS gestionados,
           SUM(CASE WHEN g.f_dir <= c.corte THEN 1 ELSE 0 END) AS directo,
           SUM(CASE WHEN (g.f_dir IS NULL OR g.f_dir > c.corte) AND g.f_ind <= c.corte THEN 1 ELSE 0 END) AS indirecto,
           SUM(CASE WHEN g.f_gest <= c.corte AND (g.f_dir IS NULL OR g.f_dir > c.corte)
                         AND (g.f_ind IS NULL OR g.f_ind > c.corte) THEN 1 ELSE 0 END) AS sin_contacto,
           -- Llamados del mes (sin IVR, terreno ni mensajes; ver dbo.kpi_accion_canal). Mes actual: hasta la ultima carga del CRM.
           SUM(CASE WHEN g.f_gest <= c.corte THEN g.n_llamadas ELSE 0 END) AS llamados
    FROM #cortes c
    LEFT JOIN casos cs ON cs.periodo = c.periodo
    LEFT JOIN gest g ON g.periodo = c.periodo
    GROUP BY c.periodo;

    -- 3) Pagos al corte por mes (solo los de la asignacion cuentan como pagos del KPI).
    SELECT c.periodo,
           SUM(CASE WHEN p.tramo <> N'{SIN_ASIGNACION}' THEN p.monto ELSE 0 END) AS pagos,
           SUM(CASE WHEN p.tramo = N'{SIN_ASIGNACION}' THEN p.monto ELSE 0 END) AS pagos_fuera,
           MAX(p.aprox) AS aprox,
           MAX(p.fecha_foto) AS foto
    FROM #cortes c
    LEFT JOIN #pagos p ON p.periodo = c.periodo{dim_p_sql}
    GROUP BY c.periodo;

    -- 4) Compromisos generados hasta el corte, por mes y estado, con su monto. en_mes = vence hasta fin de mes
    --    (los pendientes que vencen en el mes forman el tubo).
    --    El monto es el que trae el CRM (kpi_compromisos.monto_compromiso), sin ajustes.
    ;WITH comp AS (
        SELECT DISTINCT c.id, c.periodo, k.mandante, k.cartera AS crm_cartera_kpi, c.rut,
               CAST(c.fecha_gestion AS date) AS f_gest, c.fecha_compromiso, ct.corte,
               CAST(ISNULL(c.monto_compromiso, 0) AS float) AS monto
        FROM dbo.kpi_compromisos c
        INNER JOIN #cortes ct ON ct.periodo = c.periodo
        INNER JOIN dbo.kpi_crm_cartera k ON k.crm_cartera = c.crm_cartera
        INNER JOIN #asig s
            ON s.periodo = c.periodo AND s.mandante = k.mandante AND s.rut = c.rut
           AND (k.cartera IS NULL OR k.cartera = s.cartera)
        WHERE CAST(c.fecha_gestion AS date) <= ct.corte
    )
    SELECT x.periodo, x.estado, x.en_mes, COUNT(*) AS n, SUM(x.monto) AS monto
    FROM (
        SELECT c.periodo, c.monto,
               CASE WHEN c.fecha_compromiso <= EOMONTH(c.corte) THEN 1 ELSE 0 END AS en_mes,
               CASE
                   WHEN EXISTS (
                       SELECT 1 FROM #pagos p
                       WHERE p.periodo = c.periodo AND p.mandante = c.mandante AND p.rut = c.rut
                         AND p.pago_efectivo = 1
                         AND (c.crm_cartera_kpi IS NULL OR p.cartera = c.crm_cartera_kpi)
                         AND p.f_pago >= c.f_gest
                   ) THEN 'CUMPLIDO'
                   WHEN c.fecha_compromiso < c.corte THEN 'INCUMPLIDO'
                   ELSE 'PENDIENTE'
               END AS estado
        FROM comp c
    ) x
    GROUP BY x.periodo, x.estado, x.en_mes;

    -- 5) Segmentos por mes.
    SELECT a.periodo, {seg_cols_a}, COUNT(DISTINCT a.mandante + '|' + CAST(a.rut AS varchar(20))) AS casos, SUM(a.saldo) AS saldo
    FROM #asig a
    GROUP BY a.periodo, {seg_cols_a};

    SELECT p.periodo, {seg_cols_p}, SUM(p.monto) AS pagos
    FROM #pagos p
    WHERE p.tramo <> N'{SIN_ASIGNACION}'{dim_p_sql}
    GROUP BY p.periodo, {seg_cols_p};

    -- 6) Mandantes con pagos aproximados por mes (sin foto diaria anterior al corte).
    SELECT DISTINCT p.periodo, p.mandante
    FROM #pagos p
    WHERE p.aprox = 1{dim_p_sql};
    """
    params = [*cortes_params, *dim_a_params, cortes[0][0], *mand_params, *mand_params, *dim_p_params, *dim_p_params, *dim_p_params]
    asig, contacto, pagos, compromisos, seg_asig, seg_pagos, aprox = run_query_sets(sql, tuple(params))
    response = _build_response(hoy, cortes, filters, asig, contacto, pagos, compromisos, seg_asig, seg_pagos)
    for mes in response["meses"]:
        mes["aproximado_mandantes"] = sorted({r["mandante"] for r in aprox if r["periodo"] == mes["periodo"]})
    return response


def _kpi(nombre: str, valores: list) -> dict:
    tipo, delta_tipo = TIPO_KPI[nombre]
    actual, anterior = valores[0], valores[1]
    delta = None
    if actual is not None and anterior is not None:
        delta = actual - anterior if delta_tipo == "pp" else _safe_div(actual - anterior, anterior)
    return {"tipo": tipo, "valores": valores, "delta": delta, "delta_tipo": delta_tipo}


def _segment_order(mandante: str):
    config = SEGMENTACION.get(mandante, {})
    carteras = config.get("carteras", [])
    tramos = _union([config.get("tramos", []), *config.get("tramos_por_cartera", {}).values()])
    mandantes = list(SEGMENTACION)

    def key(item: dict):
        def idx(lista, valor):
            return lista.index(valor) if valor in lista else len(lista)
        return (idx(mandantes, item["mandante"]), idx(carteras, item.get("cartera")), idx(tramos, item.get("tramo")),
                item.get("cartera") or "", item.get("tramo") or "")

    return key


def _build_response(hoy, cortes, filters, asig, contacto, pagos, compromisos, seg_asig, seg_pagos) -> dict:
    periodos = [periodo for periodo, _ in cortes]
    by = lambda rows: {row["periodo"]: row for row in rows}  # noqa: E731
    asig_p, cont_p, pagos_p = by(asig), by(contacto), by(pagos)

    comp_p: dict[str, dict] = {p: {"CUMPLIDO": 0, "INCUMPLIDO": 0, "PENDIENTE": 0} for p in periodos}
    monto_p: dict[str, dict] = {p: {"CUMPLIDO": 0.0, "INCUMPLIDO": 0.0, "PENDIENTE": 0.0} for p in periodos}
    tubo_p: dict[str, dict] = {p: {"n": 0, "monto": 0.0} for p in periodos}
    for row in compromisos:
        periodo, estado = row["periodo"], row["estado"]
        n, monto_c = int(row.get("n") or 0), float(row.get("monto") or 0)
        comp_p[periodo][estado] += n
        monto_p[periodo][estado] += monto_c
        # Tubo: pendientes (sin pago, aun no vencen) que vencen hasta fin de mes.
        if estado == "PENDIENTE" and row.get("en_mes"):
            tubo_p[periodo]["n"] += n
            tubo_p[periodo]["monto"] += monto_c

    series: dict[str, list] = {name: [] for name in TIPO_KPI}
    meses = []
    tipos_contacto = []
    for periodo, corte in cortes:
        a, c, p, cp, mp = asig_p.get(periodo, {}), cont_p.get(periodo, {}), pagos_p.get(periodo, {}), comp_p[periodo], monto_p[periodo]
        casos = int(a.get("casos") or 0)
        saldo = float(a.get("saldo") or 0)
        asignados = int(c.get("asignados") or 0)
        gestionados = int(c.get("gestionados") or 0)
        directo = int(c.get("directo") or 0)
        indirecto = int(c.get("indirecto") or 0)
        sin_contacto = int(c.get("sin_contacto") or 0)
        monto = float(p.get("pagos") or 0)
        total_comp = sum(cp.values())
        con_datos = casos > 0

        valores = {
            "casos": casos,
            "saldo": saldo,
            "contactabilidad": _safe_div(directo, gestionados),
            "cobertura": _safe_div(gestionados, asignados),
            "pagos": monto,
            "recuperacion": _safe_div(monto, saldo),
            "gestionados": gestionados,
            "contacto_directo": directo,
            "contacto_indirecto": indirecto,
            "sin_contacto": sin_contacto,
            "compromisos": total_comp,
            "cumplidos": cp["CUMPLIDO"],
            "incumplidos": cp["INCUMPLIDO"],
            "pendientes": cp["PENDIENTE"],
            "cumplimiento": _safe_div(cp["CUMPLIDO"], cp["CUMPLIDO"] + cp["INCUMPLIDO"]),
            # Intensidad = llamados / casos asignados.
            "intensidad": _safe_div(int(c.get("llamados") or 0), asignados),
            # Clientes asignados sin ninguna gestion al corte.
            "sin_gestion": _safe_div(asignados - gestionados, asignados),
            "no_gestionados": max(asignados - gestionados, 0),
            "monto_comprometido": sum(mp.values()),
            "cumplimiento_monto": _safe_div(mp["CUMPLIDO"], mp["CUMPLIDO"] + mp["INCUMPLIDO"]),
        }
        for name, value in valores.items():
            # Mes sin asignacion cargada: sin dato (no cero), para no mostrar caidas falsas.
            series[name].append(value if con_datos else None)

        meses.append({
            "periodo": periodo,
            "corte": corte.isoformat(),
            "con_datos": con_datos,
            "aproximado": bool(p.get("aprox")),
            "foto_pagos": _iso(p.get("foto")),
            "pagos_fuera_asignacion": float(p.get("pagos_fuera") or 0),
        })
        tipos_contacto.append({
            "periodo": periodo,
            "gestionados": gestionados,
            "directo": directo,
            "indirecto": indirecto,
            "sin_contacto": sin_contacto,
        })

    # Segmentos: una fila por segmento con los 4 meses.
    segmentos: dict[tuple, dict] = {}
    keys = ("mandante", "cartera", "tramo") if filters["mandante"] else ("mandante",)
    for row in seg_asig:
        key = tuple(row.get(k) for k in keys)
        item = segmentos.setdefault(key, {**dict(zip(keys, key)), "meses": {}})
        item["meses"][row["periodo"]] = {"casos": int(row.get("casos") or 0), "saldo": float(row.get("saldo") or 0), "pagos": 0.0}
    for row in seg_pagos:
        key = tuple(row.get(k) for k in keys)
        if key not in segmentos:
            continue
        mes = segmentos[key]["meses"].setdefault(row["periodo"], {"casos": 0, "saldo": 0.0, "pagos": 0.0})
        mes["pagos"] = float(row.get("pagos") or 0)
    seg_rows = []
    for item in segmentos.values():
        for mes in item["meses"].values():
            mes["recuperacion"] = _safe_div(mes["pagos"], mes["saldo"])
        seg_rows.append(item)
    seg_rows.sort(key=_segment_order(filters["mandante"]))

    # Proyeccion de cierre: pagos a hoy + tubo del mes x cumplimiento en monto de los 3 meses cerrados.
    cerrados = [p for p, m in zip(periodos[1:], meses[1:]) if m["con_datos"]]
    cumplido_3m = sum(monto_p[p]["CUMPLIDO"] for p in cerrados)
    vencido_3m = sum(monto_p[p]["CUMPLIDO"] + monto_p[p]["INCUMPLIDO"] for p in cerrados)
    tasa = _safe_div(cumplido_3m, vencido_3m)
    tubo = tubo_p[periodos[0]]
    pagos_hoy = series["pagos"][0]
    aporte = tubo["monto"] * tasa if tasa is not None else None
    proyeccion = (pagos_hoy or 0) + aporte if pagos_hoy is not None and aporte is not None else None
    cierre_anterior = series["pagos"][1]
    saldo_actual = series["saldo"][0]

    return {
        "hoy": hoy.isoformat(),
        "filtros": filters,
        "meses": meses,
        "kpis": {name: _kpi(name, values) for name, values in series.items()},
        "proyeccion": {
            "pagos_hoy": pagos_hoy,
            "tubo_n": tubo["n"],
            "tubo_monto": tubo["monto"],
            "tasa": tasa,
            "tasa_meses": cerrados,
            "aporte_tubo": aporte,
            "proyeccion": proyeccion,
            "recuperacion_proyectada": _safe_div(proyeccion, saldo_actual) if proyeccion is not None else None,
            "cierre_anterior": cierre_anterior,
            "delta_vs_cierre_anterior": _safe_div(proyeccion - cierre_anterior, cierre_anterior)
            if proyeccion is not None and cierre_anterior else None,
            "fin_mes": _cortes(hoy)[0][1].replace(day=calendar.monthrange(hoy.year, hoy.month)[1]).isoformat(),
        },
        "tipos_contacto": tipos_contacto,
        "segmentos": seg_rows,
        "vacio": not any(m["con_datos"] for m in meses),
    }
