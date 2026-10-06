from __future__ import annotations

from datetime import date, datetime, timedelta

from database import run_query
from feriados_chile import es_habil


DEFAULT_EXECUTIVE = "PHOENIX"
# Cartera Itau Castigo en el CRM de gestiones (dbo.tmp_GEST_CRM).
CRM_CARTERA = 522
DIAS_HABILES_COBERTURA = 4
GESTOR_PHOENIX = "PHOENIX"


def _clean_text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _parse_fecha_carga(value: str | None) -> str:
    text = _clean_text(value)
    if not text:
        rows = run_query(
            """
            SELECT TOP 1 CONVERT(char(10), fecha_carga, 126) AS fecha_carga
            FROM dbo.recup_itau_castigo
            WHERE fecha_carga IS NOT NULL
            GROUP BY fecha_carga
            ORDER BY fecha_carga DESC
            """
        )
        if not rows or not rows[0].get("fecha_carga"):
            raise RuntimeError("No hay fechas de carga disponibles para Itaú Castigo")
        return str(rows[0]["fecha_carga"])

    if len(text) >= 10:
        text = text[:10]

    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass

    raise RuntimeError(f"Fecha de carga invalida: {value}")


def _recup_source_file(fecha_carga: str) -> str:
    # Hay dias con dos cargas del recupero: se usa solo el ultimo archivo, igual que el KPI operacional.
    rows = run_query(
        """
        SELECT TOP 1 source_file
        FROM dbo.recup_itau_castigo
        WHERE fecha_carga = ?
        GROUP BY source_file
        ORDER BY MAX(ts_carga) DESC
        """,
        (fecha_carga,),
    )
    return _clean_text(rows[0].get("source_file")) if rows else ""


def _contencion_cruce_fecha(periodo: str, fecha_carga: str) -> str | None:
    # Ultima contencion de Itau Vencida del mes cargada hasta la fecha consultada.
    rows = run_query(
        """
        SELECT CONVERT(char(10), MAX(fecha_carga), 126) AS fecha_carga
        FROM dbo.contencion_itau_vencida
        WHERE GESTOR = ?
          AND fecha_carga >= ?
          AND fecha_carga <= ?
        """,
        (GESTOR_PHOENIX, periodo, fecha_carga),
    )
    return _clean_text(rows[0].get("fecha_carga")) or None if rows else None


def _periodo_from_fecha(fecha_carga: str) -> str:
    parsed = date.fromisoformat(fecha_carga)
    return parsed.replace(day=1).isoformat()

def _dia_habil_del_mes(periodo: str, n: int) -> str:
    """Fecha ISO del n-esimo dia habil del mes del periodo."""
    cursor = date.fromisoformat(periodo)
    habiles = 0
    while True:
        if es_habil(cursor):
            habiles += 1
            if habiles == n:
                return cursor.isoformat()
        cursor += timedelta(days=1)


def _cap(value: float, max_value: float = 1.3) -> float:
    return max(0.0, min(value, max_value))

def _safe_div(num: float, den: float) -> float:
    if den is None or den == 0:
        return 0.0
    return num / den


def _cobrador_sql(expr: str) -> str:
    # El cobrador viene con distinta capitalizacion segun el archivo ('Phoenix MCV', 'Phoenix Mcv').
    return (
        f"CASE UPPER(LTRIM(RTRIM({expr}))) "
        "WHEN 'PHOENIX' THEN 'Phoenix' WHEN 'PHOENIX MCV' THEN 'Phoenix MCV' "
        f"ELSE LTRIM(RTRIM({expr})) END"
    )


def _base_filters(filters: dict, alias: str = "d") -> tuple[str, list]:
    clauses: list[str] = []
    params: list = []

    ejecutivo = _clean_text(filters.get("ejecutivo"))
    if ejecutivo:
        clauses.append(f"UPPER(LTRIM(RTRIM({alias}.Ejecutivo))) = UPPER(LTRIM(RTRIM(?)))")
        params.append(ejecutivo)

    if not clauses:
        return "", params

    return " AND " + " AND ".join(clauses), params


def get_filter_values(fecha_carga: str | None = None) -> dict:
    fechas_carga = [
        r["fecha_carga"]
        for r in run_query(
            """
            SELECT DISTINCT CONVERT(char(10), fecha_carga, 126) AS fecha_carga
            FROM dbo.recup_itau_castigo
            WHERE fecha_carga IS NOT NULL
            ORDER BY fecha_carga DESC
            """
        )
        if r.get("fecha_carga")
    ]

    ejecutivos = [
        r["ejecutivo"]
        for r in run_query(
            f"""
            SELECT DISTINCT LTRIM(RTRIM(ISNULL(c.ejecutivo, 'PHOENIX'))) AS ejecutivo
            FROM dbo.recup_itau_castigo base
            LEFT JOIN dbo.tmp_carterizado_ITAU_CASTIGO c
                ON base.RUT = c.rut
               AND c.mes_carterizado = DATEFROMPARTS(YEAR(base.fecha_carga), MONTH(base.fecha_carga), 1)
            WHERE LTRIM(RTRIM(ISNULL(c.ejecutivo, 'PHOENIX'))) <> ''
              {"AND base.fecha_carga = ?" if fecha_carga else ""}
            ORDER BY ejecutivo
            """,
            (_parse_fecha_carga(fecha_carga),) if fecha_carga else (),
        )
        if r.get("ejecutivo")
    ]

    return {
        "fechas_carga": fechas_carga,
        "ejecutivos": ejecutivos,
        "productos": ["Phoenix", "Phoenix MCV"],
    }


def get_general(filters: dict) -> dict:
    fecha_carga = _parse_fecha_carga(filters.get("fecha_carga"))
    periodo = _periodo_from_fecha(fecha_carga)
    filter_sql, filter_params = _base_filters(filters, "k")

    # Phoenix y Phoenix MCV se separan por el cobrador de cada RUT segun la asignacion (COBRADOR_VISTA).
    # Cada ejecutivo pertenece a un solo cobrador: aquel donde tiene mas RUT. Los RUT que tiene carterizados
    # en el otro cobrador, y los no carterizados, se suman a la fila grupal PHOENIX de su cobrador, asi el
    # total de cada pestaña calza con la asignacion.
    sql = f"""
    WITH asig AS (
        -- Efectividad sobre lo asignado: base = asignacion del mes, cruzada por RUT con el recupero y el carterizado.
        SELECT
            RUT,
            MAX({_cobrador_sql("COBRADOR_VISTA")}) AS Cobrador,
            SUM(COALESCE(CAST(SDO_CAST_ACTUAL AS float), 0)) AS Monto_Asignado
        FROM dbo.tmp_itau_castigo_asignacion
        WHERE PERIODO = ?
          AND RUT IS NOT NULL
          AND UPPER(LTRIM(RTRIM(COBRADOR_VISTA))) IN ('PHOENIX', 'PHOENIX MCV')
        GROUP BY RUT
    ), rut_cob AS (
        -- Manda el cobrador de la asignacion; el del recupero solo se usa si el RUT no esta asignado.
        SELECT RUT, Cobrador FROM asig
        UNION ALL
        SELECT
            r.RUT,
            MAX({_cobrador_sql("r.COBRADOR_DES")}) AS Cobrador
        FROM dbo.recup_itau_castigo r
        WHERE r.fecha_carga = ?
          AND r.source_file = ?
          AND NOT EXISTS (SELECT 1 FROM asig a WHERE a.RUT = r.RUT)
        GROUP BY r.RUT
    ), rut_cart AS (
        SELECT
            rc.RUT,
            rc.Cobrador,
            c.ejecutivo AS Ejecutivo_Cart
        FROM rut_cob rc
        LEFT JOIN dbo.tmp_carterizado_ITAU_CASTIGO c
            ON rc.RUT = c.rut
           AND c.mes_carterizado = ?
    ), hogar AS (
        SELECT
            Ejecutivo_Cart,
            Cobrador,
            ROW_NUMBER() OVER (PARTITION BY Ejecutivo_Cart ORDER BY COUNT(*) DESC, Cobrador) AS rn
        FROM rut_cart
        WHERE Ejecutivo_Cart IS NOT NULL
        GROUP BY Ejecutivo_Cart, Cobrador
    ), rut_ej AS (
        SELECT
            rc.RUT,
            rc.Cobrador,
            CASE WHEN h.Ejecutivo_Cart IS NOT NULL THEN rc.Ejecutivo_Cart ELSE '{DEFAULT_EXECUTIVE}' END AS Ejecutivo
        FROM rut_cart rc
        LEFT JOIN hogar h
            ON h.Ejecutivo_Cart = rc.Ejecutivo_Cart
           AND h.Cobrador = rc.Cobrador
           AND h.rn = 1
    ), agg AS (
        SELECT
            f.Ejecutivo,
            f.Cobrador,
            SUM(COALESCE(CAST(base.MONTO_CASTIGADO AS float), 0)) AS Deuda_Total,
            SUM(COALESCE(CAST(base.RECUPERO AS float), 0)) AS Recupero_Total
        FROM dbo.recup_itau_castigo base
        INNER JOIN rut_ej f
            ON f.RUT = base.RUT
        WHERE base.fecha_carga = ?
          AND base.source_file = ?
        GROUP BY f.Ejecutivo, f.Cobrador
    ), rec_rut AS (
        SELECT
            RUT,
            SUM(COALESCE(CAST(RECUPERO AS float), 0)) AS Recupero
        FROM dbo.recup_itau_castigo
        WHERE fecha_carga = ?
          AND source_file = ?
        GROUP BY RUT
    ), gest AS (
        -- RUT con al menos una gestion telefonica o en terreno hasta el dia habil de corte de la cobertura.
        SELECT DISTINCT TRY_CAST(g.rut AS bigint) AS RUT
        FROM dbo.tmp_GEST_CRM g
        INNER JOIN dbo.kpi_accion_canal ac
            ON ac.valor = UPPER(LTRIM(RTRIM(g.AccionGestion)))
           AND ac.canal IN ('LLAMADA', 'TERRENO')
        WHERE g.cartera = {CRM_CARTERA}
          AND g.GestionFecha >= ?
          AND g.GestionFecha <= ?
    ), asig_ej AS (
        SELECT
            f.Ejecutivo,
            f.Cobrador,
            SUM(a.Monto_Asignado) AS Monto_Asignado,
            SUM(COALESCE(rr.Recupero, 0)) AS Recupero_Asignado,
            COUNT(*) AS Ruts_Asignados,
            SUM(CASE WHEN ge.RUT IS NOT NULL THEN 1 ELSE 0 END) AS Ruts_Gestionados
        FROM asig a
        INNER JOIN rut_ej f
            ON f.RUT = a.RUT
        LEFT JOIN rec_rut rr
            ON rr.RUT = a.RUT
        LEFT JOIN gest ge
            ON ge.RUT = a.RUT
        GROUP BY f.Ejecutivo, f.Cobrador
    ), cruce_op AS (
        -- Contencion cruce vigente: operaciones de la contencion Itau Vencida gestionadas por Phoenix
        -- cuyo canal es cruce vigente. Una fila por operacion aunque el archivo se haya cargado dos veces.
        SELECT
            RUT,
            OPER,
            MAX(COALESCE(CAST(SALDO_INI AS float), 0)) AS Saldo_Ini,
            MAX(COALESCE(CAST(SALDO_CONT AS float), 0)) AS Saldo_Cont
        FROM dbo.contencion_itau_vencida
        WHERE fecha_carga = ?
          AND GESTOR = '{GESTOR_PHOENIX}'
          AND UPPER(CANAL) LIKE '%CRUCE VIGENTE%'
        GROUP BY RUT, OPER
    ), cruce_ej AS (
        -- Solo RUT de la asignacion de castigo; lo que no esta asignado no entra.
        SELECT
            f.Ejecutivo,
            f.Cobrador,
            SUM(x.Saldo_Ini) AS Cruce_Saldo_Ini,
            SUM(x.Saldo_Cont) AS Cruce_Saldo_Cont
        FROM cruce_op x
        INNER JOIN asig a
            ON a.RUT = x.RUT
        INNER JOIN rut_ej f
            ON f.RUT = x.RUT
        GROUP BY f.Ejecutivo, f.Cobrador
    ), llaves AS (
        SELECT Ejecutivo, Cobrador FROM agg
        UNION
        SELECT Ejecutivo, Cobrador FROM asig_ej
    )
    SELECT
        k.Ejecutivo,
        k.Cobrador AS Cobrador_Vista,
        COALESCE(g.Deuda_Total, 0) AS Deuda_Total,
        COALESCE(g.Recupero_Total, 0) AS Recupero_Total,
        COALESCE(ae.Monto_Asignado, 0) AS Monto_Asignado,
        COALESCE(ae.Recupero_Asignado, 0) AS Recupero_Asignado,
        COALESCE(ae.Ruts_Asignados, 0) AS Ruts_Asignados,
        COALESCE(ae.Ruts_Gestionados, 0) AS Ruts_Gestionados,
        COALESCE(ce.Cruce_Saldo_Ini, 0) AS Cruce_Saldo_Ini,
        COALESCE(ce.Cruce_Saldo_Cont, 0) AS Cruce_Saldo_Cont,
        MAX(COALESCE(CAST(me.meta_recupero AS float), CAST(m.meta_recupero AS float), 0)) AS Meta_Recupero,
        CAST(
            COALESCE(g.Recupero_Total, 0)
            / NULLIF(MAX(COALESCE(CAST(me.meta_recupero AS float), CAST(m.meta_recupero AS float), 0)), 0)
        AS DECIMAL(18, 6)) AS Cumplimiento
    FROM llaves k
    LEFT JOIN agg g
        ON g.Ejecutivo = k.Ejecutivo
       AND g.Cobrador = k.Cobrador
    LEFT JOIN dbo.itau_castigo_metas_mensuales m
        ON m.periodo = ?
       AND m.cobrador_des = k.Cobrador
       AND m.activo = 1
    LEFT JOIN dbo.itau_castigo_metas_ejecutivo me
        ON me.periodo = ?
       AND UPPER(LTRIM(RTRIM(me.ejecutivo))) = UPPER(LTRIM(RTRIM(k.Ejecutivo)))
       AND (
            me.cobrador_des IS NULL
            OR UPPER(LTRIM(RTRIM(me.cobrador_des))) = UPPER(LTRIM(RTRIM(k.Cobrador)))
       )
       AND me.activo = 1
    LEFT JOIN asig_ej ae
        ON ae.Ejecutivo = k.Ejecutivo
       AND ae.Cobrador = k.Cobrador
    LEFT JOIN cruce_ej ce
        ON ce.Ejecutivo = k.Ejecutivo
       AND ce.Cobrador = k.Cobrador
    WHERE 1 = 1
    {filter_sql}
    GROUP BY
        k.Ejecutivo,
        k.Cobrador,
        g.Deuda_Total,
        g.Recupero_Total,
        ae.Monto_Asignado,
        ae.Recupero_Asignado,
        ae.Ruts_Asignados,
        ae.Ruts_Gestionados,
        ce.Cruce_Saldo_Ini,
        ce.Cruce_Saldo_Cont
    ORDER BY
        k.Cobrador,
        k.Ejecutivo
    -- Sin esto el optimizador elige nested loops sobre el cruce por RUT y la consulta pasa de <1s a ~50s
    -- en los meses sin carterizado.
    OPTION (HASH JOIN)
    """

    rows = []
    total_deuda = 0.0
    total_recupero = 0.0
    total_meta = 0.0
    total_asignado = 0.0
    total_recupero_asignado = 0.0
    total_ruts_asignados = 0
    total_ruts_gestionados = 0
    periodo_asignacion = periodo[:4] + periodo[5:7]
    corte_cobertura = _dia_habil_del_mes(periodo, DIAS_HABILES_COBERTURA)
    source_file = _recup_source_file(fecha_carga)
    contencion_cruce_fecha = _contencion_cruce_fecha(periodo, fecha_carga)
    total_cruce_ini = 0.0
    total_cruce_cont = 0.0
    query_params = [
        periodo_asignacion,
        fecha_carga, source_file,
        periodo,
        fecha_carga, source_file,
        fecha_carga, source_file,
        periodo, corte_cobertura,
        contencion_cruce_fecha,
        periodo, periodo,
    ] + filter_params
    for row in run_query(sql, tuple(query_params)):
        deuda = float(row.get("Deuda_Total") or 0)
        recupero = float(row.get("Recupero_Total") or 0)
        meta = float(row.get("Meta_Recupero") or 0)
        asignado = float(row.get("Monto_Asignado") or 0)
        recupero_asignado = float(row.get("Recupero_Asignado") or 0)
        ruts_asignados = int(row.get("Ruts_Asignados") or 0)
        ruts_gestionados = int(row.get("Ruts_Gestionados") or 0)
        cruce_ini = float(row.get("Cruce_Saldo_Ini") or 0)
        cruce_cont = float(row.get("Cruce_Saldo_Cont") or 0)
        rows.append(
            {
                "ejecutivo": row.get("Ejecutivo") or DEFAULT_EXECUTIVE,
                "cobrador_vista": row.get("Cobrador_Vista") or "",
                "deuda_total": deuda,
                "recupero_total": recupero,
                "monto_asignado": asignado,
                "recupero_asignado": recupero_asignado,
                "pct_efectividad": _safe_div(recupero_asignado, asignado),
                "ruts_asignados": ruts_asignados,
                "ruts_gestionados": ruts_gestionados,
                "pct_cobertura": _safe_div(ruts_gestionados, ruts_asignados),
                "cruce_saldo_ini": cruce_ini,
                "cruce_saldo_cont": cruce_cont,
                "pct_contencion_cruce": _safe_div(cruce_cont, cruce_ini),
                "meta_recupero": meta,
                "cumplimiento": _cap(float(row.get("Cumplimiento") or 0)),
            }
        )
        total_asignado += asignado
        total_recupero_asignado += recupero_asignado
        total_ruts_asignados += ruts_asignados
        total_ruts_gestionados += ruts_gestionados
        total_cruce_ini += cruce_ini
        total_cruce_cont += cruce_cont
        total_deuda += deuda
        total_recupero += recupero
        total_meta += meta

    return {
        "fecha_carga": fecha_carga,
        "periodo": periodo,
        "corte_cobertura": corte_cobertura,
        "contencion_cruce_fecha": contencion_cruce_fecha,
        "rows": rows,
        "total": {
            "ejecutivo": "Total general",
            "cobrador_vista": "",
            "deuda_total": total_deuda,
            "recupero_total": total_recupero,
            "monto_asignado": total_asignado,
            "recupero_asignado": total_recupero_asignado,
            "pct_efectividad": _safe_div(total_recupero_asignado, total_asignado),
            "ruts_asignados": total_ruts_asignados,
            "ruts_gestionados": total_ruts_gestionados,
            "pct_cobertura": _safe_div(total_ruts_gestionados, total_ruts_asignados),
            "cruce_saldo_ini": total_cruce_ini,
            "cruce_saldo_cont": total_cruce_cont,
            "pct_contencion_cruce": _safe_div(total_cruce_cont, total_cruce_ini),
            "meta_recupero": total_meta,
            "cumplimiento": _cap(_safe_div(total_recupero, total_meta)),
        },
    }


def get_producto(filters: dict) -> dict:
    fecha_carga = _parse_fecha_carga(filters.get("fecha_carga"))
    periodo = _periodo_from_fecha(fecha_carga)
    ejecutivo = _clean_text(filters.get("ejecutivo"))

    filter_sql = ""
    params: list = [periodo, fecha_carga, _recup_source_file(fecha_carga)]
    if ejecutivo:
        filter_sql = f"HAVING UPPER(LTRIM(RTRIM(ISNULL(c.ejecutivo, '{DEFAULT_EXECUTIVE}')))) = UPPER(LTRIM(RTRIM(?)))"
        params.append(ejecutivo)

    sql = f"""
    SELECT
        ISNULL(c.ejecutivo, '{DEFAULT_EXECUTIVE}') AS Ejecutivo,
        SUM(CASE WHEN base.COBRADOR_DES = 'Phoenix' THEN COALESCE(CAST(base.MONTO_CASTIGADO AS float), 0) ELSE 0 END) AS Deuda_Phoenix,
        SUM(CASE WHEN base.COBRADOR_DES = 'Phoenix' THEN COALESCE(CAST(base.RECUPERO AS float), 0) ELSE 0 END) AS Recupero_Phoenix,
        SUM(CASE WHEN base.COBRADOR_DES = 'Phoenix MCV' THEN COALESCE(CAST(base.MONTO_CASTIGADO AS float), 0) ELSE 0 END) AS Deuda_Phoenix_MCV,
        SUM(CASE WHEN base.COBRADOR_DES = 'Phoenix MCV' THEN COALESCE(CAST(base.RECUPERO AS float), 0) ELSE 0 END) AS Recupero_Phoenix_MCV
    FROM dbo.recup_itau_castigo base
    LEFT JOIN dbo.tmp_carterizado_ITAU_CASTIGO c
        ON base.RUT = c.rut
       AND c.mes_carterizado = ?
    WHERE base.fecha_carga = ?
      AND base.source_file = ?
    GROUP BY ISNULL(c.ejecutivo, '{DEFAULT_EXECUTIVE}')
    {filter_sql}
    ORDER BY Ejecutivo
    """

    rows = []
    totals = {
        "deuda_phoenix": 0.0,
        "recupero_phoenix": 0.0,
        "deuda_phoenix_mcv": 0.0,
        "recupero_phoenix_mcv": 0.0,
    }

    for row in run_query(sql, tuple(params)):
        deuda_phoenix = float(row.get("Deuda_Phoenix") or 0)
        recupero_phoenix = float(row.get("Recupero_Phoenix") or 0)
        deuda_phoenix_mcv = float(row.get("Deuda_Phoenix_MCV") or 0)
        recupero_phoenix_mcv = float(row.get("Recupero_Phoenix_MCV") or 0)
        rows.append(
            {
                "ejecutivo": row.get("Ejecutivo") or DEFAULT_EXECUTIVE,
                "deuda_phoenix": deuda_phoenix,
                "recupero_phoenix": recupero_phoenix,
                "pct_recupero_phoenix": _safe_div(recupero_phoenix, deuda_phoenix),
                "deuda_phoenix_mcv": deuda_phoenix_mcv,
                "recupero_phoenix_mcv": recupero_phoenix_mcv,
                "pct_recupero_phoenix_mcv": _safe_div(recupero_phoenix_mcv, deuda_phoenix_mcv),
            }
        )
        totals["deuda_phoenix"] += deuda_phoenix
        totals["recupero_phoenix"] += recupero_phoenix
        totals["deuda_phoenix_mcv"] += deuda_phoenix_mcv
        totals["recupero_phoenix_mcv"] += recupero_phoenix_mcv

    return {
        "fecha_carga": fecha_carga,
        "periodo": periodo,
        "rows": rows,
        "total": {
            "ejecutivo": "Total general",
            **totals,
            "pct_recupero_phoenix": _safe_div(totals["recupero_phoenix"], totals["deuda_phoenix"]),
            "pct_recupero_phoenix_mcv": _safe_div(totals["recupero_phoenix_mcv"], totals["deuda_phoenix_mcv"]),
        },
    }
