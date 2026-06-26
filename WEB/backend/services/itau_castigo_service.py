from __future__ import annotations

from datetime import date, datetime

from database import run_query


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


def _periodo_from_fecha(fecha_carga: str) -> str:
    parsed = date.fromisoformat(fecha_carga)
    return parsed.replace(day=1).isoformat()

def _cap(value: float, max_value: float = 1.3) -> float:
    return max(0.0, min(value, max_value))

def _safe_div(num: float, den: float) -> float:
    if den is None or den == 0:
        return 0.0
    return num / den


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


def get_filter_values() -> dict:
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
            """
            SELECT DISTINCT LTRIM(RTRIM(ISNULL(c.ejecutivo, 'Jorge Lopez'))) AS ejecutivo
            FROM dbo.recup_itau_castigo base
            LEFT JOIN dbo.tmp_carterizado_ITAU_CASTIGO c
                ON base.RUT = c.rut
               AND c.mes_carterizado = DATEFROMPARTS(YEAR(base.fecha_carga), MONTH(base.fecha_carga), 1)
            WHERE LTRIM(RTRIM(ISNULL(c.ejecutivo, 'Jorge Lopez'))) <> ''
            ORDER BY ejecutivo
            """
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
    filter_sql, filter_params = _base_filters(filters, "r")

    sql = f"""
    WITH agg AS (
        SELECT
            ISNULL(c.ejecutivo, 'Jorge Lopez') AS Ejecutivo,
            base.COBRADOR_DES,
            COUNT(*) AS cantidad,
            SUM(COALESCE(CAST(base.MONTO_CASTIGADO AS float), 0)) AS Deuda_Cobrador,
            SUM(COALESCE(CAST(base.RECUPERO AS float), 0)) AS Recupero_Cobrador
        FROM dbo.recup_itau_castigo base
        LEFT JOIN dbo.tmp_carterizado_ITAU_CASTIGO c
            ON base.RUT = c.rut
           AND c.mes_carterizado = ?
        WHERE base.fecha_carga = ?
        GROUP BY
            ISNULL(c.ejecutivo, 'Jorge Lopez'),
            base.COBRADOR_DES
    ), ranked AS (
        SELECT
            Ejecutivo,
            COBRADOR_DES AS Cobrador_Vista,
            SUM(Deuda_Cobrador) OVER (PARTITION BY Ejecutivo) AS Deuda_Total,
            SUM(Recupero_Cobrador) OVER (PARTITION BY Ejecutivo) AS Recupero_Total,
            ROW_NUMBER() OVER (
                PARTITION BY Ejecutivo
                ORDER BY cantidad DESC
            ) AS rn
        FROM agg
    )
    SELECT
        r.Ejecutivo,
        r.Cobrador_Vista,
        r.Deuda_Total,
        r.Recupero_Total,
        MAX(COALESCE(CAST(me.meta_recupero AS float), CAST(m.meta_recupero AS float), 0)) AS Meta_Recupero,
        CAST(
            r.Recupero_Total
            / NULLIF(MAX(COALESCE(CAST(me.meta_recupero AS float), CAST(m.meta_recupero AS float), 0)), 0)
        AS DECIMAL(18, 6)) AS Cumplimiento
    FROM ranked r
    LEFT JOIN dbo.itau_castigo_metas_mensuales m
        ON m.periodo = ?
       AND m.cobrador_des = r.Cobrador_Vista
       AND m.activo = 1
    LEFT JOIN dbo.itau_castigo_metas_ejecutivo me
        ON me.periodo = ?
       AND UPPER(LTRIM(RTRIM(me.ejecutivo))) = UPPER(LTRIM(RTRIM(r.Ejecutivo)))
       AND (
            me.cobrador_des IS NULL
            OR UPPER(LTRIM(RTRIM(me.cobrador_des))) = UPPER(LTRIM(RTRIM(r.Cobrador_Vista)))
       )
       AND me.activo = 1
    WHERE 1 = 1
    {filter_sql}
      AND r.rn = 1
    GROUP BY
        r.Ejecutivo,
        r.Cobrador_Vista,
        r.Deuda_Total,
        r.Recupero_Total
    ORDER BY
        r.Cobrador_Vista,
        r.Ejecutivo
    """

    rows = []
    total_deuda = 0.0
    total_recupero = 0.0
    total_meta = 0.0
    for row in run_query(sql, tuple([periodo, fecha_carga, periodo, periodo] + filter_params)):
        deuda = float(row.get("Deuda_Total") or 0)
        recupero = float(row.get("Recupero_Total") or 0)
        meta = float(row.get("Meta_Recupero") or 0)
        rows.append(
            {
                "ejecutivo": row.get("Ejecutivo") or "Jorge Lopez",
                "cobrador_vista": row.get("Cobrador_Vista") or "",
                "deuda_total": deuda,
                "recupero_total": recupero,
                "pct_efectividad": _safe_div(recupero, deuda),
                "meta_recupero": meta,
                "cumplimiento": _cap(float(row.get("Cumplimiento") or 0)),
            }
        )
        total_deuda += deuda
        total_recupero += recupero
        total_meta += meta

    return {
        "fecha_carga": fecha_carga,
        "periodo": periodo,
        "rows": rows,
        "total": {
            "ejecutivo": "Total general",
            "cobrador_vista": "",
            "deuda_total": total_deuda,
            "recupero_total": total_recupero,
            "pct_efectividad": _safe_div(total_recupero, total_deuda),
            "meta_recupero": total_meta,
            "cumplimiento": _cap(_safe_div(total_recupero, total_meta)),
        },
    }


def get_producto(filters: dict) -> dict:
    fecha_carga = _parse_fecha_carga(filters.get("fecha_carga"))
    periodo = _periodo_from_fecha(fecha_carga)
    ejecutivo = _clean_text(filters.get("ejecutivo"))

    filter_sql = ""
    params: list = [periodo, fecha_carga]
    if ejecutivo:
        filter_sql = "HAVING UPPER(LTRIM(RTRIM(ISNULL(c.ejecutivo, 'Jorge Lopez')))) = UPPER(LTRIM(RTRIM(?)))"
        params.append(ejecutivo)

    sql = f"""
    SELECT
        ISNULL(c.ejecutivo, 'Jorge Lopez') AS Ejecutivo,
        SUM(CASE WHEN base.COBRADOR_DES = 'Phoenix' THEN COALESCE(CAST(base.MONTO_CASTIGADO AS float), 0) ELSE 0 END) AS Deuda_Phoenix,
        SUM(CASE WHEN base.COBRADOR_DES = 'Phoenix' THEN COALESCE(CAST(base.RECUPERO AS float), 0) ELSE 0 END) AS Recupero_Phoenix,
        SUM(CASE WHEN base.COBRADOR_DES = 'Phoenix MCV' THEN COALESCE(CAST(base.MONTO_CASTIGADO AS float), 0) ELSE 0 END) AS Deuda_Phoenix_MCV,
        SUM(CASE WHEN base.COBRADOR_DES = 'Phoenix MCV' THEN COALESCE(CAST(base.RECUPERO AS float), 0) ELSE 0 END) AS Recupero_Phoenix_MCV
    FROM dbo.recup_itau_castigo base
    LEFT JOIN dbo.tmp_carterizado_ITAU_CASTIGO c
        ON base.RUT = c.rut
       AND c.mes_carterizado = ?
    WHERE base.fecha_carga = ?
    GROUP BY ISNULL(c.ejecutivo, 'Jorge Lopez')
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
                "ejecutivo": row.get("Ejecutivo") or "Jorge Lopez",
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
