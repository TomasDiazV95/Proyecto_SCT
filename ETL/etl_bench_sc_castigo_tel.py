"""Carga el bench de castigo telefonia (SC Piloto) en dbo.tmp_bench_SC_Castigo_tel.

    YYYYMMDD_PHOENIX (TELEFONIA)_BENCH_CASTIGO.XLSX  (carpeta EXTRAS del visor)

Misma estructura y logica que etl_bench_sc_castigo.py (columnas tipadas, recarga y pre-cierre con
bench_recarga). Queda en la misma carpeta que el castigo de terreno: aqui solo se toman los archivos
con TELEFONIA en el nombre (y el ETL de terreno los ignora).
"""

import os
from pathlib import Path

import corregir_nombres
from etl_bench_sc_castigo import cargar_archivo, get_input_excel_paths, parse_sheet_name, require_env

BENCH_FOLDER = Path(require_env("BENCH_SC_CASTIGO_FOLDER"))
# Mismo default que DESCARGAS/descarga_SCT.py.
BENCH_PATTERN = (
    os.getenv("BENCH_SC_CASTIGO_TEL_PATTERN", "").strip()
    or "*PHOENIX (TELEFONIA)_BENCH_CASTIGO*.xlsx"
)
SHEET_NAME = parse_sheet_name(os.getenv("BENCH_SC_CASTIGO_TEL_SHEET_NAME", "0"))

TABLE = "dbo.tmp_bench_SC_Castigo_tel"


def main() -> None:
    for excel_path in get_input_excel_paths(BENCH_FOLDER, BENCH_PATTERN, telefonia=True):
        cargar_archivo(excel_path, TABLE, SHEET_NAME)
    # Los archivos pueden traer nombres de ejecutivos mal escritos: se corrigen segun la nomina.
    corregir_nombres.corregir_tras_carga()


if __name__ == "__main__":
    main()
