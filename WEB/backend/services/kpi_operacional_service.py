"""KPI Operacional: lee las tablas consolidadas que arma dbo.sp_kpi_operacional_cargar (SQL/007_kpi_operacional.sql).

Sin filtro de periodo: compara el mes en curso (hasta hoy) con los 3 meses anteriores cortados al mismo dia habil
restante antes del cierre (corte equivalente). Gestiones, pagos y compromisos se calculan a ese corte y tambien al
cierre de cada mes (la ultima informacion disponible); los deltas usan el corte equivalente y la proyeccion, el cierre.
Dias habiles = lun-vie sin feriados de feriados_chile (los años fuera del catalogo cuentan solo lun-vie).

Universo:
  - Casos = RUT unico por mandante (dentro de un mandante, un RUT en dos carteras cuenta una vez).
  - Asignacion = la final de cada mes (no se corta por dia).
  - Gestiones: contacto al corte segun la fecha del primer contacto de cada tipo.
  - Pagos: meses cerrados = la ultima foto disponible del mes; mes actual = la ultima foto hasta hoy
    (y fecha de pago <= corte cuando la fuente la trae).
    Solo cuentan los pagos de la asignacion; los de RUT fuera de ella quedan con tramo 'Sin asignación'
    (salvo Itau Castigo: un RUT con recupero no asignado se arrastra de la asignacion del mes anterior y, si
    tampoco estaba, cuenta en Stock o MCV segun su COBRADOR_DES).
  - Compromisos generados hasta el corte, de RUT asignados.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta

from cache import cached, cached_view
from database import run_query, run_query_sets
from feriados_chile import es_habil


SIN_PRODUCTO = "Sin producto"
FILTROS_TTL = 600  # segundos; la asignacion solo cambia cuando corre sp_kpi_operacional_cargar
SIN_ASIGNACION = "Sin asignación"
MESES_COMPARACION = 4  # mes actual + 3 anteriores
DIMENSIONES = ("mandante", "cartera", "tramo", "producto", "zona", "canal")
# Cada mes se calcula al cierre y al corte equivalente; sufijo de las columnas SQL de cada uno.
CORTES_TIPO = {"cierre": "", "eq": "_eq"}

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
        # Todos los ciclos que traen los datos (C0, C1, ...) del producto elegido.
        "tramos_desde_datos": True,
    },
    "SC TELEFONÍA": {
        "tramo_label": "Segmento",
        # Solo C1, C2 y C3 (el SP de carga deja fuera los demas tramos).
        "tramos": ["C1", "C2", "C3"],
    },
    "SC PILOTO": {
        "tramo_label": "Segmento",
        # Bench de mora tardia telefonia, con los segmentos de mora tardia de SC Terreno.
        "tramos": ["Susc. CV", "C5", "C6", "Pre Castigo", "Castigo"],
    },
    "BANCO INTERNACIONAL": {
        # Solo filtro de tramo: 30-90 y 90+ son la cartera Vigente; Castigo, la cartera Castigo.
        "tramo_label": "Tramo",
        "tramos": ["30-90", "90+", "Castigo"],
    },
    "SC TERRENO": {
        "tramo_label": "Segmento",
        # Entra toda la asignacion: C1 y C2 (y cualquier tramo que la regla no clasifica) quedan con su tramo.
        "tramos": ["C1", "C2", "C3", "Susc. CV", "C5", "C6", "Pre Castigo", "Castigo"],
        "zonas": ["Norte", "Metropolitana", "Sur"],
    },
    "ITAÚ": {
        "carteras": ["VIGENTE", "VENCIDA", "CASTIGO"],
        "tramo_label": "Fase / tipo",
        "tramos_por_cartera": {
            "VIGENTE": ["Fase 1", "Fase 2", "Fase 3"],
            "VENCIDA": ["Fase 4", "Fase 5", "Fase 6", "Fase 7"],
            "CASTIGO": ["Stock", "MCV"],
        },
        "productos_por_cartera": {"VIGENTE": ["Consumo", "Hipoteca"], "VENCIDA": ["Consumo", "Hipoteca"]},
        # Canal de la contencion (los valores salen de los datos); solo Vigente y Vencida lo traen.
        "canal_carteras": ["VIGENTE", "VENCIDA"],
    },
    "LA ARAUCANA": {
        "carteras": ["VIGENTE", "CASTIGO", "+365"],
    },
    "FORUM": {
        # Sin saldo asignado ni pagos: solo casos y gestiones (CRM 574).
        "carteras": ["VIGENTE", "CASTIGO"],
    },
}

TIPO_KPI = {
    "casos": ("int", "pct"),
    "operaciones": ("int", "pct"),
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
    "pct_cumplidos": ("pct", "pp"),
    "pct_incumplidos": ("pct", "pp"),
    "intensidad": ("dec", "pct"),
    "sin_gestion": ("pct", "pp"),
    "no_gestionados": ("int", "pct"),
    "monto_comprometido": ("money", "pct"),
    "contactables": ("int", "pct"),
    "alcance_contacto": ("pct", "pp"),
    "contactables_logrados": ("int", "pct"),
    "contactables_pendientes": ("int", "pct"),
    "avance_alcance": ("pct", "pp"),
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
def _fin_de_mes(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def _habiles_restantes(dia: date) -> int:
    """Dias habiles despues de `dia` hasta el fin de su mes."""
    fin = _fin_de_mes(dia.year, dia.month)
    return sum(es_habil(dia + timedelta(days=i)) for i in range(1, (fin - dia).days + 1))


def _corte_equivalente(year: int, month: int, n: int) -> date:
    """Ultima fecha del mes a la que aun le quedan `n` dias habiles para el cierre."""
    fin = _fin_de_mes(year, month)
    if n <= 0:
        return fin
    habiles = [d for d in (date(year, month, i) for i in range(1, fin.day + 1)) if es_habil(d)]
    if n > len(habiles):
        return date(year, month, 1)
    return max(habiles[-n] - timedelta(days=1), date(year, month, 1))


def _cortes(hoy: date) -> list[tuple[str, date, date]]:
    """(periodo, corte al cierre, corte equivalente): mes actual hasta hoy y los 3 anteriores al cierre y al
    mismo dia habil restante que hoy."""
    out = [(f"{hoy.year:04d}-{hoy.month:02d}", hoy, hoy)]
    restantes = _habiles_restantes(hoy)
    year, month = hoy.year, hoy.month
    for _ in range(MESES_COMPARACION - 1):
        year, month = (year - 1, 12) if month == 1 else (year, month - 1)
        out.append((f"{year:04d}-{month:02d}", _fin_de_mes(year, month), _corte_equivalente(year, month, restantes)))
    return out


# ------------------------------------------------------------
# Filtros
# ------------------------------------------------------------
def _valores(filters: dict, field: str) -> list[str]:
    """Valores elegidos de un filtro (admite uno o varios), sin vacios ni repetidos."""
    raw = filters.get(field)
    if raw is None or isinstance(raw, str):
        raw = [raw]
    out: list[str] = []
    for item in raw:
        value = _clean(item)
        if value and value not in out:
            out.append(value)
    return out


def _unico(filters: dict, field: str) -> str:
    """El valor del filtro cuando se eligio exactamente uno; con ninguno o varios, ''."""
    valores = _valores(filters, field)
    return valores[0] if len(valores) == 1 else ""


def _dimension_filters(filters: dict, alias: str, include: tuple[str, ...] = DIMENSIONES) -> tuple[str, list]:
    """Filtros de mandante/cartera/tramo/producto/zona/canal (mismas columnas en asignacion y pagos)."""
    clauses: list[str] = []
    params: list = []
    for field in include:
        valores = _valores(filters, field)
        if not valores:
            continue
        sin_producto = field == "producto" and SIN_PRODUCTO in valores
        if sin_producto:
            valores = [v for v in valores if v != SIN_PRODUCTO]
        partes = []
        if valores:
            partes.append(f"{alias}.{field} IN ({', '.join('?' for _ in valores)})")
            params.extend(valores)
        if sin_producto:
            partes.append(f"{alias}.producto IS NULL")
        clauses.append(partes[0] if len(partes) == 1 else f"({' OR '.join(partes)})")
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


def _combinaciones(periodo: str) -> list[dict]:
    """Combinaciones distintas de dimensiones del mes (pocas filas), en la cache compartida por FILTROS_TTL.
    datos_version la limpia apenas cambian las tablas, asi una carga nueva aparece al instante."""
    return cached(
        ("kpi_operacional_combinaciones", periodo),
        lambda: run_query(
            f"""SELECT DISTINCT mandante, cartera, tramo, ISNULL(producto, N'{SIN_PRODUCTO}') AS producto, zona, canal
            FROM dbo.kpi_asignacion WHERE periodo = ?""",
            (periodo,),
        ),
        ttl=FILTROS_TTL,
    )


def _coincide(row: dict, filters: dict, include: tuple[str, ...] = DIMENSIONES) -> bool:
    """Mismo criterio que _dimension_filters (producto 'Sin producto' = NULL, ya normalizado en la consulta)."""
    return all(row.get(f) in _valores(filters, f) for f in include if _valores(filters, f))


def _hay_asignacion(periodo: str, filters: dict) -> bool:
    return any(_coincide(row, filters) for row in _combinaciones(periodo))


def _fin_mes_anterior(hoy: date) -> date:
    return hoy.replace(day=1) - timedelta(days=1)


def get_filter_values(filters: dict | None = None, hoy: date | None = None) -> dict:
    filters = filters or {}
    hoy = hoy or date.today()
    periodo_actual = _cortes(hoy)[0][0]
    # Un segmento sin asignacion este mes sigue disponible si la tuvo el mes anterior (el dashboard muestra ese mes).
    combinaciones = _combinaciones(periodo_actual) + _combinaciones(_cortes(_fin_mes_anterior(hoy))[0][0])

    def distinct(field: str, include: tuple[str, ...]) -> set[str]:
        return {row[field] for row in combinaciones if row.get(field) and _coincide(row, filters, include)}

    # Los filtros especificos solo aplican con un unico mandante elegido.
    mandante = _unico(filters, "mandante")
    carteras = _valores(filters, "cartera")
    out = {
        "periodo_actual": periodo_actual,
        "mandantes": _ordered(list(SEGMENTACION), distinct("mandante", ())),
        "labels": {"cartera": "Cartera", "tramo": "Tramo", "producto": "Producto", "zona": "Zona", "canal": "Canal"},
        "visibles": {"cartera": False, "tramo": False, "producto": False, "zona": False, "canal": False},
        "carteras": [],
        "tramos": [],
        "productos": [],
        "zonas": [],
        "canales": [],
    }
    config = SEGMENTACION.get(mandante)
    if not config:
        return out

    out["labels"]["cartera"] = config.get("cartera_label", "Cartera")
    out["labels"]["tramo"] = config.get("tramo_label", "Tramo")

    if config.get("carteras"):
        out["visibles"]["cartera"] = True
        out["carteras"] = _ordered(config["carteras"], distinct("cartera", ("mandante",)))

    if config.get("tramos_desde_datos"):
        # (largo, texto): C2 antes que C10.
        tramos = sorted(distinct("tramo", ("mandante", "cartera")), key=lambda v: (len(v), v))
    elif config.get("tramos_por_cartera"):
        por_cartera = config["tramos_por_cartera"]
        tramos = _union(por_cartera.get(c, []) for c in carteras) if carteras else _union(por_cartera.values())
    else:
        tramos = config.get("tramos", [])
    if tramos:
        out["visibles"]["tramo"] = True
        out["tramos"] = _ordered(tramos, distinct("tramo", ("mandante", "cartera")) & set(tramos))

    productos = _union(config.get("productos_por_cartera", {}).get(c, []) for c in carteras)
    if productos:
        out["visibles"]["producto"] = True
        out["productos"] = _ordered(productos, distinct("producto", ("mandante", "cartera", "tramo")) & set(productos))

    if config.get("zonas"):
        out["visibles"]["zona"] = True
        out["zonas"] = _ordered(config["zonas"], distinct("zona", ("mandante", "cartera", "tramo", "producto")) & set(config["zonas"]))

    # Canal: sin cartera elegida o con alguna que lo trae; elegir un canal deja fuera las carteras sin canal.
    canal_carteras = config.get("canal_carteras", [])
    if canal_carteras and (not carteras or set(carteras) & set(canal_carteras)):
        out["visibles"]["canal"] = True
        out["canales"] = _ordered([], distinct("canal", ("mandante", "cartera", "tramo", "producto")))
    return out


# ------------------------------------------------------------
# Dashboard
# ------------------------------------------------------------
# En cache por filtros y dia (hoy va en la clave); datos_version la limpia cuando corre la carga del KPI.
@cached_view
def get_dashboard(filters: dict, hoy: date | None = None) -> dict:
    hoy = hoy or date.today()
    filters = {k: _valores(filters, k) for k in DIMENSIONES}
    mandante = _unico(filters, "mandante")
    periodo_en_curso = _cortes(hoy)[0][0]
    # Sin asignacion del mes en curso (p. ej. primeros dias del mes): se muestra el mes anterior, ya cerrado.
    mes_anterior = not _hay_asignacion(periodo_en_curso, filters)
    referencia = _fin_mes_anterior(hoy) if mes_anterior else hoy
    cortes = _cortes(referencia)

    dim_a_sql, dim_a_params = _dimension_filters(filters, "a")
    dim_p_sql, dim_p_params = _dimension_filters(filters, "p")
    mand_sql, mand_params = _dimension_filters(filters, "p", ("mandante",))
    cortes_values = ", ".join("(?, ?, ?)" for _ in cortes)
    # Fechas como texto ISO: el driver ODBC "SQL Server" no enlaza parametros date.
    cortes_params = [v for periodo, corte, corte_eq in cortes for v in (periodo, corte.isoformat(), corte_eq.isoformat())]
    # Con un mandante se desglosa por cartera y tramo; con ninguno o varios, por mandante.
    seg_cols = "mandante, cartera, tramo" if mandante else "mandante"
    seg_cols_a = ", ".join(f"a.{c}" for c in seg_cols.split(", "))
    seg_cols_p = ", ".join(f"p.{c}" for c in seg_cols.split(", "))

    def pagos_al_corte(tabla: str, foto: str, corte: str) -> str:
        """Pagos al corte (con todos los segmentos del mandante: los compromisos se cruzan por RUT)."""
        return f"""
    SELECT p.periodo, p.mandante, p.cartera, p.tramo, p.producto, p.zona, p.canal, p.rut, CAST(p.monto AS float) AS monto,
           p.pago_efectivo, ISNULL(p.fecha_pago, p.fecha_foto) AS f_pago, p.fecha_foto,
           CASE WHEN f.{foto} IS NULL AND p.fecha_pago IS NULL THEN 1 ELSE 0 END AS aprox
    INTO {tabla}
    FROM dbo.kpi_pagos_diario p
    INNER JOIN #fotos f ON f.periodo = p.periodo AND f.fuente = p.fuente AND p.fecha_foto = ISNULL(f.{foto}, f.f_min)
    INNER JOIN #cortes c ON c.periodo = p.periodo
    WHERE (p.fecha_pago IS NULL OR p.fecha_pago <= c.{corte}){mand_sql};
    CREATE INDEX IX_{tabla[1:]} ON {tabla}(periodo, mandante, rut);"""

    def pagos_por_mes(tabla: str) -> str:
        """Pagos por mes (solo los de la asignacion cuentan como pagos del KPI)."""
        return f"""(
        SELECT p.periodo,
               SUM(CASE WHEN p.tramo <> N'{SIN_ASIGNACION}' THEN p.monto ELSE 0 END) AS pagos,
               SUM(CASE WHEN p.tramo = N'{SIN_ASIGNACION}' THEN p.monto ELSE 0 END) AS pagos_fuera,
               MAX(p.aprox) AS aprox,
               MAX(p.fecha_foto) AS foto
        FROM {tabla} p
        WHERE 1 = 1{dim_p_sql}
        GROUP BY p.periodo
    )"""

    def cumplido(tabla: str) -> str:
        """Compromiso con un pago efectivo del mismo mandante + RUT desde la fecha de gestion, en una cartera que
        atiende su cartera CRM (cartera NULL en kpi_crm_cartera = cualquiera; 523 = Itau Vencida o Vigente)."""
        return f"""EXISTS (
                       SELECT 1 FROM {tabla} p
                       WHERE p.periodo = c.periodo AND p.mandante = c.mandante AND p.rut = c.rut
                         AND p.pago_efectivo = 1
                         AND p.f_pago >= c.f_gest
                         AND EXISTS (
                             SELECT 1 FROM dbo.kpi_crm_cartera k
                             WHERE k.crm_cartera = c.crm_cartera AND k.mandante = c.mandante
                               AND (k.cartera IS NULL OR k.cartera = p.cartera)
                         )
                   )"""

    sql = f"""
    SET NOCOUNT ON;

    CREATE TABLE #cortes (periodo CHAR(7) NOT NULL PRIMARY KEY, corte DATE NOT NULL, corte_eq DATE NOT NULL);
    INSERT INTO #cortes (periodo, corte, corte_eq) VALUES {cortes_values};

    -- Asignacion final de cada mes con los filtros.
    SELECT a.periodo, a.mandante, a.cartera, a.tramo, a.rut, CAST(a.saldo_asignado AS float) AS saldo
    INTO #asig
    FROM dbo.kpi_asignacion a
    INNER JOIN #cortes c ON c.periodo = a.periodo
    WHERE 1 = 1{dim_a_sql};
    CREATE CLUSTERED INDEX IX_asig ON #asig(periodo, mandante, rut);

    -- RUT asignados por mes y cartera (base de casos, gestiones, alcance y compromisos).
    SELECT DISTINCT periodo, mandante, cartera, rut
    INTO #asig_rut
    FROM #asig;
    CREATE CLUSTERED INDEX IX_asig_rut ON #asig_rut(periodo, mandante, rut);

    -- Mejor contacto por mandante + RUT asignado (lo usan el contacto y el alcance). Cada cartera CRM del RUT
    -- entra una vez aunque el RUT este en dos carteras que la comparten (Itau Vencida y Vigente = 523).
    SELECT s.periodo, s.mandante, s.rut,
           MIN(g.fecha_primera_gestion) AS f_gest,
           MIN(g.fecha_primer_directo) AS f_dir,
           MIN(g.fecha_primer_indirecto) AS f_ind,
           SUM(CAST(ISNULL(g.n_gestiones, 0) AS bigint)) AS n_gestiones
    INTO #gest
    FROM (
        SELECT DISTINCT s.periodo, s.mandante, s.rut, k.crm_cartera
        FROM #asig_rut s
        INNER JOIN dbo.kpi_crm_cartera k
            ON k.mandante = s.mandante AND (k.cartera IS NULL OR k.cartera = s.cartera)
    ) s
    INNER JOIN dbo.kpi_gestiones_rut g
        ON g.periodo = s.periodo AND g.crm_cartera = s.crm_cartera AND g.rut = s.rut
    GROUP BY s.periodo, s.mandante, s.rut;
    CREATE CLUSTERED INDEX IX_gest ON #gest(periodo, mandante, rut);

    -- Alcance de contacto: RUT asignado con contacto titular en alguno de los 3 meses anteriores.
    -- Los meses se enumeran para buscar por la clave de kpi_gestiones_rut (periodo, crm_cartera, rut).
    SELECT DISTINCT s.periodo, s.mandante, s.rut
    INTO #hist
    FROM #asig_rut s
    CROSS APPLY (VALUES (1), (2), (3)) m(n)
    INNER JOIN dbo.kpi_crm_cartera k
        ON k.mandante = s.mandante AND (k.cartera IS NULL OR k.cartera = s.cartera)
    INNER JOIN dbo.kpi_gestiones_rut g
        ON g.periodo = CONVERT(char(7), DATEADD(month, -m.n, CAST(s.periodo + '-01' AS date)), 120)
       AND g.crm_cartera = k.crm_cartera AND g.rut = s.rut AND g.fecha_primer_directo IS NOT NULL;

    -- Foto de pagos de cada fuente: meses cerrados = la ultima foto disponible del mes (aunque llegue despues
    -- del cierre); mes actual = la ultima <= hoy (si no hay, la primera).
    -- f_eq: la ultima foto <= corte equivalente (si el corte equivalente es el cierre, con la regla del cierre).
    SELECT d.periodo, d.fuente,
           MAX(CASE WHEN d.fecha_foto <= c.corte OR c.periodo <> ? THEN d.fecha_foto END) AS f_ok,
           MAX(CASE WHEN d.fecha_foto <= c.corte_eq OR (c.corte_eq = c.corte AND c.periodo <> ?)
                    THEN d.fecha_foto END) AS f_eq,
           MIN(d.fecha_foto) AS f_min
    INTO #fotos
    FROM (
        SELECT DISTINCT p.periodo, p.fuente, p.fecha_foto
        FROM dbo.kpi_pagos_diario p
        WHERE p.periodo IN (SELECT periodo FROM #cortes){mand_sql}
    ) d
    INNER JOIN #cortes c ON c.periodo = d.periodo
    GROUP BY d.periodo, d.fuente;

    -- Pagos al cierre (#pagos) y al corte equivalente (#pagos_eq).
    {pagos_al_corte("#pagos", "f_ok", "corte")}
    {pagos_al_corte("#pagos_eq", "f_eq", "corte_eq")}

    -- 1) Asignacion por mes.
    SELECT c.periodo, ISNULL(cs.casos, 0) AS casos, ISNULL(op.operaciones, 0) AS operaciones, op.saldo
    FROM #cortes c
    LEFT JOIN (
        SELECT periodo, COUNT(*) AS casos FROM (SELECT DISTINCT periodo, mandante, rut FROM #asig_rut) x GROUP BY periodo
    ) cs ON cs.periodo = c.periodo
    LEFT JOIN (
        SELECT periodo, COUNT(rut) AS operaciones, SUM(saldo) AS saldo FROM #asig GROUP BY periodo
    ) op ON op.periodo = c.periodo;

    -- 2) Contacto al cierre y al corte equivalente (_eq) por mes (mejor contacto por mandante + RUT asignado).
    ;WITH casos AS (
        SELECT periodo, COUNT(*) AS n FROM (SELECT DISTINCT periodo, mandante, rut FROM #asig_rut) x GROUP BY periodo
    ),
    -- Sin corte equivalente: meses cerrados completos, mes actual hasta hoy.
    alcance AS (
        SELECT h.periodo, COUNT(*) AS contactables,
               SUM(CASE WHEN g.f_dir <= c.corte THEN 1 ELSE 0 END) AS contactables_ok
        FROM #hist h
        INNER JOIN #cortes c ON c.periodo = h.periodo
        LEFT JOIN #gest g ON g.periodo = h.periodo AND g.mandante = h.mandante AND g.rut = h.rut
        GROUP BY h.periodo
    ),
    -- Meses de historia disponibles (de los 3 anteriores) en kpi_gestiones_rut.
    historia AS (
        SELECT c.periodo, COUNT(m.periodo) AS meses_historia
        FROM #cortes c
        LEFT JOIN (SELECT DISTINCT periodo FROM dbo.kpi_gestiones_rut) m
            ON m.periodo < c.periodo
           AND m.periodo >= CONVERT(char(7), DATEADD(month, -3, CAST(c.periodo + '-01' AS date)), 120)
        GROUP BY c.periodo
    )
    SELECT c.periodo, ISNULL(MAX(cs.n), 0) AS asignados,
           MAX(al.contactables) AS contactables, MAX(al.contactables_ok) AS contactables_ok,
           MAX(hi.meses_historia) AS meses_historia,
           SUM(CASE WHEN g.f_gest <= c.corte THEN 1 ELSE 0 END) AS gestionados,
           SUM(CASE WHEN g.f_dir <= c.corte THEN 1 ELSE 0 END) AS directo,
           SUM(CASE WHEN (g.f_dir IS NULL OR g.f_dir > c.corte) AND g.f_ind <= c.corte THEN 1 ELSE 0 END) AS indirecto,
           SUM(CASE WHEN g.f_gest <= c.corte AND (g.f_dir IS NULL OR g.f_dir > c.corte)
                         AND (g.f_ind IS NULL OR g.f_ind > c.corte) THEN 1 ELSE 0 END) AS sin_contacto,
           -- Gestiones del mes de cualquier tipo/canal (sin las EXCLUIR). Mes actual: hasta la ultima carga del CRM.
           SUM(CASE WHEN g.f_gest <= c.corte THEN g.n_gestiones ELSE 0 END) AS gestiones,
           SUM(CASE WHEN g.f_gest <= c.corte_eq THEN 1 ELSE 0 END) AS gestionados_eq,
           SUM(CASE WHEN g.f_dir <= c.corte_eq THEN 1 ELSE 0 END) AS directo_eq,
           SUM(CASE WHEN (g.f_dir IS NULL OR g.f_dir > c.corte_eq) AND g.f_ind <= c.corte_eq THEN 1 ELSE 0 END) AS indirecto_eq,
           SUM(CASE WHEN g.f_gest <= c.corte_eq AND (g.f_dir IS NULL OR g.f_dir > c.corte_eq)
                         AND (g.f_ind IS NULL OR g.f_ind > c.corte_eq) THEN 1 ELSE 0 END) AS sin_contacto_eq,
           -- n_gestiones es el total del mes por RUT: en meses cerrados, al corte equivalente queda sobreestimado.
           SUM(CASE WHEN g.f_gest <= c.corte_eq THEN g.n_gestiones ELSE 0 END) AS gestiones_eq
    FROM #cortes c
    LEFT JOIN casos cs ON cs.periodo = c.periodo
    LEFT JOIN alcance al ON al.periodo = c.periodo
    LEFT JOIN historia hi ON hi.periodo = c.periodo
    LEFT JOIN #gest g ON g.periodo = c.periodo
    GROUP BY c.periodo;

    -- 3) Pagos al cierre y al corte equivalente (_eq) por mes.
    SELECT c.periodo, x.pagos, x.pagos_fuera, x.aprox, x.foto,
           e.pagos AS pagos_eq, e.pagos_fuera AS pagos_fuera_eq, e.aprox AS aprox_eq, e.foto AS foto_eq
    FROM #cortes c
    LEFT JOIN {pagos_por_mes("#pagos")} x ON x.periodo = c.periodo
    LEFT JOIN {pagos_por_mes("#pagos_eq")} e ON e.periodo = c.periodo;

    -- 4) Compromisos generados hasta el corte (cierre y equivalente), por mes y estado, con su monto.
    --    en_mes = vence hasta fin de mes (los pendientes que vencen en el mes forman el tubo).
    --    El monto es el que trae el CRM (kpi_compromisos.monto_compromiso), sin ajustes.
    --    Un compromiso por mandante aunque el RUT este en dos carteras que comparten la cartera CRM.
    ;WITH comp AS (
        SELECT DISTINCT c.id, c.periodo, k.mandante, c.crm_cartera, c.rut,
               CAST(c.fecha_gestion AS date) AS f_gest, c.fecha_compromiso, ct.corte, ct.corte_eq,
               CAST(ISNULL(c.monto_compromiso, 0) AS float) AS monto
        FROM dbo.kpi_compromisos c
        INNER JOIN #cortes ct ON ct.periodo = c.periodo
        INNER JOIN dbo.kpi_crm_cartera k ON k.crm_cartera = c.crm_cartera
        INNER JOIN #asig_rut s
            ON s.periodo = c.periodo AND s.mandante = k.mandante AND s.rut = c.rut
           AND (k.cartera IS NULL OR k.cartera = s.cartera)
        WHERE CAST(c.fecha_gestion AS date) <= ct.corte
    )
    SELECT x.periodo, x.corte_tipo, x.estado, x.en_mes, COUNT(*) AS n, SUM(x.monto) AS monto
    FROM (
        SELECT c.periodo, c.monto, v.corte_tipo,
               CASE WHEN c.fecha_compromiso <= EOMONTH(c.corte) THEN 1 ELSE 0 END AS en_mes,
               CASE
                   WHEN v.corte_tipo = 'cierre' AND {cumplido("#pagos")} THEN 'CUMPLIDO'
                   WHEN v.corte_tipo = 'eq' AND {cumplido("#pagos_eq")} THEN 'CUMPLIDO'
                   WHEN c.fecha_compromiso < v.corte_x THEN 'INCUMPLIDO'
                   ELSE 'PENDIENTE'
               END AS estado
        FROM comp c
        CROSS APPLY (VALUES ('cierre', c.corte), ('eq', c.corte_eq)) v(corte_tipo, corte_x)
        WHERE c.f_gest <= v.corte_x
    ) x
    GROUP BY x.periodo, x.corte_tipo, x.estado, x.en_mes;

    -- 5) Segmentos por mes (el mandante es parte del segmento: casos = RUT distintos).
    SELECT a.periodo, {seg_cols_a}, COUNT(DISTINCT a.rut) AS casos, SUM(a.saldo) AS saldo
    FROM #asig a
    GROUP BY a.periodo, {seg_cols_a};

    SELECT 'cierre' AS corte_tipo, p.periodo, {seg_cols_p}, SUM(p.monto) AS pagos
    FROM #pagos p
    WHERE p.tramo <> N'{SIN_ASIGNACION}'{dim_p_sql}
    GROUP BY p.periodo, {seg_cols_p}
    UNION ALL
    SELECT 'eq' AS corte_tipo, p.periodo, {seg_cols_p}, SUM(p.monto) AS pagos
    FROM #pagos_eq p
    WHERE p.tramo <> N'{SIN_ASIGNACION}'{dim_p_sql}
    GROUP BY p.periodo, {seg_cols_p};

    -- 6) Mandantes con pagos aproximados por mes (sin foto diaria anterior al corte).
    SELECT DISTINCT 'cierre' AS corte_tipo, p.periodo, p.mandante
    FROM #pagos p
    WHERE p.aprox = 1{dim_p_sql}
    UNION
    SELECT DISTINCT 'eq' AS corte_tipo, p.periodo, p.mandante
    FROM #pagos_eq p
    WHERE p.aprox = 1{dim_p_sql};
    """
    # Mes que se trata como "en curso" en las fotos de pagos; con mes_anterior todos los meses estan cerrados.
    periodo_abierto = "" if mes_anterior else periodo_en_curso
    params = [
        *cortes_params, *dim_a_params,
        periodo_abierto, periodo_abierto, *mand_params,  # #fotos
        *mand_params, *mand_params,  # #pagos, #pagos_eq
        *dim_p_params, *dim_p_params,  # 3) pagos por mes
        *dim_p_params, *dim_p_params,  # 5) pagos por segmento
        *dim_p_params, *dim_p_params,  # 6) aproximados
    ]
    asig, contacto, pagos, compromisos, seg_asig, seg_pagos, aprox = run_query_sets(sql, tuple(params))
    response = _build_response(referencia, cortes, filters, asig, contacto, pagos, compromisos, seg_asig, seg_pagos)
    for mes in response["meses"]:
        for tipo, sufijo in CORTES_TIPO.items():
            mes[f"aproximado_mandantes{sufijo}"] = sorted(
                {r["mandante"] for r in aprox if r["periodo"] == mes["periodo"] and r["corte_tipo"] == tipo}
            )
    response["hoy"] = hoy.isoformat()
    response["mes_anterior"] = mes_anterior
    response["periodo_en_curso"] = periodo_en_curso
    if mes_anterior:
        # El mes mostrado ya cerro: no hay cierre que proyectar.
        response["proyeccion"] = None
    return response


def _delta(actual, anterior, delta_tipo: str) -> float | None:
    if actual is None or anterior is None:
        return None
    return actual - anterior if delta_tipo == "pp" else _safe_div(actual - anterior, anterior)


def _kpi(nombre: str, valores: list, valores_cierre: list) -> dict:
    """valores/delta al corte equivalente (comparable con hoy); valores_cierre/delta_cierre al cierre de cada mes."""
    tipo, delta_tipo = TIPO_KPI[nombre]
    return {
        "tipo": tipo,
        "valores": valores,
        "delta": _delta(valores[0], valores[1], delta_tipo),
        "valores_cierre": valores_cierre,
        "delta_cierre": _delta(valores_cierre[0], valores_cierre[1], delta_tipo),
        "delta_tipo": delta_tipo,
    }


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


def _valores_mes(a: dict, c: dict, p: dict, cp: dict, mp: dict, sufijo: str) -> dict:
    """KPIs de un mes a un corte; sufijo '' = cierre, '_eq' = corte equivalente (asignacion igual en ambos)."""
    saldo = float(a.get("saldo") or 0)
    asignados = int(c.get("asignados") or 0)
    gestionados = int(c.get(f"gestionados{sufijo}") or 0)
    directo = int(c.get(f"directo{sufijo}") or 0)
    monto = float(p.get(f"pagos{sufijo}") or 0)
    total_comp = sum(cp.values())
    # Alcance de contacto: sin sufijo a proposito (meses anteriores completos, mes actual hasta hoy).
    contactables = int(c.get("contactables") or 0)
    logrados = int(c.get("contactables_ok") or 0)
    return {
        "casos": int(a.get("casos") or 0),
        # Operaciones asignadas (un RUT puede tener varias).
        "operaciones": int(a.get("operaciones") or 0),
        "saldo": saldo,
        "contactabilidad": _safe_div(directo, gestionados),
        "cobertura": _safe_div(gestionados, asignados),
        "pagos": monto,
        "recuperacion": _safe_div(monto, saldo),
        "gestionados": gestionados,
        "contacto_directo": directo,
        "contacto_indirecto": int(c.get(f"indirecto{sufijo}") or 0),
        "sin_contacto": int(c.get(f"sin_contacto{sufijo}") or 0),
        "compromisos": total_comp,
        "cumplidos": cp["CUMPLIDO"],
        "incumplidos": cp["INCUMPLIDO"],
        "pendientes": cp["PENDIENTE"],
        # Sobre el total de compromisos generados (cumplidos + incumplidos + pendientes = 100%).
        "pct_cumplidos": _safe_div(cp["CUMPLIDO"], total_comp),
        "pct_incumplidos": _safe_div(cp["INCUMPLIDO"], total_comp),
        # Intensidad = gestiones (cualquier tipo) / casos asignados.
        "intensidad": _safe_div(int(c.get(f"gestiones{sufijo}") or 0), asignados),
        # Clientes asignados sin ninguna gestion al corte.
        "sin_gestion": _safe_div(asignados - gestionados, asignados),
        "no_gestionados": max(asignados - gestionados, 0),
        "monto_comprometido": sum(mp.values()),
        # Contactables = asignados con contacto titular en los 3 meses anteriores.
        "contactables": contactables,
        "alcance_contacto": _safe_div(contactables, asignados),
        "contactables_logrados": logrados,
        "contactables_pendientes": max(contactables - logrados, 0),
        "avance_alcance": _safe_div(logrados, contactables),
    }


def _build_response(hoy, cortes, filters, asig, contacto, pagos, compromisos, seg_asig, seg_pagos) -> dict:
    periodos = [periodo for periodo, _, _ in cortes]
    by = lambda rows: {row["periodo"]: row for row in rows}  # noqa: E731
    asig_p, cont_p, pagos_p = by(asig), by(contacto), by(pagos)

    # Compromisos por (periodo, corte_tipo).
    claves = [(p, t) for p in periodos for t in CORTES_TIPO]
    comp_p: dict[tuple, dict] = {k: {"CUMPLIDO": 0, "INCUMPLIDO": 0, "PENDIENTE": 0} for k in claves}
    monto_p: dict[tuple, dict] = {k: {"CUMPLIDO": 0.0, "INCUMPLIDO": 0.0, "PENDIENTE": 0.0} for k in claves}
    tubo_p: dict[tuple, dict] = {k: {"n": 0, "monto": 0.0} for k in claves}
    for row in compromisos:
        key, estado = (row["periodo"], row["corte_tipo"]), row["estado"]
        n, monto_c = int(row.get("n") or 0), float(row.get("monto") or 0)
        comp_p[key][estado] += n
        monto_p[key][estado] += monto_c
        # Tubo: pendientes (sin pago, aun no vencen) que vencen hasta fin de mes.
        if estado == "PENDIENTE" and row.get("en_mes"):
            tubo_p[key]["n"] += n
            tubo_p[key]["monto"] += monto_c

    series: dict[str, dict[str, list]] = {t: {name: [] for name in TIPO_KPI} for t in CORTES_TIPO}
    meses = []
    tipos_contacto = []
    for periodo, corte, corte_eq in cortes:
        a, c, p = asig_p.get(periodo, {}), cont_p.get(periodo, {}), pagos_p.get(periodo, {})
        con_datos = int(a.get("casos") or 0) > 0
        for tipo, sufijo in CORTES_TIPO.items():
            valores = _valores_mes(a, c, p, comp_p[(periodo, tipo)], monto_p[(periodo, tipo)], sufijo)
            for name, value in valores.items():
                # Mes sin asignacion cargada: sin dato (no cero), para no mostrar caidas falsas.
                series[tipo][name].append(value if con_datos else None)

        meses.append({
            "periodo": periodo,
            "corte": corte.isoformat(),
            "corte_equivalente": corte_eq.isoformat(),
            "dias_habiles_restantes": _habiles_restantes(corte_eq),
            "con_datos": con_datos,
            "aproximado": bool(p.get("aprox")),
            "aproximado_eq": bool(p.get("aprox_eq")),
            "foto_pagos": _iso(p.get("foto")),
            "foto_pagos_eq": _iso(p.get("foto_eq")),
            "pagos_fuera_asignacion": float(p.get("pagos_fuera") or 0),
            "pagos_fuera_asignacion_eq": float(p.get("pagos_fuera_eq") or 0),
            # Meses (de los 3 anteriores) con gestiones cargadas para el alcance de contacto.
            "meses_historia": int(c.get("meses_historia") or 0),
        })
        # Tipos de contacto al corte equivalente (comparable con hoy).
        tipos_contacto.append({
            "periodo": periodo,
            "gestionados": int(c.get("gestionados_eq") or 0),
            "directo": int(c.get("directo_eq") or 0),
            "indirecto": int(c.get("indirecto_eq") or 0),
            "sin_contacto": int(c.get("sin_contacto_eq") or 0),
        })

    # Segmentos: una fila por segmento con los 4 meses. pagos/recuperacion al corte equivalente; *_cierre al cierre.
    segmentos: dict[tuple, dict] = {}
    keys = ("mandante", "cartera", "tramo") if _unico(filters, "mandante") else ("mandante",)
    vacio = lambda: {"casos": 0, "saldo": 0.0, "pagos": 0.0, "pagos_cierre": 0.0}  # noqa: E731
    for row in seg_asig:
        key = tuple(row.get(k) for k in keys)
        item = segmentos.setdefault(key, {**dict(zip(keys, key)), "meses": {}})
        item["meses"][row["periodo"]] = {**vacio(), "casos": int(row.get("casos") or 0), "saldo": float(row.get("saldo") or 0)}
    for row in seg_pagos:
        key = tuple(row.get(k) for k in keys)
        if key not in segmentos:
            continue
        mes = segmentos[key]["meses"].setdefault(row["periodo"], vacio())
        mes["pagos" if row["corte_tipo"] == "eq" else "pagos_cierre"] = float(row.get("pagos") or 0)
    seg_rows = []
    for item in segmentos.values():
        for mes in item["meses"].values():
            mes["recuperacion"] = _safe_div(mes["pagos"], mes["saldo"])
            mes["recuperacion_cierre"] = _safe_div(mes["pagos_cierre"], mes["saldo"])
        seg_rows.append(item)
    seg_rows.sort(key=_segment_order(_unico(filters, "mandante")))

    # Proyeccion de cierre: pagos a hoy + tubo del mes x cumplimiento en monto de los 3 meses cerrados (al cierre).
    cierre, eq = series["cierre"], series["eq"]
    cerrados = [p for p, m in zip(periodos[1:], meses[1:]) if m["con_datos"]]
    cumplido_3m = sum(monto_p[(p, "cierre")]["CUMPLIDO"] for p in cerrados)
    vencido_3m = sum(monto_p[(p, "cierre")]["CUMPLIDO"] + monto_p[(p, "cierre")]["INCUMPLIDO"] for p in cerrados)
    tasa = _safe_div(cumplido_3m, vencido_3m)
    tubo = tubo_p[(periodos[0], "cierre")]
    pagos_hoy = cierre["pagos"][0]
    aporte = tubo["monto"] * tasa if tasa is not None else None
    proyeccion = (pagos_hoy or 0) + aporte if pagos_hoy is not None and aporte is not None else None
    cierre_anterior = cierre["pagos"][1]
    saldo_actual = cierre["saldo"][0]

    return {
        "hoy": hoy.isoformat(),
        "filtros": filters,
        "dias_habiles_restantes": _habiles_restantes(hoy),
        "meses": meses,
        "kpis": {name: _kpi(name, eq[name], cierre[name]) for name in TIPO_KPI},
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
            # Pagos del mes anterior al corte equivalente (mismos dias habiles restantes que hoy).
            "pagos_mismo_dia_anterior": eq["pagos"][1],
            "delta_vs_cierre_anterior": _safe_div(proyeccion - cierre_anterior, cierre_anterior)
            if proyeccion is not None and cierre_anterior else None,
            "fin_mes": _cortes(hoy)[0][1].replace(day=calendar.monthrange(hoy.year, hoy.month)[1]).isoformat(),
        },
        "tipos_contacto": tipos_contacto,
        "segmentos": seg_rows,
        "vacio": not any(m["con_datos"] for m in meses),
    }
