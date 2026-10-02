from __future__ import annotations

from datetime import date

from database import run_query, run_query_sets


USER_TO_NAME = {
    "EMUNOZ": "Elizabet Muñoz",
    "LROJAS": "Lissette Rojas",
    "MINOSTROZA": "Marilin Inostroza",
    "CVERA": "Carolina Vera",
    "SDUARTE": "Susana Duarte",
    "BMONCADA": "Barbara Canales",
    "SFUENTES": "Sandra Fuentes",
    "MCOLMENARES": "Marlexis Colmenares",
    "PALTAMIRANO": "Paula Altamirano",
    "RCALDERON": "Rocio Calderon",
}

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
]

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


def _normalize_period(periodo: str | None) -> str:
    if periodo:
        value = str(periodo).strip()
        if len(value) >= 10:
            return value[:10]
        return value

    sql = """
    SELECT CONVERT(char(10), MAX(fld_fecha), 126) AS periodo
    FROM dbo.tmp_bench_temp_STC
    """
    rows = run_query(sql)
    return (rows[0].get("periodo") if rows else None) or date.today().isoformat()


def _safe_div(num: float, den: float) -> float:
    if den is None or den == 0:
        return 0.0
    return (num / den) * 100.0


def _asignacion_sql(periodo: str) -> tuple[str, list]:
    """Lote SQL que deja en #asig una fila por operacion del bench con la gestion que se la lleva.

    Fecha de pago de una operacion contenida: el ultimo pago informado en el primer bench del mes
    en que aparece contenida (si no es una fecha del mes hasta ese bench, la fecha de ese bench).
    Gana la mejor gestion del RUT hasta la fecha de pago (peso de la respuesta y la mas reciente);
    si no hay, la primera gestion posterior. Asi el contenido no cambia de ejecutivo al llegar
    gestiones nuevas. Las operaciones no contenidas van a la mejor gestion del mes.
    """
    peso_case = "\n".join(
        "                WHEN '{}' THEN {}".format(respuesta.replace("'", "''"), peso)
        for peso, respuesta in enumerate(PESO_RESPUESTA, start=1)
    )
    sql = f"""SET NOCOUNT ON;
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
        FROM dbo.tmp_bench_temp_STC b
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
        CAST(ISNULL(b.fld_DEUDA_INI, 0) AS float) AS deuda,
        CAST(ISNULL(b.fld_CONTENIDO, 0) AS float) AS monto_contenido,
        CASE WHEN ISNULL(b.fld_CONTENIDO, 0) <> 0 THEN 1 ELSE 0 END AS contenido,
        CASE WHEN ISNULL(b.fld_NORMALIZADO, 0) <> 0 THEN 1 ELSE 0 END AS normalizado,
        CASE WHEN ISNULL(b.fld_CONTENIDO, 0) <> 0 THEN p.fecha_pago END AS fecha_pago
    INTO #ops
    FROM dbo.tmp_bench_temp_STC b
    LEFT JOIN #pago p ON p.operacion = b.fld_OPERACION
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
        o.tramo,
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
    return sql, [periodo] * 8


def get_filter_values(periodo: str | None = None) -> dict:
    sql_periodos = """
    SELECT DISTINCT CONVERT(char(10), fld_fecha, 126) AS periodo
    FROM dbo.tmp_bench_temp_STC
    WHERE fld_fecha IS NOT NULL
    ORDER BY periodo DESC
    """
    periodos = [r["periodo"] for r in run_query(sql_periodos) if r.get("periodo")]

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


def get_cycle_view(filters: dict) -> list[dict]:
    periodo = _normalize_period(filters.get("periodo"))
    ejecutivo_filter = str(filters.get("ejecutivo") or "").strip().lower()

    asignacion_sql, params = _asignacion_sql(periodo)
    usuarios = ", ".join(f"'{user}'" for user in USER_ORDER)
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
    GROUP BY a.usuario_gestion
    """

    raw_rows = run_query_sets(sql, tuple(params))[-1]

    sql_c3_base = """
    SELECT COUNT_BIG(1) AS c3_casos_base
    FROM dbo.tmp_bench_temp_STC
    WHERE fld_fecha = ?
      AND UPPER(LTRIM(RTRIM(fld_TRAMO_MORA))) = 'C3'
    """
    c3_base_rows = run_query(sql_c3_base, (periodo,))
    c3_casos_base = int(c3_base_rows[0].get("c3_casos_base") or 0) if c3_base_rows else 0

    c1_total_cont = sum(float(r.get("c1_monto_cont") or 0) for r in raw_rows)
    c2_total_cont = sum(float(r.get("c2_monto_cont") or 0) for r in raw_rows)
    c3_total_cont = sum(float(r.get("c3_monto_cont") or 0) for r in raw_rows)

    rows: list[dict] = []
    for user in USER_ORDER:
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

    asignacion_sql, params = _asignacion_sql(periodo)
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
