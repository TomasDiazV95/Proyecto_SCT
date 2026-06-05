import os
from pathlib import Path

import pyodbc
from dotenv import load_dotenv


def load_env_files() -> None:
    root_dir = Path(__file__).resolve().parents[2]
    load_dotenv(root_dir / ".env")
    load_dotenv(root_dir / "ETL" / ".env")


def pick_driver() -> str:
    available = list(pyodbc.drivers())
    driver_env = os.getenv("DB_DRIVER")
    preferred = []
    if driver_env:
        preferred.append(driver_env)
    preferred += [
        "ODBC Driver 18 for SQL Server",
        "ODBC Driver 17 for SQL Server",
        "SQL Server",
    ]

    for driver in preferred:
        if driver in available:
            return driver

    raise RuntimeError(f"No hay driver ODBC para SQL Server. Drivers encontrados: {available}")


def get_connection() -> pyodbc.Connection:
    load_env_files()

    driver = pick_driver()
    server = os.getenv("DB_SERVER")
    database = os.getenv("DB_NAME")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    encrypt = os.getenv("DB_ENCRYPT", "no")

    if not all([server, database, user, password]):
        raise RuntimeError("Faltan variables DB_SERVER, DB_NAME, DB_USER o DB_PASSWORD en .env")

    conn_str = (
        f"Driver={{{driver}}};"
        f"Server={server};"
        f"Database={database};"
        f"Uid={user};"
        f"Pwd={password};"
        "TrustServerCertificate=yes;"
        f"Encrypt={encrypt};"
    )
    return pyodbc.connect(conn_str)


def run_query(sql: str, params: tuple = ()) -> list[dict]:
    with get_connection() as cn:
        cur = cn.cursor()
        cur.execute(sql, params)
        columns = [col[0] for col in cur.description]
        rows = cur.fetchall()

    return [dict(zip(columns, row)) for row in rows]
