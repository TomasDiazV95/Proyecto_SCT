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


def _driver_candidates() -> list[str]:
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

    ordered: list[str] = []
    for driver in preferred:
        if driver in available and driver not in ordered:
            ordered.append(driver)
    return ordered


def _encrypt_candidates() -> list[str | None]:
    encrypt_env = os.getenv("DB_ENCRYPT")
    if encrypt_env is not None and str(encrypt_env).strip():
        return [str(encrypt_env).strip()]
    return ["yes", "no", None]


def get_connection() -> pyodbc.Connection:
    load_env_files()

    driver = pick_driver()
    server = os.getenv("DB_SERVER")
    database = os.getenv("DB_NAME")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")

    if not all([server, database, user, password]):
        raise RuntimeError("Faltan variables DB_SERVER, DB_NAME, DB_USER o DB_PASSWORD en .env")

    errors: list[str] = []
    for candidate_driver in _driver_candidates() or [driver]:
        for encrypt in _encrypt_candidates():
            parts = [
                f"Driver={{{candidate_driver}}}",
                f"Server={server}",
                f"Database={database}",
                f"Uid={user}",
                f"Pwd={password}",
                "TrustServerCertificate=yes",
            ]
            if candidate_driver != "SQL Server" and encrypt is not None:
                parts.append(f"Encrypt={encrypt}")

            conn_str = ";".join(parts) + ";"
            try:
                return pyodbc.connect(conn_str)
            except pyodbc.Error as exc:
                errors.append(f"{candidate_driver} / Encrypt={encrypt}: {exc}")

    raise RuntimeError("No se pudo conectar a SQL Server. Intentos: " + " | ".join(errors))


def run_query(sql: str, params: tuple = ()) -> list[dict]:
    with get_connection() as cn:
        cur = cn.cursor()
        cur.execute(sql, params)
        columns = [col[0] for col in cur.description]
        rows = cur.fetchall()

    return [dict(zip(columns, row)) for row in rows]


def run_query_sets(sql: str, params: tuple = ()) -> list[list[dict]]:
    """Execute one SQL batch and return every tabular result set.

    This keeps temporary tables alive on the same SQL Server connection, which
    is useful for dashboard queries that need several projections of one
    filtered universe. Non-tabular statements (for example SET NOCOUNT ON or
    CREATE INDEX) are skipped safely.
    """
    result_sets: list[list[dict]] = []
    with get_connection() as cn:
        cur = cn.cursor()
        cur.execute(sql, params)
        while True:
            if cur.description:
                columns = [col[0] for col in cur.description]
                rows = cur.fetchall()
                result_sets.append([dict(zip(columns, row)) for row in rows])
            if not cur.nextset():
                break
    return result_sets
