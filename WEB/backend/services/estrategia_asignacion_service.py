from __future__ import annotations

import re
import sys
from io import BytesIO
from pathlib import Path

from database import get_connection, run_query

# El reparto vive en ETL/estrategia_asignacion_itau_castigo.py (tambien se corre por consola); aca solo se reutiliza.
ETL_DIR = Path(__file__).resolve().parents[3] / "ETL"
if str(ETL_DIR) not in sys.path:
    sys.path.insert(0, str(ETL_DIR))

from estrategia_asignacion_itau_castigo import generar_estrategia, write_excel  # noqa: E402

COBRADOR = "PHOENIX"
MIN_EJECUTIVOS = 2
MAX_EJECUTIVOS = 50


class ParametroInvalido(ValueError):
    pass


def get_itau_castigo_periodos() -> dict:
    rows = run_query(
        """
        SELECT DISTINCT PERIODO
        FROM dbo.tmp_itau_castigo_asignacion
        WHERE PERIODO IS NOT NULL
          AND UPPER(LTRIM(RTRIM(COBRADOR_VISTA))) = ?
        ORDER BY PERIODO DESC
        """,
        (COBRADOR,),
    )
    return {
        "periodos": [r["PERIODO"] for r in rows],
        "min_ejecutivos": MIN_EJECUTIVOS,
        "max_ejecutivos": MAX_EJECUTIVOS,
    }


def get_itau_castigo_excel(periodo: str, ejecutivos: int) -> tuple[BytesIO, str]:
    periodo = str(periodo or "").strip()
    if not re.fullmatch(r"\d{6}", periodo):
        raise ParametroInvalido("Periodo invalido. Se esperaba YYYYMM")
    if not MIN_EJECUTIVOS <= ejecutivos <= MAX_EJECUTIVOS:
        raise ParametroInvalido(f"La cantidad de ejecutivos debe estar entre {MIN_EJECUTIVOS} y {MAX_EJECUTIVOS}")

    with get_connection() as cn:
        try:
            estrategia = generar_estrategia(cn.cursor(), periodo, ejecutivos, COBRADOR)
        except RuntimeError as exc:
            # Sin asignacion para el periodo o sin RUT sobre el saldo minimo.
            raise ParametroInvalido(str(exc)) from exc

    output = BytesIO()
    write_excel(output, estrategia["salida"])
    output.seek(0)
    return output, f"Estrategia_Asignacion_Itau_Castigo_{periodo}_{ejecutivos}_ejecutivos.xlsx"
