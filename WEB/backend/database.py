import functools
import os
import threading
from pathlib import Path

import pyodbc
from dotenv import load_dotenv


_env_cargado = False


def load_env_files() -> None:
    """Carga el .env de la raiz y el de ETL/ (una vez por proceso: load_dotenv no pisa variables ya definidas,
    asi que volver a leerlos en cada conexion no cambiaba nada)."""
    global _env_cargado
    if _env_cargado:
        return
    root_dir = Path(__file__).resolve().parents[2]
    load_dotenv(root_dir / ".env")
    load_dotenv(root_dir / "ETL" / ".env")
    _env_cargado = True


@functools.lru_cache(maxsize=1)
def _drivers_instalados() -> tuple[str, ...]:
    return tuple(pyodbc.drivers())


def pick_driver() -> str:
    candidates = _driver_candidates()
    if candidates:
        return candidates[0]
    raise RuntimeError(f"No hay driver ODBC para SQL Server. Drivers encontrados: {list(_drivers_instalados())}")


def _driver_candidates() -> list[str]:
    available = _drivers_instalados()
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

    server = os.getenv("DB_SERVER")
    database = os.getenv("DB_NAME")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")

    if not all([server, database, user, password]):
        raise RuntimeError("Faltan variables DB_SERVER, DB_NAME, DB_USER o DB_PASSWORD en .env")

    return _connect(server, database, user, password)


def get_judicial_connection() -> pyodbc.Connection:
    """Base de reportes del CRM judicial: otro servidor, solo lectura."""
    load_env_files()

    server = os.getenv("JUDICIAL_DB_SERVER")
    database = os.getenv("JUDICIAL_DB_NAME")
    user = os.getenv("JUDICIAL_DB_USER")
    password = os.getenv("JUDICIAL_DB_PASSWORD")

    if not all([server, database, user, password]):
        raise RuntimeError(
            "Faltan variables JUDICIAL_DB_SERVER, JUDICIAL_DB_NAME, JUDICIAL_DB_USER o JUDICIAL_DB_PASSWORD en .env"
        )

    return _connect(server, database, user, password)


# Combinacion (driver, Encrypt) que ya funciono por servidor: se prueba primero en las conexiones siguientes.
_combinacion_ok: dict[tuple[str, str], tuple[str, str | None]] = {}
_combinacion_lock = threading.Lock()


def _connect(server: str, database: str, user: str, password: str) -> pyodbc.Connection:
    driver = pick_driver()
    errors: list[str] = []
    combinaciones = [(d, e) for d in (_driver_candidates() or [driver]) for e in _encrypt_candidates()]
    with _combinacion_lock:
        recordada = _combinacion_ok.get((server, database))
    if recordada in combinaciones:
        combinaciones.remove(recordada)
        combinaciones.insert(0, recordada)
    for candidate_driver, encrypt in combinaciones:
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
            cn = pyodbc.connect(conn_str)
        except pyodbc.Error as exc:
            errors.append(f"{candidate_driver} / Encrypt={encrypt}: {exc}")
            continue
        with _combinacion_lock:
            _combinacion_ok[(server, database)] = (candidate_driver, encrypt)
        return cn

    raise RuntimeError("No se pudo conectar a SQL Server. Intentos: " + " | ".join(errors))


def run_query(sql: str, params: tuple = ()) -> list[dict]:
    with get_connection() as cn:
        cur = cn.cursor()
        cur.execute(sql, params)
        columns = [col[0] for col in cur.description]
        rows = cur.fetchall()

    return [dict(zip(columns, row)) for row in rows]


def run_query_judicial(sql: str, params: tuple = ()) -> list[dict]:
    with get_judicial_connection() as cn:
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
