from __future__ import annotations

import re
from datetime import datetime

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


def _parse_period(periodo: str) -> str:
    value = (periodo or "").strip()
    for fmt in ("%Y-%m", "%Y-%m-%d", "%m-%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, fmt).replace(day=1).strftime("%Y-%m-%d")
        except ValueError:
            pass
    raise RuntimeError(f"Formato de periodo no soportado: {periodo}")


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
