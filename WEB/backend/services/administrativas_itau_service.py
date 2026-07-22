from __future__ import annotations

import re
from datetime import datetime, timedelta

from database import run_query


CUOTAS_HEADERS = [
    "fecha_carga",
    "ts_carga",
    "source_file",
    "FechaDeProceso",
    "RutCliente",
    "Rut",
    "Dv",
    "NumeroOperacion",
    "NumeroCuota",
    "FechaVencimiento",
    "ValorCuota",
    "capital",
    "InteresesSimple",
    "InteresMora",
    "ImporteOtros",
    "ImporteTotal",
    "Estado",
]

ASIGNACION_HEADERS = [
    "fecha_carga",
    "ts_carga",
    "source_file",
    "Tipo_Asignacion",
    "Segmento",
    "Fecha",
    "Apellido_Cliente",
    "Nombre_Cliente",
    "Numero_Cliente",
    "Rut",
    "Dv",
    "Numero_Cuenta",
    "Producto",
    "Subproducto",
    "Codigo_Subproducto",
    "Fecha_Fin_Asignacion",
    "Escenario_en_Asg",
    "Estrategia_en_Asg",
    "Estado_en_Asg",
    "Escenario_actual",
    "Estrategia_actual",
    "Estado_actual",
    "Dias_Mora",
    "Deuda_Vencida",
    "Deuda_A_Vencer",
    "Monto_Asignado",
    "Monto_Facturado",
    "Estado",
]

CUOTAS_PAGADAS_HEADERS = [
    "FechaProcesoAnterior",
    "FechaProcesoPagoEstimado",
    "Rut",
    "Dv",
    "RutCliente",
    "NumeroOperacion",
    "CuotasPagadas",
    "CuotasPendientes",
    "CuotasTotales",
    "TotalValorCuotaPagado",
    "TotalImportePagado",
    "PrimeraCuotaPagada",
    "UltimaCuotaPagada",
    "DetalleCuotasPagadas",
    "fecha_carga",
    "OPER",
    "FASE_PROY_MAX",
    "GESTOR",
    "SALDO_INI",
    "SALDO_ACT",
    "SALDO_CONT",
    "SALDO_NORMALIZADO_COPIA",
]


def _parse_period(periodo: str) -> str:
    value = (periodo or "").strip()
    for fmt in ("%Y-%m", "%Y-%m-%d", "%m-%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, fmt).replace(day=1).strftime("%Y-%m-%d")
        except ValueError:
            pass
    raise RuntimeError(f"Formato de periodo no soportado: {periodo}")


def _next_month_start(periodo_base: str) -> str:
    dt = datetime.strptime(periodo_base, "%Y-%m-%d")
    next_month = (dt.replace(day=28) + timedelta(days=4)).replace(day=1)
    return next_month.strftime("%Y-%m-%d")


def _period_from_asignacion_source(source_file: str | None) -> str | None:
    match = re.search(r"Asignacion_PHOENIX_(\d{8})", source_file or "", re.IGNORECASE)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y%m%d").strftime("%Y-%m")
    except ValueError:
        return None


def _asignacion_sources_for_period(periodo: str) -> list[str]:
    period_month = _parse_period(periodo)[:7]
    rows = run_query(
        """
        SELECT DISTINCT source_file
        FROM dbo.asignacion_itau_vencida
        WHERE source_file IS NOT NULL AND LTRIM(RTRIM(source_file)) <> ''
        """
    )
    return sorted(
        row["source_file"]
        for row in rows
        if row.get("source_file") and _period_from_asignacion_source(row.get("source_file")) == period_month
    )


def get_periodos() -> dict:
    cuotas_sql = """
    SELECT DISTINCT CONVERT(char(7), FechaDeProceso, 126) AS periodo
    FROM dbo.cuotas_itau_vencida
    WHERE FechaDeProceso IS NOT NULL
    ORDER BY periodo DESC
    """
    asignacion_sources_sql = """
    SELECT DISTINCT source_file
    FROM dbo.asignacion_itau_vencida
    WHERE source_file IS NOT NULL AND LTRIM(RTRIM(source_file)) <> ''
    """
    asignacion_periodos = sorted(
        {
            period
            for row in run_query(asignacion_sources_sql)
            for period in [_period_from_asignacion_source(row.get("source_file"))]
            if period
        },
        reverse=True,
    )
    return {
        "cuotas": [row["periodo"] for row in run_query(cuotas_sql) if row.get("periodo")],
        "asignacion": asignacion_periodos,
    }


def get_cuotas_export_rows(periodo: str) -> tuple[str, list[str], list[dict]]:
    periodo_base = _parse_period(periodo)
    sql = """
    SELECT
        fecha_carga,
        ts_carga,
        source_file,
        FechaDeProceso,
        RutCliente,
        Rut,
        Dv,
        NumeroOperacion,
        NumeroCuota,
        FechaVencimiento,
        ValorCuota,
        capital,
        InteresesSimple,
        InteresMora,
        ImporteOtros,
        ImporteTotal,
        Estado
    FROM dbo.cuotas_itau_vencida
    WHERE FechaDeProceso >= CAST(? AS date)
      AND FechaDeProceso <= EOMONTH(CAST(? AS date))
    ORDER BY FechaDeProceso, Rut, NumeroOperacion, NumeroCuota, id
    """
    return periodo_base[:7], CUOTAS_HEADERS, run_query(sql, (periodo_base, periodo_base))


def get_asignacion_export_rows(periodo: str) -> tuple[str, list[str], list[dict]]:
    periodo_base = _parse_period(periodo)
    source_files = _asignacion_sources_for_period(periodo)
    if not source_files:
        return periodo_base[:7], ASIGNACION_HEADERS, []

    marks = ",".join("?" for _ in source_files)
    sql = """
    SELECT
        fecha_carga,
        ts_carga,
        source_file,
        Tipo_Asignacion,
        Segmento,
        Fecha,
        Apellido_Cliente,
        Nombre_Cliente,
        Numero_Cliente,
        Rut,
        Dv,
        Numero_Cuenta,
        Producto,
        Subproducto,
        Codigo_Subproducto,
        Fecha_Fin_Asignacion,
        Escenario_en_Asg,
        Estrategia_en_Asg,
        Estado_en_Asg,
        Escenario_actual,
        Estrategia_actual,
        Estado_actual,
        Dias_Mora,
        Deuda_Vencida,
        Deuda_A_Vencer,
        Monto_Asignado,
        Monto_Facturado,
        Estado
    FROM dbo.asignacion_itau_vencida
    WHERE source_file IN ({marks})
    ORDER BY source_file, Fecha, Rut, Numero_Cuenta, id
    """.format(marks=marks)
    return periodo_base[:7], ASIGNACION_HEADERS, run_query(sql, tuple(source_files))


def get_cuotas_pagadas_export_rows(periodo: str) -> tuple[str, list[str], list[dict]]:
    periodo_base = _parse_period(periodo)
    periodo_siguiente = _next_month_start(periodo_base)
    sql = """
    ;WITH fechas AS (
        SELECT
            FechaDeProceso,
            LEAD(FechaDeProceso) OVER (
                ORDER BY FechaDeProceso
            ) AS FechaDeProcesoSiguiente
        FROM (
            SELECT DISTINCT
                FechaDeProceso
            FROM dbo.cuotas_itau_vencida
            WHERE FechaDeProceso >= CAST(? AS date)
              AND FechaDeProceso <  CAST(? AS date)
        ) AS f
    ),
    cuotas AS (
        SELECT DISTINCT
            FechaDeProceso,
            Rut,
            Dv,
            RutCliente,
            NumeroOperacion,
            NumeroCuota,
            FechaVencimiento,
            ValorCuota,
            capital,
            InteresesSimple,
            InteresMora,
            ImporteOtros,
            ImporteTotal,
            Estado
        FROM dbo.cuotas_itau_vencida
        WHERE FechaDeProceso >= CAST(? AS date)
          AND FechaDeProceso <  CAST(? AS date)
    ),
    comparacion AS (
        SELECT
            f.FechaDeProceso AS FechaProcesoAnterior,
            f.FechaDeProcesoSiguiente AS FechaProcesoPagoEstimado,
            c.Rut,
            c.Dv,
            c.RutCliente,
            c.NumeroOperacion,
            c.NumeroCuota,
            c.FechaVencimiento,
            c.ValorCuota,
            c.capital,
            c.InteresesSimple,
            c.InteresMora,
            c.ImporteOtros,
            c.ImporteTotal,
            c.Estado
        FROM fechas AS f
        INNER JOIN cuotas AS c
            ON c.FechaDeProceso = f.FechaDeProceso
        LEFT JOIN cuotas AS c_sig
            ON c_sig.FechaDeProceso = f.FechaDeProcesoSiguiente
           AND c_sig.NumeroOperacion = c.NumeroOperacion
           AND c_sig.NumeroCuota = c.NumeroCuota
        WHERE f.FechaDeProcesoSiguiente IS NOT NULL
          AND c_sig.NumeroOperacion IS NULL
    ),
    resumen_pago AS (
        SELECT
            FechaProcesoAnterior,
            FechaProcesoPagoEstimado,
            Rut,
            Dv,
            RutCliente,
            NumeroOperacion,
            COUNT(*) AS CuotasPagadas,
            SUM(ISNULL(ValorCuota, 0)) AS TotalValorCuotaPagado,
            SUM(ISNULL(ImporteTotal, 0)) AS TotalImportePagado,
            MIN(NumeroCuota) AS PrimeraCuotaPagada,
            MAX(NumeroCuota) AS UltimaCuotaPagada,
            STRING_AGG(
                CONVERT(VARCHAR(20), NumeroCuota),
                ', '
            ) AS DetalleCuotasPagadas
        FROM comparacion
        GROUP BY
            FechaProcesoAnterior,
            FechaProcesoPagoEstimado,
            Rut,
            Dv,
            RutCliente,
            NumeroOperacion
    ),
    cuotas_pendientes AS (
        SELECT
            FechaDeProceso,
            NumeroOperacion,
            COUNT(DISTINCT NumeroCuota) AS CuotasPendientes
        FROM cuotas
        GROUP BY
            FechaDeProceso,
            NumeroOperacion
    ),
    base_pagados AS (
        SELECT
            fecha_carga,
            OPER,
            RUT,
            DV1,
            FASE_PROY_MAX,
            GESTOR,
            SALDO_INI,
            SALDO_ACT,
            SALDO_CONT,
            SALDO_NORMALIZADO_COPIA
        FROM (
            SELECT
                *,
                ROW_NUMBER() OVER (
                    PARTITION BY OPER
                    ORDER BY
                        CASE
                            WHEN SALDO_CONT IS NOT NULL THEN 0
                            ELSE 1
                        END,
                        fecha_carga DESC
                ) AS rn
            FROM dbo.contencion_itau_vencida
            WHERE fecha_carga >= CAST(? AS date)
              AND fecha_carga <  CAST(? AS date)
              AND GESTOR = 'PHOENIX'
        ) AS x
        WHERE rn = 1
          AND SALDO_CONT IS NOT NULL
    )
    SELECT
        rp.FechaProcesoAnterior,
        rp.FechaProcesoPagoEstimado,
        rp.Rut,
        rp.Dv,
        rp.RutCliente,
        rp.NumeroOperacion,
        rp.CuotasPagadas,
        ISNULL(cp.CuotasPendientes, 0) AS CuotasPendientes,
        rp.CuotasPagadas
            + ISNULL(cp.CuotasPendientes, 0) AS CuotasTotales,
        rp.TotalValorCuotaPagado,
        rp.TotalImportePagado,
        rp.PrimeraCuotaPagada,
        rp.UltimaCuotaPagada,
        rp.DetalleCuotasPagadas,
        bp.fecha_carga,
        bp.OPER,
        bp.FASE_PROY_MAX,
        bp.GESTOR,
        bp.SALDO_INI,
        bp.SALDO_ACT,
        bp.SALDO_CONT,
        bp.SALDO_NORMALIZADO_COPIA
    FROM resumen_pago AS rp
    LEFT JOIN cuotas_pendientes AS cp
        ON cp.FechaDeProceso = rp.FechaProcesoPagoEstimado
       AND cp.NumeroOperacion = rp.NumeroOperacion
    INNER JOIN base_pagados AS bp
        ON rp.NumeroOperacion = bp.OPER
    ORDER BY
        rp.FechaProcesoPagoEstimado,
        rp.NumeroOperacion
    """
    params = (
        periodo_base,
        periodo_siguiente,
        periodo_base,
        periodo_siguiente,
        periodo_base,
        periodo_siguiente,
    )
    return periodo_base[:7], CUOTAS_PAGADAS_HEADERS, run_query(sql, params)
