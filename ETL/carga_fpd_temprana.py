"""Carga la base FPD de SC Temprana del mes en dbo.tmp_sc_temprana_fpd.

Las operaciones FPD se miden aparte en la productividad de SC Temprana (bloque FPD,
WEB/backend/services/sc_temprana_service.py). Reemplaza las filas del periodo.

Uso:
    python ETL/carga_fpd_temprana.py "BASE FPD SIN CONTACTO CON DIRECCIONES.xlsx" 202610
"""
from __future__ import annotations

import argparse

import pandas as pd

from recarga_gest_crm_mes import sqlserver


TABLE = "dbo.tmp_sc_temprana_fpd"
HOJA = "fpd sin contacto"
COLUMNA = "DDAS_ID_NUMERO_OPERAC"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("excel")
    parser.add_argument("periodo", help="YYYYMM")
    args = parser.parse_args()
    if len(args.periodo) != 6 or not args.periodo.isdigit():
        raise SystemExit("El periodo va como YYYYMM")

    datos = pd.read_excel(args.excel, sheet_name=HOJA, usecols=[COLUMNA], dtype=str)
    operaciones = sorted({op.strip() for op in datos[COLUMNA].dropna() if op.strip()})

    cn = sqlserver()
    cur = cn.cursor()
    cur.execute(f"""
        IF OBJECT_ID('{TABLE}') IS NULL
            CREATE TABLE {TABLE} (
                periodo char(6) NOT NULL,
                operacion varchar(30) NOT NULL,
                CONSTRAINT PK_tmp_sc_temprana_fpd PRIMARY KEY (periodo, operacion)
            )
    """)
    cur.execute(f"DELETE FROM {TABLE} WHERE periodo = ?", args.periodo)
    cur.fast_executemany = True
    cur.executemany(f"INSERT INTO {TABLE} (periodo, operacion) VALUES (?, ?)", [(args.periodo, op) for op in operaciones])
    cn.commit()
    cn.close()
    print(f"{len(operaciones)} operaciones FPD cargadas en {TABLE} para {args.periodo}")


if __name__ == "__main__":
    main()
