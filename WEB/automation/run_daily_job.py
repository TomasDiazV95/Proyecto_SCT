import datetime as dt
import logging
import os
import subprocess
import sys
from pathlib import Path

import pyodbc
from dotenv import load_dotenv

from fetch_from_visor import download_latest_bench


ROOT_DIR = Path(__file__).resolve().parents[2]
ETL_DIR = ROOT_DIR / "ETL"
LOGS_DIR = Path(__file__).resolve().parent / "logs"


def load_env() -> None:
    load_dotenv(ROOT_DIR / ".env")
    load_dotenv(ETL_DIR / ".env")


def setup_logger() -> logging.Logger:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOGS_DIR / f"daily_job_{dt.datetime.now().strftime('%Y%m%d')}.log"

    logger = logging.getLogger("daily_bench_job")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(formatter)
    logger.addHandler(sh)
    return logger


def pick_driver() -> str:
    available = list(pyodbc.drivers())
    preferred = []
    if os.getenv("DB_DRIVER"):
        preferred.append(os.getenv("DB_DRIVER"))
    preferred += ["ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server", "SQL Server"]
    for d in preferred:
        if d in available:
            return d
    raise RuntimeError(f"No hay driver ODBC para SQL Server. Drivers encontrados: {available}")


def connect() -> pyodbc.Connection:
    driver = pick_driver()
    server = os.getenv("DB_SERVER")
    db = os.getenv("DB_NAME")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    if not all([server, db, user, password]):
        raise RuntimeError("Faltan variables de BD en .env")

    conn_str = (
        f"Driver={{{driver}}};"
        f"Server={server};"
        f"Database={db};"
        f"Uid={user};"
        f"Pwd={password};"
        "TrustServerCertificate=yes;"
        "Encrypt=yes;"
    )
    return pyodbc.connect(conn_str)


def build_expected_filename(today: dt.date) -> str:
    suffix = os.getenv("BENCH_FILE_SUFFIX", " - BENCH MORA TARDIA - PHOENIX.xlsx")
    return f"{today.strftime('%Y%m%d')}{suffix}"


def is_weekday(today: dt.date) -> bool:
    return today.weekday() < 5


def already_loaded(source_file: str, table: str = "dbo.tmp_bench_STC") -> bool:
    with connect() as cn:
        cur = cn.cursor()
        cur.execute(f"SELECT COUNT(1) FROM {table} WHERE source_file = ?", (source_file,))
        return (cur.fetchone()[0] or 0) > 0


def run_etl(excel_path: Path, logger: logging.Logger) -> None:
    env = os.environ.copy()
    env["BENCH_EXCEL_PATH"] = str(excel_path)
    env["BENCH_SHEET_NAME"] = os.getenv("BENCH_SHEET_NAME", "PHOENIX")

    etl_script = ETL_DIR / "etl_bench_stc.py"
    logger.info(f"Ejecutando ETL con archivo: {excel_path.name}")
    result = subprocess.run([sys.executable, str(etl_script)], cwd=str(ETL_DIR), env=env)
    if result.returncode != 0:
        raise RuntimeError(f"ETL finalizo con codigo {result.returncode}")


def main() -> int:
    load_env()
    logger = setup_logger()

    today = dt.date.today()
    if not is_weekday(today):
        logger.info("Hoy no es dia habil (lunes-viernes). Proceso omitido.")
        return 0

    expected_name = build_expected_filename(today)
    logger.info(f"Archivo esperado del dia: {expected_name}")

    download_dir = Path(os.getenv("BENCH_DOWNLOAD_DIR", str(ROOT_DIR / "downloads")))
    download_dir.mkdir(parents=True, exist_ok=True)

    downloaded = download_latest_bench(expected_name, download_dir, logger)
    if not downloaded:
        logger.info("No hay archivo nuevo para cargar. Fin del proceso.")
        return 0

    if already_loaded(downloaded.name):
        logger.info(f"El archivo ya estaba cargado en BD: {downloaded.name}. No se reprocesa.")
        return 0

    run_etl(downloaded, logger)
    logger.info("Proceso diario completado correctamente.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        logging.basicConfig(level=logging.ERROR)
        logging.exception("Error en proceso diario: %s", exc)
        raise
