"""Funciones auxiliares que estaban copiadas, iguales, en varios ETL.

Cada script las importa con su nombre de siempre (`from etl_comun import ...`); funciona al correr
`python ETL\\<script>.py` porque la carpeta del script queda en sys.path (igual que data_cleaners.py).
La conexion (pick_driver/connect) se mantiene en cada script: depende de sus propias variables.
"""
from __future__ import annotations

import os
from pathlib import Path

import pyodbc
from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[1]


def load_env_files() -> None:
    """Carga el .env de la raiz del repo y luego el de ETL/."""
    load_dotenv(ROOT_DIR / ".env")
    load_dotenv(ROOT_DIR / "ETL" / ".env")


def load_env_raiz() -> None:
    """Carga solo el .env de la raiz del repo (lo que usan los ETL de bench)."""
    load_dotenv(ROOT_DIR / ".env")


def require_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or not str(value).strip():
        raise RuntimeError(f"Falta definir {name} en .env")
    return str(value).strip()


def sql_ident(name: str) -> str:
    return "[" + str(name).replace("]", "]]" ) + "]"


# Conexion SQL Server que lee las variables al conectar (usada por recarga_gest_crm_mes y carga_fpd_temprana).
def sqlserver() -> pyodbc.Connection:
    faltan = [n for n in ("DB_SERVER", "DB_NAME", "DB_USER", "DB_PASSWORD") if not os.getenv(n)]
    if faltan:
        raise RuntimeError("Faltan variables en .env: " + ", ".join(faltan))
    disponibles = pyodbc.drivers()
    driver = next(
        (d for d in (os.getenv("DB_DRIVER"), "ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server", "SQL Server")
         if d and d in disponibles),
        None,
    )
    if not driver:
        raise RuntimeError(f"No hay driver ODBC para SQL Server. Drivers encontrados: {disponibles}")
    return pyodbc.connect(
        f"Driver={{{driver}}};Server={os.getenv('DB_SERVER')};Database={os.getenv('DB_NAME')};"
        f"UID={os.getenv('DB_USER')};PWD={os.getenv('DB_PASSWORD')};TrustServerCertificate=yes;",
        autocommit=False,
    )
