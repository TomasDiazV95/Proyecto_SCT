"""Ejecuta la carga del KPI Operacional (dbo.sp_kpi_operacional_cargar).

Toda la logica vive en el stored procedure (WEB/backend/sql/007_kpi_operacional.sql);
este script solo lo invoca para poder encadenarlo con los demas ETL.

Uso:
  python etl_kpi_operacional.py                 # mes actual y 3 anteriores (los que compara el dashboard)
  python etl_kpi_operacional.py --periodos 2026-08 2026-09
"""

import argparse
import os
import re
from pathlib import Path

import pyodbc
from dotenv import load_dotenv


def load_env_files() -> None:
    root_dir = Path(__file__).resolve().parents[1]
    load_dotenv(root_dir / ".env")
    load_dotenv(root_dir / "ETL" / ".env")


load_env_files()

SERVER = os.getenv("DB_SERVER")
DATABASE = os.getenv("DB_NAME")
USER = os.getenv("DB_USER")
PASSWORD = os.getenv("DB_PASSWORD")
DRIVER_ENV = os.getenv("DB_DRIVER")


def pick_driver() -> str:
    available = list(pyodbc.drivers())
    preferred = [DRIVER_ENV, "ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server", "SQL Server"]
    for driver in preferred:
        if driver and driver in available:
            return driver
    raise RuntimeError(f"No hay driver ODBC para SQL Server. Drivers encontrados: {available}")


def connect() -> pyodbc.Connection:
    missing = [n for n, v in {"DB_SERVER": SERVER, "DB_NAME": DATABASE, "DB_USER": USER, "DB_PASSWORD": PASSWORD}.items() if not v]
    if missing:
        raise RuntimeError("Faltan variables en .env: " + ", ".join(missing))
    driver = pick_driver()
    base = f"Driver={{{driver}}};Server={SERVER};Database={DATABASE};Uid={USER};Pwd={PASSWORD};TrustServerCertificate=yes;"
    # El driver antiguo "SQL Server" no acepta Encrypt; los ODBC 17/18 prueban con y sin cifrado (como database.py).
    encrypts = [None] if driver == "SQL Server" else [os.getenv("DB_ENCRYPT") or "yes", "no"]
    errors = []
    for encrypt in encrypts:
        try:
            return pyodbc.connect(base + (f"Encrypt={encrypt};" if encrypt else ""))
        except pyodbc.Error as exc:
            errors.append(str(exc))
    raise RuntimeError("No se pudo conectar a SQL Server: " + " | ".join(errors))


def print_results(cur: pyodbc.Cursor) -> None:
    """El SP devuelve por periodo: filas cargadas por paso y valores de contacto sin catalogo."""
    while True:
        if cur.description:
            columns = [c[0] for c in cur.description]
            rows = cur.fetchall()
            if columns and columns[0] == "periodo":
                if rows:
                    print(f"Periodo {rows[0][0]}")
                    print("  " + ", ".join(f"{row[1]}={row[2]}" for row in rows))
            elif rows:
                detalle = ", ".join(f"{row[0]} ({row[1]})" for row in rows[:10])
                print(f"  Advertencia: valores de ContactoGestion sin catalogo (cuentan como SIN CONTACTO): {detalle}")
        if not cur.nextset():
            break


def main() -> None:
    parser = argparse.ArgumentParser(description="Carga KPI Operacional (stored procedure)")
    parser.add_argument("--periodos", nargs="*", help="Periodos YYYY-MM. Por defecto, mes actual y 3 anteriores.")
    args = parser.parse_args()

    for periodo in args.periodos or []:
        if not re.fullmatch(r"\d{4}-\d{2}", periodo):
            raise RuntimeError(f"Periodo invalido: {periodo}. Se esperaba YYYY-MM")

    with connect() as cn:
        cn.autocommit = True
        cur = cn.cursor()
        if args.periodos:
            for periodo in args.periodos:
                cur.execute("EXEC dbo.sp_kpi_operacional_cargar @periodo = ?", periodo)
                print_results(cur)
        else:
            cur.execute("EXEC dbo.sp_kpi_operacional_cargar")
            print_results(cur)


if __name__ == "__main__":
    main()
