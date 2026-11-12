from __future__ import annotations

from datetime import date

from cache import cached, cached_view
from database import run_query, run_query_sets


USER_TO_NAME = {
    "EMUNOZ": "Elizabeth Muñoz",
    "LROJAS": "Lissette Rojas",
    "MINOSTROZA": "Marilin Inostroza",
    "CVERA": "Carolina Vera",
    "SDUARTE": "Susana Duarte",
    "BMONCADA": "Barbara Canales",
    "SFUENTES": "Sandra Fuentes",
    "MCOLMENARES": "Marlexis Colmenares",
    "PALTAMIRANO": "Paula Altamirano",
    "RCALDERON": "Rocio Calderon",
    "RCHERNANDEZ": "Raiza Hernandez",
    "MLOPEZ": "Margarita Lopez",
}

# Altas y bajas del equipo (YYYYMM): la ejecutiva se mide desde EQUIPO_DESDE y hasta EQUIPO_HASTA inclusive.
EQUIPO_DESDE = {"RCHERNANDEZ": "202611", "MLOPEZ": "202611"}
EQUIPO_HASTA = {"BMONCADA": "202610", "EMUNOZ": "202610", "MCOLMENARES": "202610"}

USER_ORDER = [
    "EMUNOZ",
    "LROJAS",
    "MINOSTROZA",
    "CVERA",
    "SDUARTE",
    "BMONCADA",
    "SFUENTES",
    "MCOLMENARES",
    "PALTAMIRANO",
    "RCALDERON",
    "RCHERNANDEZ",
    "MLOPEZ",
]


def usuarios_del_mes(periodo: str) -> list[str]:
    """Ejecutivas que se miden en el mes de la foto, en el orden de siempre."""
    mes = "".join(ch for ch in str(periodo) if ch.isdigit())[:6]
    return [u for u in USER_ORDER if EQUIPO_DESDE.get(u, "000000") <= mes <= EQUIPO_HASTA.get(u, "999999")]

# Nombre con que el archivo de negocios (columna DERIVADO) identifica a cada ejecutiva.
DERIVADO_TO_USER = {
    "ELY": "EMUNOZ",
    "LISSETTE": "LROJAS",
    "MARILYN": "MINOSTROZA",
    "CAROLINA": "CVERA",
    "SUSANA": "SDUARTE",
    "BARBARA": "BMONCADA",
    "SANDRA": "SFUENTES",
    "MARLEXIS": "MCOLMENARES",
    "PAULA": "PALTAMIRANO",
    "ROCIO": "RCALDERON",
    "RAIZA": "RCHERNANDEZ",
    "MARGARITA": "MLOPEZ",
}

# Peso de cada respuesta: 1 es la mejor. Las respuestas que no estan aca no cuentan.
PESO_RESPUESTA = [
    "COMPROMISO NORMALIZACION",
    "COMPROMISO CONTENCION",
    "COMPROMISO PREPAGO",
    "COMPROMISO",
    "COMPROMISO ADP (CUOTA)",
    "COMPRA DIRECTA EN TRAMITE",
    "COMPRA DIRECTA CONCRETADA",
    "COMPRA DIRECTA INTERESADO",
    "COMPROMISO INTERESADO EN PAC",
    "COMPROMISO PUT",
    "COMPROMISO SOLICITA PREPAGO",
    "DACION",
    "NOVACION EN TRMITE",
    "NOVACION",
    "REFINANCIAMIENTO",
    "RECONDUCCION EN TRAMITE",
    "RECONDUCCION INTERESADO",
    "NOVACION INTERESADO",
    "DACION EN TRAMITE",
    "DACION INTERESADO",
    "REFINANCIAMIENTO EN TRAMITE",
    "REFINANCIAMIENTO INTERESADO",
    "A LA ESPERA DEL DESCUENTO PAC",
    "RENOVACION EN TRAMITE",
    "VENTA DIRECTA EN TRAMITE",
    "VENTA DIRECTA INTERESADO",
    "RENOVACION INTERESADO",
    "REGULARIZAR POR SUS PROPIOS MEDIOS",
    "ADP EN TRAMITE",
    "ADP INTERESADO",
    "PAGARE EN TRIBUNALES",
    "RENOVACION",
    "CESANTE",
    "EN TRAMITE CON CONCESIONARIO",
    "ENFERMEDAD DEUDOR MUCHOS GASTOS MEDICOS",
    "ENFERMEDAD DEUDOR TERMINAL",
    "YA PAGO",
    "NOVACION EN TRAMITE",
    "PROBLEMA ECONOMICO IMPREVISTO",
    "PROBLEMA ECONOMICO SUELDO INSUFICIENTE",
    "PROBLEMAS TECNICOS PARA PAGAR CONSUMER.CL",
    "PROBLEMAS TECNICOS PARA PAGAR PAC",
    "SINIESTRO PERDIDA TOTAL",
    "FALLECIDO",
]


# Equipos de octubre 2026: cada ejecutiva solo suma en su ambito (C1 o C2C3) y una gestion fuera de el no
# cuenta. Los equipos se separaron el 13-10, pero se aplica todo el mes: los pagos de un ciclo que no es el
# suyo pasan a la mejor gestion de alguien de ese ciclo. Sin fila para la fecha de la gestion, cuenta en
# cualquier tramo. Desde el 16-10 Marlexis trabaja la base FPD, que se calcula aparte: ninguna de sus
# gestiones cuenta.
_EQUIPO_C1 = ("CVERA", "SDUARTE", "RCALDERON", "PALTAMIRANO", "MINOSTROZA")
_EQUIPO_C2C3 = ("BMONCADA", "EMUNOZ", "SFUENTES", "LROJAS")
EQUIPOS = [
    *((user, "C1", "2026-10-01", "2026-10-31") for user in _EQUIPO_C1),
    *((user, "C2C3", "2026-10-01", "2026-10-31") for user in _EQUIPO_C2C3),
    ("MCOLMENARES", "C2C3", "2026-10-01", "2026-10-15"),
    ("MCOLMENARES", "FPD", "2026-10-16", "2026-10-31"),
]
# Operaciones FPD del mes (ETL/carga_fpd_temprana.py): siguen en el bench y en el detalle con la marca fpd,
# pero no suman al aporte (deuda asignada ni monto contenido) de nadie.
FPD_TABLE = "dbo.tmp_sc_temprana_fpd"

BENCH_TABLE = "dbo.tmp_bench_temp_STC"
# El bench de fin de mes guarda dos cargas del mismo archivo (ETL/bench_recarga.py):
# version_carga = 'PRECIERRE' en la primera y NULL en la vigente (cierre).
VERSION_COL = "version_carga"
_version_col_disponible = False


def _tiene_version() -> bool:
    """La columna se crea con SQL/sct_precierre.sql o en la primera carga del ETL."""
    global _version_col_disponible
    if not _version_col_disponible:
        rows = run_query("SELECT COL_LENGTH(?, ?) AS largo", (BENCH_TABLE, VERSION_COL))
        _version_col_disponible = bool(rows and rows[0].get("largo") is not None)
    return _version_col_disponible


def _normalize_period(periodo: str | None) -> str:
    if periodo:
        # El filtro puede traer la version de la carga: 'YYYYMMDD (Cierre)' / 'YYYYMMDD (Pre-cierre)'.
        value = str(periodo).strip().split(" (")[0].strip()
        if len(value) >= 10:
            return value[:10]
        return value

    sql = """
    SELECT CONVERT(char(10), MAX(fld_fecha), 126) AS periodo
    FROM dbo.tmp_bench_temp_STC
    """
    rows = run_query(sql)
    return (rows[0].get("periodo") if rows else None) or date.today().isoformat()


def _period_version(periodo: str | None) -> str:
    text = str(periodo or "").upper().replace("-", "")
    return "PRECIERRE" if "PRECIERRE" in text else "CIERRE"


def _bench_source(periodo: str, version: str) -> str:
    """Origen del bench para las consultas: solo la carga vigente de cada foto. Para el pre-cierre,
    la foto de la fecha consultada es la carga de pre-cierre; las demas fotos del mes, la vigente."""
    if not _tiene_version():
        return BENCH_TABLE
    columnas = (
        "id_bench_temp_stc, fld_OPERACION, fld_RUT, fld_TRAMO_MORA, fld_DEUDA_INI, "
        "fld_CONTENIDO, fld_NORMALIZADO, fld_FEC_ULT_PAGO, fld_fecha"
    )
    if version != "PRECIERRE" or not periodo.isdigit():
        return f"(SELECT {columnas} FROM {BENCH_TABLE} WHERE {VERSION_COL} IS NULL)"
    return f"""(
            SELECT {columnas} FROM {BENCH_TABLE}
            WHERE ({VERSION_COL} IS NULL AND fld_fecha <> '{periodo}')
               OR ({VERSION_COL} = 'PRECIERRE' AND fld_fecha = '{periodo}')
        )"""


def _safe_div(num: float, den: float) -> float:
    if den is None or den == 0:
        return 0.0
    return (num / den) * 100.0


def _equipo_insert(periodo: str) -> str:
    """INSERT de #equipo con las filas de EQUIPOS que tocan el mes de la foto (vacio en otros meses)."""
    mes = "".join(ch for ch in periodo if ch.isdigit())[:6]
    filas = [
        f"('{user}', '{ambito}', '{desde}', '{hasta}')"
        for user, ambito, desde, hasta in EQUIPOS
        if desde.replace("-", "")[:6] <= mes <= hasta.replace("-", "")[:6]
    ]
    return f"INSERT INTO #equipo VALUES {', '.join(filas)};" if filas else ""


def _asignacion_sql(periodo: str, version: str = "CIERRE") -> tuple[str, list]:
    """Lote SQL que deja en #asig una fila por operacion del bench con la gestion que se la lleva.

    Fecha de pago de una operacion contenida: el ultimo pago informado en el primer bench del mes
    en que aparece contenida (si no es una fecha del mes hasta ese bench, la fecha de ese bench).
    Gana la mejor gestion del RUT hasta la fecha de pago (peso de la respuesta y la mas reciente);
    si no hay, la primera gestion posterior. Asi el contenido no cambia de ejecutivo al llegar
    gestiones nuevas. Las operaciones no contenidas van a la mejor gestion del mes.

    Solo cuentan las gestiones dentro del ambito de la ejecutiva en esa fecha (EQUIPOS). Las operaciones
    FPD del mes quedan marcadas con fpd = 1.
    """
    bench = _bench_source(periodo, version)
    peso_case = "\n".join(
        "                WHEN '{}' THEN {}".format(respuesta.replace("'", "''"), peso)
        for peso, respuesta in enumerate(PESO_RESPUESTA, start=1)
    )
    sql = f"""SET NOCOUNT ON;
    CREATE TABLE #equipo (
        usuario varchar(30) COLLATE DATABASE_DEFAULT,
        ambito varchar(10) COLLATE DATABASE_DEFAULT,
        desde date,
        hasta date
    );
    {_equipo_insert(periodo)}

    CREATE TABLE #fpd (operacion nvarchar(60) COLLATE DATABASE_DEFAULT PRIMARY KEY);
    IF OBJECT_ID('{FPD_TABLE}') IS NOT NULL
        INSERT INTO #fpd (operacion)
        SELECT DISTINCT LTRIM(RTRIM(operacion)) FROM {FPD_TABLE} WHERE periodo = LEFT(?, 6);

    SELECT
        g.rut,
        g.UsuarioGestion,
        g.RespuestaGestion,
        g.GestionFecha,
        g.GestionHora,
        g.telefono,
        p.peso_gestion
    INTO #gest
    FROM dbo.tmp_GEST_CRM g
    CROSS APPLY (
        SELECT
            CASE g.RespuestaGestion
{peso_case}
                ELSE 999
            END AS peso_gestion
    ) p
    WHERE g.cartera = 526
      AND g.GestionFecha BETWEEN DATEFROMPARTS(YEAR(?), MONTH(?), 1) AND CAST(? AS date)
      AND g.ContactoGestion IN ('TITULAR', 'INFORMATIVO')
      AND p.peso_gestion <> 999;

    CREATE CLUSTERED INDEX IX_gest_rut ON #gest (rut);

    SELECT
        x.operacion,
        CASE
            WHEN TRY_CAST(x.ult_pago AS date) BETWEEN DATEFROMPARTS(YEAR(?), MONTH(?), 1) AND TRY_CAST(x.foto AS date)
                THEN TRY_CAST(x.ult_pago AS date)
            ELSE TRY_CAST(x.foto AS date)
        END AS fecha_pago
    INTO #pago
    FROM (
        SELECT
            b.fld_OPERACION AS operacion,
            b.fld_fecha AS foto,
            MAX(b.fld_FEC_ULT_PAGO) AS ult_pago,
            ROW_NUMBER() OVER (PARTITION BY b.fld_OPERACION ORDER BY b.fld_fecha) AS rn
        FROM {bench} b
        WHERE LEFT(b.fld_fecha, 6) = LEFT(?, 6)
          AND b.fld_fecha <= ?
          AND ISNULL(b.fld_CONTENIDO, 0) <> 0
        GROUP BY b.fld_OPERACION, b.fld_fecha
    ) x
    WHERE x.rn = 1;

    SELECT
        b.id_bench_temp_stc AS fila,
        b.fld_OPERACION AS operacion,
        b.fld_RUT AS rut,
        LTRIM(RTRIM(b.fld_TRAMO_MORA)) AS tramo,
        CASE WHEN f.operacion IS NOT NULL THEN 1 ELSE 0 END AS fpd,
        CAST(ISNULL(b.fld_DEUDA_INI, 0) AS float) AS deuda,
        CAST(ISNULL(b.fld_CONTENIDO, 0) AS float) AS monto_contenido,
        CASE WHEN ISNULL(b.fld_CONTENIDO, 0) <> 0 THEN 1 ELSE 0 END AS contenido,
        CASE WHEN ISNULL(b.fld_NORMALIZADO, 0) <> 0 THEN 1 ELSE 0 END AS normalizado,
        CASE WHEN ISNULL(b.fld_CONTENIDO, 0) <> 0 THEN p.fecha_pago END AS fecha_pago
    INTO #ops
    FROM {bench} b
    LEFT JOIN #pago p ON p.operacion = b.fld_OPERACION
    LEFT JOIN #fpd f ON f.operacion = LTRIM(RTRIM(b.fld_OPERACION))
    WHERE b.fld_fecha = ?;

    WITH candidatas AS (
        SELECT
            o.fila,
            g.UsuarioGestion,
            g.RespuestaGestion,
            g.GestionFecha,
            g.GestionHora,
            g.telefono,
            g.peso_gestion,
            CASE WHEN o.fecha_pago IS NOT NULL AND g.GestionFecha > o.fecha_pago THEN 1 ELSE 0 END AS es_posterior
        FROM #ops o
        INNER JOIN #gest g ON g.rut = o.rut
        WHERE NOT EXISTS (
            SELECT 1 FROM #equipo e
            WHERE e.usuario = g.UsuarioGestion
              AND g.GestionFecha BETWEEN e.desde AND e.hasta
              AND e.ambito <> CASE WHEN o.tramo = 'C1' THEN 'C1' ELSE 'C2C3' END
        )
    ),
    elegida AS (
        SELECT
            c.*,
            ROW_NUMBER() OVER (
                PARTITION BY c.fila
                ORDER BY
                    c.es_posterior ASC,
                    CASE WHEN c.es_posterior = 0 THEN c.peso_gestion ELSE 0 END ASC,
                    CASE WHEN c.es_posterior = 0 THEN c.GestionFecha END DESC,
                    CASE WHEN c.es_posterior = 0 THEN c.GestionHora END DESC,
                    c.GestionFecha ASC,
                    c.GestionHora ASC
            ) AS rn
        FROM candidatas c
    )
    SELECT
        o.operacion,
        o.rut,
        o.tramo,
        o.fpd,
        o.deuda,
        o.monto_contenido,
        o.contenido,
        o.normalizado,
        e.UsuarioGestion AS usuario_gestion,
        e.RespuestaGestion AS respuesta_gestion,
        e.GestionFecha AS gestion_fecha,
        e.telefono
    INTO #asig
    FROM #ops o
    LEFT JOIN elegida e ON e.fila = o.fila AND e.rn = 1;
    """
    return sql, [periodo] * 9


@cached_view
def get_filter_values(periodo: str | None = None) -> dict:
    sql_periodos = """
    -- Meses anteriores: solo su ultima fecha; mes actual: todas (fld_fecha es texto YYYYMMDD).
    WITH f AS (
        SELECT DISTINCT CONVERT(char(10), fld_fecha, 126) AS fecha
        FROM dbo.tmp_bench_temp_STC
        WHERE fld_fecha IS NOT NULL
    )
    SELECT fecha AS periodo
    FROM (SELECT fecha, MAX(fecha) OVER (PARTITION BY LEFT(LTRIM(fecha), 6)) AS ultima FROM f) x
    WHERE fecha = ultima
       OR LEFT(LTRIM(fecha), 6) = CONVERT(char(6), GETDATE(), 112)
    ORDER BY periodo DESC
    """
    con_precierre: set[str] = set()
    if _tiene_version():
        sql_precierres = f"""
        SELECT DISTINCT CONVERT(char(10), fld_fecha, 126) AS periodo
        FROM {BENCH_TABLE}
        WHERE {VERSION_COL} = 'PRECIERRE' AND fld_fecha IS NOT NULL
        """
        con_precierre = {r["periodo"].strip() for r in run_query(sql_precierres) if r.get("periodo")}
    # La fecha con pre-cierre se ofrece dos veces: la carga vigente (cierre) y la primera (pre-cierre).
    periodos: list[str] = []
    for fecha in (r["periodo"] for r in run_query(sql_periodos) if r.get("periodo")):
        if fecha.strip() in con_precierre:
            periodos += [f"{fecha.strip()} (Cierre)", f"{fecha.strip()} (Pre-cierre)"]
        else:
            periodos.append(fecha)

    ejecutivos = [USER_TO_NAME[u] for u in USER_ORDER]
    if periodo:
        # Solo los ejecutivos con cartera en la vista del periodo, en el mismo orden de siempre.
        con_datos = {row.get("ejecutivo") for row in get_cycle_view({"periodo": periodo})}
        ejecutivos = [nombre for nombre in ejecutivos if nombre in con_datos]

    return {
        "periodos": periodos,
        "tramos": [],
        "aperturas": [],
        "ejecutivos": ejecutivos,
        "usuarios_gestion": [{"usuario": user, "nombre": USER_TO_NAME[user]} for user in USER_ORDER],
        "zonas": [],
    }


def get_general_view(filters: dict) -> list[dict]:
    return []


def _cycle_data(periodo: str, version: str) -> tuple[list[dict], int]:
    """Montos por usuario de gestion y casos C3 del bench para la foto consultada."""
    asignacion_sql, params = _asignacion_sql(periodo, version)
    usuarios = ", ".join(f"'{user}'" for user in usuarios_del_mes(periodo))
    sql = f"""{asignacion_sql}
    SELECT
        a.usuario_gestion,
        SUM(CASE WHEN a.tramo = 'C1' THEN a.deuda ELSE 0 END) AS c1_deuda_asignada,
        SUM(CASE WHEN a.tramo = 'C1' THEN a.monto_contenido ELSE 0 END) AS c1_monto_cont,
        SUM(CASE WHEN a.tramo = 'C2' THEN a.deuda ELSE 0 END) AS c2_deuda_asignada,
        SUM(CASE WHEN a.tramo = 'C2' THEN a.monto_contenido ELSE 0 END) AS c2_monto_cont,
        SUM(CASE WHEN a.tramo = 'C3' THEN a.deuda ELSE 0 END) AS c3_deuda_asignada,
        SUM(CASE WHEN a.tramo = 'C3' THEN a.monto_contenido ELSE 0 END) AS c3_monto_cont,
        SUM(CASE WHEN a.tramo = 'C3' THEN 1 ELSE 0 END) AS c3_casos
    FROM #asig a
    WHERE a.usuario_gestion IN ({usuarios})
      AND a.tramo IN ('C1', 'C2', 'C3')
      AND a.fpd = 0
    GROUP BY a.usuario_gestion
    """

    raw_rows = run_query_sets(sql, tuple(params))[-1]

    # Casos C3 del bench sin las operaciones FPD, que se calculan aparte.
    sql_c3_base = f"""
    SELECT COUNT_BIG(1) AS c3_casos_base
    FROM {_bench_source(periodo, version)} b
    WHERE fld_fecha = ?
      AND UPPER(LTRIM(RTRIM(fld_TRAMO_MORA))) = 'C3'
      AND NOT EXISTS (
          SELECT 1 FROM {FPD_TABLE} f
          WHERE f.periodo = LEFT(?, 6) AND f.operacion = LTRIM(RTRIM(b.fld_OPERACION))
      )
    """
    c3_base_rows = run_query(sql_c3_base, (periodo, periodo))
    c3_casos_base = int(c3_base_rows[0].get("c3_casos_base") or 0) if c3_base_rows else 0
    return raw_rows, c3_casos_base


def get_cycle_view(filters: dict) -> list[dict]:
    periodo = _normalize_period(filters.get("periodo"))
    version = _period_version(filters.get("periodo"))
    ejecutivo_filter = str(filters.get("ejecutivo") or "").strip().lower()

    # El lote es el mismo para todos los ejecutivos: el filtro se aplica en memoria sobre lo guardado.
    raw_rows, c3_casos_base = cached(("sc_temprana", "ciclo", periodo, version), lambda: _cycle_data(periodo, version))

    c1_total_cont = sum(float(r.get("c1_monto_cont") or 0) for r in raw_rows)
    c2_total_cont = sum(float(r.get("c2_monto_cont") or 0) for r in raw_rows)
    c3_total_cont = sum(float(r.get("c3_monto_cont") or 0) for r in raw_rows)

    rows: list[dict] = []
    for user in usuarios_del_mes(periodo):
        item = next((r for r in raw_rows if str(r.get("usuario_gestion") or "").strip().upper() == user), None)
        c1_deuda = float(item.get("c1_deuda_asignada") or 0) if item else 0.0
        c1_cont = float(item.get("c1_monto_cont") or 0) if item else 0.0
        c2_deuda = float(item.get("c2_deuda_asignada") or 0) if item else 0.0
        c2_cont = float(item.get("c2_monto_cont") or 0) if item else 0.0
        c3_deuda = float(item.get("c3_deuda_asignada") or 0) if item else 0.0
        c3_cont = float(item.get("c3_monto_cont") or 0) if item else 0.0
        c3_casos = int(item.get("c3_casos") or 0) if item else 0

        row = {
            "ejecutivo": USER_TO_NAME[user],
            "c1_deuda_asignada": c1_deuda,
            "c1_monto_cont": c1_cont,
            "c1_porc_contenido": _safe_div(c1_cont, c1_deuda),
            "c1_porc_aporte": _safe_div(c1_cont, c1_total_cont),
            "c2_deuda_asignada": c2_deuda,
            "c2_monto_cont": c2_cont,
            "c2_porc_contenido": _safe_div(c2_cont, c2_deuda),
            "c2_porc_aporte": _safe_div(c2_cont, c2_total_cont),
            "c3_deuda_asignada": c3_deuda,
            "c3_monto_cont": c3_cont,
            "c3_porc_contenido": _safe_div(c3_cont, c3_deuda),
            "c3_porc_aporte": _safe_div(c3_cont, c3_total_cont),
            "c3_casos": c3_casos,
        }

        if ejecutivo_filter and row["ejecutivo"].strip().lower() != ejecutivo_filter:
            continue
        rows.append(row)

    total_c1_deuda = sum(r["c1_deuda_asignada"] for r in rows)
    total_c1_cont = sum(r["c1_monto_cont"] for r in rows)
    total_c2_deuda = sum(r["c2_deuda_asignada"] for r in rows)
    total_c2_cont = sum(r["c2_monto_cont"] for r in rows)
    total_c3_deuda = sum(r["c3_deuda_asignada"] for r in rows)
    total_c3_cont = sum(r["c3_monto_cont"] for r in rows)
    total_c3_casos = sum(r["c3_casos"] for r in rows)

    rows.append(
        {
            "ejecutivo": "Total",
            "c1_deuda_asignada": total_c1_deuda,
            "c1_monto_cont": total_c1_cont,
            "c1_porc_contenido": _safe_div(total_c1_cont, total_c1_deuda),
            "c1_porc_aporte": 100.0 if total_c1_cont > 0 else 0.0,
            "c2_deuda_asignada": total_c2_deuda,
            "c2_monto_cont": total_c2_cont,
            "c2_porc_contenido": _safe_div(total_c2_cont, total_c2_deuda),
            "c2_porc_aporte": 100.0 if total_c2_cont > 0 else 0.0,
            "c3_deuda_asignada": total_c3_deuda,
            "c3_monto_cont": total_c3_cont,
            "c3_porc_contenido": _safe_div(total_c3_cont, total_c3_deuda),
            "c3_porc_aporte": 100.0 if total_c3_cont > 0 else 0.0,
            "c3_casos": total_c3_casos,
            "c3_casos_base": c3_casos_base,
        }
    )

    return rows


def get_detail_view(filters: dict) -> dict:
    periodo = _normalize_period(filters.get("periodo"))
    operacion = str(filters.get("operacion") or "").strip()
    contenido = str(filters.get("contenido") or "").strip()
    normalizado = str(filters.get("normalizado") or "").strip()
    usuario_gestion = str(filters.get("usuario_gestion") or "").strip().upper()
    tramo = str(filters.get("tramo") or "").strip().upper()
    page = max(1, int(filters.get("page") or 1))
    page_size = min(500, max(1, int(filters.get("page_size") or 100)))
    offset = (page - 1) * page_size

    asignacion_sql, params = _asignacion_sql(periodo, _period_version(filters.get("periodo")))
    where_clauses = []

    if operacion:
        where_clauses.append("CAST(base.operacion AS VARCHAR(100)) LIKE ?")
        params.append(f"%{operacion}%")
    if contenido in {"0", "1"}:
        where_clauses.append("base.contenido = ?")
        params.append(int(contenido))
    if normalizado in {"0", "1"}:
        where_clauses.append("base.normalizado = ?")
        params.append(int(normalizado))
    if usuario_gestion:
        where_clauses.append("UPPER(LTRIM(RTRIM(ISNULL(base.usuario_gestion, '')))) = ?")
        params.append(usuario_gestion)
    if tramo:
        where_clauses.append("UPPER(LTRIM(RTRIM(base.tramo))) = ?")
        params.append(tramo)

    extra_where = ""
    if where_clauses:
        extra_where = "WHERE " + " AND ".join(where_clauses)

    sql = f"""{asignacion_sql}
    SELECT
        base.operacion,
        base.deuda,
        base.tramo,
        base.contenido,
        base.normalizado,
        base.usuario_gestion,
        base.respuesta_gestion,
        base.gestion_fecha,
        base.telefono,
        COUNT_BIG(1) OVER () AS total_count
    FROM #asig base
    {extra_where}
    ORDER BY
        CASE
            WHEN base.tramo = 'C1' THEN 1
            WHEN base.tramo = 'C2' THEN 2
            ELSE 99
        END,
        base.deuda DESC,
        base.operacion
    OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
    """

    rows = []
    total = 0
    query_params = [*params, offset, page_size]
    for row in run_query_sets(sql, tuple(query_params))[-1]:
        total = int(row.get("total_count") or 0)
        usuario = str(row.get("usuario_gestion") or "").strip().upper()
        rows.append(
            {
                "periodo": periodo,
                "operacion": row.get("operacion"),
                "deuda": float(row.get("deuda") or 0),
                "tramo": row.get("tramo") or "",
                "contenido": int(row.get("contenido") or 0),
                "normalizado": int(row.get("normalizado") or 0),
                "usuario_gestion": usuario,
                "ejecutivo": USER_TO_NAME.get(usuario, usuario or "SIN GESTION"),
                "respuesta_gestion": row.get("respuesta_gestion") or "",
                "gestion_fecha": str(row.get("gestion_fecha") or ""),
                "telefono": row.get("telefono") or "",
            }
        )

    return {
        "data": rows,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def get_tramos_mes(periodo_filtro: str | None, operaciones: list[str]) -> dict[str, str]:
    """Ultimo tramo de mora del mes (hasta la foto consultada) de cada operacion pedida, segun el bench."""
    claves = sorted({str(op or "").strip() for op in operaciones if str(op or "").strip()})
    if not claves:
        return {}
    periodo = _normalize_period(periodo_filtro)
    bench = _bench_source(periodo, _period_version(periodo_filtro))
    tramos: dict[str, str] = {}
    for i in range(0, len(claves), 500):
        lote = claves[i:i + 500]
        filas = run_query(
            f"""
            SELECT operacion, tramo
            FROM (
                SELECT
                    LTRIM(RTRIM(b.fld_OPERACION)) AS operacion,
                    LTRIM(RTRIM(b.fld_TRAMO_MORA)) AS tramo,
                    ROW_NUMBER() OVER (PARTITION BY LTRIM(RTRIM(b.fld_OPERACION)) ORDER BY b.fld_fecha DESC) AS rn
                FROM {bench} b
                WHERE LEFT(b.fld_fecha, 6) = LEFT(?, 6)
                  AND b.fld_fecha <= ?
                  AND ISNULL(b.fld_TRAMO_MORA, '') <> ''
                  AND LTRIM(RTRIM(b.fld_OPERACION)) IN ({",".join("?" * len(lote))})
            ) t
            WHERE rn = 1
            """,
            (periodo, periodo, *lote),
        )
        tramos.update({f["operacion"]: f["tramo"] for f in filas})
    return tramos


def get_detalle_excel(periodo_filtro: str | None) -> list[dict]:
    """Operaciones C1/C2/C3 de la foto que se lleva una ejecutiva. Las FPD (fpd = 1) van marcadas y no suman al aporte."""
    periodo = _normalize_period(periodo_filtro)
    asignacion_sql, params = _asignacion_sql(periodo, _period_version(periodo_filtro))
    usuarios = ", ".join(f"'{user}'" for user in usuarios_del_mes(periodo))
    sql = f"""{asignacion_sql}
    SELECT
        a.usuario_gestion,
        a.operacion,
        a.rut,
        a.tramo,
        a.fpd,
        a.deuda,
        a.monto_contenido,
        a.contenido,
        a.normalizado,
        a.respuesta_gestion,
        a.gestion_fecha,
        a.telefono
    FROM #asig a
    WHERE a.usuario_gestion IN ({usuarios})
      AND a.tramo IN ('C1', 'C2', 'C3')
    """
    rows = run_query_sets(sql, tuple(params))[-1]
    for row in rows:
        row["ejecutivo"] = USER_TO_NAME[str(row["usuario_gestion"]).strip().upper()]
    return rows
