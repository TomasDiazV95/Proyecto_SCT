from __future__ import annotations

from datetime import date

from database import run_query


USER_TO_NAME = {
    "EMUNOZ": "Elizabet Munoz",
    "LROJAS": "Lissette Rojas",
    "MINOSTROZA": "Marilin Inostroza",
    "CVERA": "Carolina Vera",
    "SDUARTE": "Susana Duarte",
    "BMONCADA": "Barbara Canales",
    "SFUENTES": "Sandra Fuentes",
    "MCOLMENARES": "Marlexis Colmenares",
    "PALTAMIRANO": "Paula Altamirano",
    "RCARRASCO": "Rocio Carrasco",
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
    "RCARRASCO",
]


def _normalize_period(periodo: str | None) -> str:
    if periodo:
        value = str(periodo).strip()
        if len(value) >= 10:
            return value[:10]
        return value

    sql = """
    SELECT CONVERT(char(10), MAX(fecha_carga), 126) AS periodo
    FROM dbo.tmp_bench_temp_STC
    """
    rows = run_query(sql)
    return (rows[0].get("periodo") if rows else None) or date.today().isoformat()


def _safe_div(num: float, den: float) -> float:
    if den is None or den == 0:
        return 0.0
    return (num / den) * 100.0


def get_filter_values() -> dict:
    sql_periodos = """
    SELECT DISTINCT CONVERT(char(10), fecha_carga, 126) AS periodo
    FROM dbo.tmp_bench_temp_STC
    WHERE fecha_carga IS NOT NULL
    ORDER BY periodo DESC
    """
    periodos = [r["periodo"] for r in run_query(sql_periodos) if r.get("periodo")]

    ejecutivos = [USER_TO_NAME[u] for u in USER_ORDER]

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

    sql = """
    WITH gestiones AS (
        SELECT
            g.rut,
            g.UsuarioGestion,
            g.ContactoGestion,
            g.RespuestaGestion,
            g.GestionFecha,
            g.GestionHora,
            g.telefono,
            CASE g.RespuestaGestion
                WHEN 'COMPROMISO NORMALIZACION' THEN 1
                WHEN 'COMPROMISO CONTENCION' THEN 2
                WHEN 'COMPROMISO PREPAGO' THEN 3
                WHEN 'COMPROMISO' THEN 4
                WHEN 'COMPROMISO ADP (CUOTA)' THEN 5
                WHEN 'COMPRA DIRECTA EN TRAMITE' THEN 6
                WHEN 'COMPRA DIRECTA CONCRETADA' THEN 7
                WHEN 'COMPRA DIRECTA INTERESADO' THEN 8
                WHEN 'COMPROMISO INTERESADO EN PAC' THEN 9
                WHEN 'COMPROMISO PUT' THEN 10
                WHEN 'COMPROMISO SOLICITA PREPAGO' THEN 11
                WHEN 'DACION' THEN 12
                WHEN 'NOVACION EN TRMITE' THEN 13
                WHEN 'NOVACION' THEN 14
                WHEN 'REFINANCIAMIENTO' THEN 15
                WHEN 'RECONDUCCION EN TRAMITE' THEN 16
                WHEN 'RECONDUCCION INTERESADO' THEN 17
                WHEN 'NOVACION INTERESADO' THEN 18
                WHEN 'DACION EN TRAMITE' THEN 19
                WHEN 'DACION INTERESADO' THEN 20
                WHEN 'REFINANCIAMIENTO EN TRAMITE' THEN 21
                WHEN 'REFINANCIAMIENTO INTERESADO' THEN 22
                WHEN 'A LA ESPERA DEL DESCUENTO PAC' THEN 23
                WHEN 'RENOVACION EN TRAMITE' THEN 24
                WHEN 'VENTA DIRECTA EN TRAMITE' THEN 25
                WHEN 'VENTA DIRECTA INTERESADO' THEN 26
                WHEN 'RENOVACION INTERESADO' THEN 27
                WHEN 'REGULARIZAR POR SUS PROPIOS MEDIOS' THEN 28
                WHEN 'ADP EN TRAMITE' THEN 29
                WHEN 'ADP INTERESADO' THEN 30
                WHEN 'PAGARE EN TRIBUNALES' THEN 31
                WHEN 'RENOVACION' THEN 32
                WHEN 'CESANTE' THEN 33
                WHEN 'EN TRAMITE CON CONCESIONARIO' THEN 34
                WHEN 'ENFERMEDAD DEUDOR MUCHOS GASTOS MEDICOS' THEN 35
                WHEN 'ENFERMEDAD DEUDOR TERMINAL' THEN 36
                WHEN 'YA PAGO' THEN 37
                WHEN 'NOVACION EN TRAMITE' THEN 38
                WHEN 'PROBLEMA ECONOMICO IMPREVISTO' THEN 39
                WHEN 'PROBLEMA ECONOMICO SUELDO INSUFICIENTE' THEN 40
                WHEN 'PROBLEMAS TECNICOS PARA PAGAR CONSUMER.CL' THEN 41
                WHEN 'PROBLEMAS TECNICOS PARA PAGAR PAC' THEN 42
                WHEN 'SINIESTRO PERDIDA TOTAL' THEN 43
                WHEN 'FALLECIDO' THEN 44
                ELSE 999
            END AS peso_gestion
        FROM dbo.tmp_GEST_CRM g
        WHERE g.cartera = 526
          AND g.GestionFecha BETWEEN DATEFROMPARTS(YEAR(?), MONTH(?), 1) AND EOMONTH(?)
          AND g.ContactoGestion IN ('TITULAR', 'INFORMATIVO')
    ),
    ranking AS (
        SELECT
            *,
            ROW_NUMBER() OVER (
                PARTITION BY rut
                ORDER BY peso_gestion ASC, GestionFecha DESC, GestionHora DESC
            ) AS rn
        FROM gestiones
        WHERE peso_gestion <> 999
    ),
    mejor_gestion AS (
        SELECT rut, UsuarioGestion
        FROM ranking
        WHERE rn = 1
    )
    SELECT
        ISNULL(mg.UsuarioGestion, 'SIN GESTION') AS usuario_gestion,
        SUM(CASE WHEN b.fld_TRAMO_MORA = 'C1' THEN ISNULL(b.fld_DEUDA_INI, 0) ELSE 0 END) AS c1_deuda_asignada,
        SUM(CASE WHEN b.fld_TRAMO_MORA = 'C1' THEN ISNULL(b.fld_CONTENIDO, 0) ELSE 0 END) AS c1_monto_cont,
        SUM(CASE WHEN b.fld_TRAMO_MORA = 'C2' THEN ISNULL(b.fld_DEUDA_INI, 0) ELSE 0 END) AS c2_deuda_asignada,
        SUM(CASE WHEN b.fld_TRAMO_MORA = 'C2' THEN ISNULL(b.fld_CONTENIDO, 0) ELSE 0 END) AS c2_monto_cont,
        SUM(CASE WHEN b.fld_TRAMO_MORA = 'C3' THEN ISNULL(b.fld_DEUDA_INI, 0) ELSE 0 END) AS c3_deuda_asignada,
        SUM(CASE WHEN b.fld_TRAMO_MORA = 'C3' THEN ISNULL(b.fld_CONTENIDO, 0) ELSE 0 END) AS c3_monto_cont,
        SUM(CASE WHEN b.fld_TRAMO_MORA = 'C3' THEN 1 ELSE 0 END) AS c3_casos
    FROM dbo.tmp_bench_temp_STC b
    LEFT JOIN mejor_gestion mg
        ON b.fld_RUT = mg.rut
    WHERE ISNULL(mg.UsuarioGestion, 'SIN GESTION') IN (
        'EMUNOZ',
        'LROJAS',
        'MINOSTROZA',
        'CVERA',
        'SDUARTE',
        'BMONCADA',
        'SFUENTES',
        'MCOLMENARES',
        'PALTAMIRANO',
        'RCARRASCO'
    )
      AND b.fld_TRAMO_MORA IN ('C1', 'C2', 'C3')
      AND b.fecha_carga = ?
    GROUP BY ISNULL(mg.UsuarioGestion, 'SIN GESTION')
    """

    raw_rows = run_query(sql, (periodo, periodo, periodo, periodo))

    sql_c3_base = """
    SELECT COUNT_BIG(1) AS c3_casos_base
    FROM dbo.tmp_bench_temp_STC
    WHERE fecha_carga = ?
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

    where_clauses = []
    params: list = [periodo, periodo, periodo, periodo]

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

    sql = f"""
    WITH gestiones AS (
        SELECT
            g.rut,
            g.UsuarioGestion,
            g.ContactoGestion,
            g.RespuestaGestion,
            g.GestionFecha,
            g.GestionHora,
            g.telefono,
            CASE g.RespuestaGestion
                WHEN 'COMPROMISO NORMALIZACION' THEN 1
                WHEN 'COMPROMISO CONTENCION' THEN 2
                WHEN 'COMPROMISO PREPAGO' THEN 3
                WHEN 'COMPROMISO' THEN 4
                WHEN 'COMPROMISO ADP (CUOTA)' THEN 5
                WHEN 'COMPRA DIRECTA EN TRAMITE' THEN 6
                WHEN 'COMPRA DIRECTA CONCRETADA' THEN 7
                WHEN 'COMPRA DIRECTA INTERESADO' THEN 8
                WHEN 'COMPROMISO INTERESADO EN PAC' THEN 9
                WHEN 'COMPROMISO PUT' THEN 10
                WHEN 'COMPROMISO SOLICITA PREPAGO' THEN 11
                WHEN 'DACION' THEN 12
                WHEN 'NOVACION EN TRMITE' THEN 13
                WHEN 'NOVACION' THEN 14
                WHEN 'REFINANCIAMIENTO' THEN 15
                WHEN 'RECONDUCCION EN TRAMITE' THEN 16
                WHEN 'RECONDUCCION INTERESADO' THEN 17
                WHEN 'NOVACION INTERESADO' THEN 18
                WHEN 'DACION EN TRAMITE' THEN 19
                WHEN 'DACION INTERESADO' THEN 20
                WHEN 'REFINANCIAMIENTO EN TRAMITE' THEN 21
                WHEN 'REFINANCIAMIENTO INTERESADO' THEN 22
                WHEN 'A LA ESPERA DEL DESCUENTO PAC' THEN 23
                WHEN 'RENOVACION EN TRAMITE' THEN 24
                WHEN 'VENTA DIRECTA EN TRAMITE' THEN 25
                WHEN 'VENTA DIRECTA INTERESADO' THEN 26
                WHEN 'RENOVACION INTERESADO' THEN 27
                WHEN 'REGULARIZAR POR SUS PROPIOS MEDIOS' THEN 28
                WHEN 'ADP EN TRAMITE' THEN 29
                WHEN 'ADP INTERESADO' THEN 30
                WHEN 'PAGARE EN TRIBUNALES' THEN 31
                WHEN 'RENOVACION' THEN 32
                WHEN 'CESANTE' THEN 33
                WHEN 'EN TRAMITE CON CONCESIONARIO' THEN 34
                WHEN 'ENFERMEDAD DEUDOR MUCHOS GASTOS MEDICOS' THEN 35
                WHEN 'ENFERMEDAD DEUDOR TERMINAL' THEN 36
                WHEN 'FALLECIDO' THEN 37
                WHEN 'YA PAGO' THEN 38
                WHEN 'NOVACION EN TRAMITE' THEN 39
                WHEN 'PROBLEMA ECONOMICO IMPREVISTO' THEN 40
                WHEN 'PROBLEMA ECONOMICO SUELDO INSUFICIENTE' THEN 41
                WHEN 'PROBLEMAS TECNICOS PARA PAGAR CONSUMER.CL' THEN 42
                WHEN 'PROBLEMAS TECNICOS PARA PAGAR PAC' THEN 43
                WHEN 'SINIESTRO PERDIDA TOTAL' THEN 44
                ELSE 999
            END AS peso_gestion
        FROM dbo.tmp_GEST_CRM g
        WHERE g.cartera = 526
          AND g.GestionFecha BETWEEN DATEFROMPARTS(YEAR(?), MONTH(?), 1) AND EOMONTH(?)
          AND g.ContactoGestion IN ('TITULAR', 'INFORMATIVO')
    ),
    ranking AS (
        SELECT
            *,
            ROW_NUMBER() OVER (
                PARTITION BY rut
                ORDER BY peso_gestion ASC, GestionFecha DESC, GestionHora DESC
            ) AS rn
        FROM gestiones
        WHERE peso_gestion <> 999
    ),
    mejor_gestion AS (
        SELECT
            rut,
            UsuarioGestion,
            RespuestaGestion,
            GestionFecha,
            telefono
        FROM ranking
        WHERE rn = 1
    ),
    base AS (
        SELECT
            b.fld_OPERACION AS operacion,
            CAST(ISNULL(b.fld_DEUDA_INI, 0) AS FLOAT) AS deuda,
            LTRIM(RTRIM(b.fld_TRAMO_MORA)) AS tramo,
            CASE WHEN ISNULL(b.fld_CONTENIDO, 0) <> 0 THEN 1 ELSE 0 END AS contenido,
            CASE WHEN ISNULL(b.fld_NORMALIZADO, 0) <> 0 THEN 1 ELSE 0 END AS normalizado,
            mg.UsuarioGestion AS usuario_gestion,
            mg.RespuestaGestion AS respuesta_gestion,
            mg.GestionFecha AS gestion_fecha,
            mg.telefono AS telefono
        FROM dbo.tmp_bench_temp_STC b
        LEFT JOIN mejor_gestion mg
            ON b.fld_RUT = mg.rut
        WHERE b.fecha_carga = ?
    )
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
    FROM base
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
    for row in run_query(sql, tuple(query_params)):
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
