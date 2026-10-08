import os
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path

import bench_recarga
import pandas as pd
import pyodbc
from dotenv import load_dotenv


def load_env_files() -> None:
    root_dir = Path(__file__).resolve().parents[1]
    load_dotenv(root_dir / ".env")


load_env_files()


def parse_sheet_name(raw_value: str) -> int | str:
    value = raw_value.strip()
    return int(value) if value.isdigit() else value


SERVER = os.getenv("DB_SERVER")
DATABASE = os.getenv("DB_NAME")
USER = os.getenv("DB_USER")
PASSWORD = os.getenv("DB_PASSWORD")
DRIVER_ENV = os.getenv("DB_DRIVER")

# El bench judicial se descarga (descarga_SCT.py) en la misma carpeta que los demas bench.
_folder = (os.getenv("BENCH_SC_JUDICIAL_FOLDER") or os.getenv("BENCH_SC_CASTIGO_FOLDER") or "").strip()
if not _folder:
    raise RuntimeError("Falta definir BENCH_SC_JUDICIAL_FOLDER o BENCH_SC_CASTIGO_FOLDER en .env")
BENCH_FOLDER = Path(_folder)
BENCH_PATTERN = "*BENCH BENCH JUDICIAL - P&S*.xlsx"
FILE_DATE_PATTERN = re.compile(r"^(\d{8})(?!\d)")
SHEET_NAME = parse_sheet_name(os.getenv("BENCH_SC_JUDICIAL_SHEET_NAME", "0"))

TABLE = "dbo.tmp_bench_SC_judicial"
# Montos y dias de mora se guardan como numero; el resto como texto.
NUMERIC_COLUMNS = {
    "DEUDA_APER",
    "DEUDA_ACT",
    "DIA_MOR_IN",
    "DIA_MOR_AC",
    "CONTENIDO",
    "NORMALIZ",
    "EFEC_RECUP",
    "CURSE_ADP",
    "CAMBIO_EST",
}
BATCH_SIZE = 5000


def pick_driver() -> str:
    available = list(pyodbc.drivers())
    preferred = []
    if DRIVER_ENV:
        preferred.append(DRIVER_ENV)
    preferred += [
        "ODBC Driver 18 for SQL Server",
        "ODBC Driver 17 for SQL Server",
        "SQL Server",
    ]
    for driver in preferred:
        if driver in available:
            return driver
    raise RuntimeError(f"No hay driver ODBC para SQL Server. Drivers encontrados: {available}")


def connect() -> pyodbc.Connection:
    missing = [
        name
        for name, value in {
            "DB_SERVER": SERVER,
            "DB_NAME": DATABASE,
            "DB_USER": USER,
            "DB_PASSWORD": PASSWORD,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError("Faltan variables en .env: " + ", ".join(missing))

    driver = pick_driver()
    conn_str = (
        f"Driver={{{driver}}};"
        f"Server={SERVER};"
        f"Database={DATABASE};"
        f"Uid={USER};"
        f"Pwd={PASSWORD};"
        "TrustServerCertificate=yes;"
        "Encrypt=yes;"
    )
    return pyodbc.connect(conn_str)


def sql_ident(name: str) -> str:
    return "[" + str(name).replace("]", "]]") + "]"


def normalize_excel_col(value: object) -> str:
    text = str(value).replace("\x00", "").replace("﻿", "")
    text = re.sub(r"[\u0000-\u001f\u007f]+", "", text)
    return re.sub(r"\s+", "_", text.strip()).upper()


def clean_value(value: object) -> str | None:
    if value is None or value is pd.NA:
        return None
    if isinstance(value, float):
        if pd.isna(value):
            return None
        # Evita que un entero leido como float quede como "123.0".
        if value.is_integer():
            return str(int(value))
        return str(value)
    if isinstance(value, (pd.Timestamp, datetime)):
        if pd.isna(value):
            return None
        if value.hour == 0 and value.minute == 0 and value.second == 0:
            return value.strftime("%Y-%m-%d")
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.isoformat()
    text = re.sub(r"\s+", " ", str(value).replace("\x00", "")).strip()
    if not text or text.lower() == "nan":
        return None
    return text


def clean_numeric(value: object) -> Decimal | None:
    text = clean_value(value)
    if text is None:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def file_date(path: Path) -> date | None:
    match = FILE_DATE_PATTERN.match(path.name)
    if not match:
        return None
    return datetime.strptime(match.group(1), "%Y%m%d").date()


def get_input_excel_paths() -> list[Path]:
    """Archivos a procesar, del mas antiguo al mas nuevo segun su carga en el visor.

    La descarga deja el bench mas reciente y, los primeros dias del mes, el pre-cierre y el
    cierre del mes anterior (aunque el nombre venga escrito de otra forma). Los ya cargados se omiten.
    """
    if not BENCH_FOLDER.exists():
        raise FileNotFoundError(f"La carpeta no existe: {BENCH_FOLDER}")

    files = [p for p in bench_recarga.archivos_bench(BENCH_FOLDER, BENCH_PATTERN) if file_date(p) is not None]
    if not files:
        raise FileNotFoundError(
            f"No se encontro ningun archivo 'YYYYMMDD - BENCH BENCH JUDICIAL - P&S.xlsx' en {BENCH_FOLDER}"
        )
    return files


def read_excel(path: Path) -> pd.DataFrame:
    raw = path.read_bytes()
    df = pd.read_excel(BytesIO(raw), sheet_name=SHEET_NAME, dtype=object, engine="openpyxl")
    df.columns = [normalize_excel_col(c) for c in df.columns]
    df = df.loc[:, [bool(c) and not c.startswith("UNNAMED:") for c in df.columns]]

    duplicated = df.columns[df.columns.duplicated()].tolist()
    if duplicated:
        raise RuntimeError(f"Columnas duplicadas en el Excel: {duplicated}")
    if not len(df.columns):
        raise RuntimeError(f"El archivo {path.name} no tiene columnas.")

    return df.dropna(how="all")


def ensure_table(cur: pyodbc.Cursor, excel_columns: list[str]) -> list[str]:
    cur.execute(
        f"""
        IF OBJECT_ID('{TABLE}', 'U') IS NULL
        BEGIN
            CREATE TABLE {TABLE} (
                id_bench_sc_judicial BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                fecha_carga DATE NOT NULL CONSTRAINT DF_tmp_bench_SC_judicial_fecha_carga DEFAULT (CONVERT(date, GETDATE())),
                ts_carga DATETIME2(0) NOT NULL CONSTRAINT DF_tmp_bench_SC_judicial_ts_carga DEFAULT (SYSDATETIME()),
                source_file NVARCHAR(260) NULL,
                fecha_archivo DATE NULL
            );
            CREATE INDEX IX_tmp_bench_SC_judicial_fecha_archivo ON {TABLE}(fecha_archivo);
            CREATE INDEX IX_tmp_bench_SC_judicial_source_file ON {TABLE}(source_file);
        END
        """
    )

    schema, table_name = TABLE.split(".")
    cur.execute(
        """
        SELECT c.name
        FROM sys.columns c
        INNER JOIN sys.tables t ON c.object_id = t.object_id
        INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
        WHERE s.name = ? AND t.name = ?
        """,
        (schema, table_name),
    )
    existing = {str(row[0]).upper() for row in cur.fetchall()}

    added = []
    for column in excel_columns:
        column_name = "fld_" + column
        if column_name.upper() not in existing:
            column_type = "DECIMAL(38,2)" if column in NUMERIC_COLUMNS else "NVARCHAR(MAX)"
            cur.execute(f"ALTER TABLE {TABLE} ADD {sql_ident(column_name)} {column_type} NULL;")
            added.append(column_name)
    return added


def insert_rows(cn: pyodbc.Connection, df: pd.DataFrame, source_file: str, fecha_archivo: date) -> int:
    excel_columns = list(df.columns)
    insert_cols = ["source_file", "fecha_archivo"] + ["fld_" + col for col in excel_columns]
    placeholders = ",".join(["?"] * len(insert_cols))
    sql = f"INSERT INTO {TABLE} ({','.join(map(sql_ident, insert_cols))}) VALUES ({placeholders})"

    cleaners = [clean_numeric if col in NUMERIC_COLUMNS else clean_value for col in excel_columns]
    rows = [
        tuple([source_file, fecha_archivo] + [clean(value) for clean, value in zip(cleaners, row)])
        for row in df.itertuples(index=False, name=None)
    ]

    cur = cn.cursor()
    inserted = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        cur.executemany(sql, batch)
        inserted += len(batch)
        print(f"OK batch {i + 1}-{i + len(batch)}")
    return inserted


def main() -> None:
    for excel_path in get_input_excel_paths():
        cargar_archivo(excel_path)


def cargar_archivo(excel_path: Path) -> None:
    source_file = excel_path.name
    fecha_archivo = file_date(excel_path)

    print(f"Archivo SC Judicial: {excel_path}")
    print(f"Fecha archivo: {fecha_archivo}")

    df = read_excel(excel_path)
    print(f"Filas: {len(df)} | Columnas: {len(df.columns)}")

    with connect() as cn:
        cn.autocommit = False
        cur = cn.cursor()

        added = ensure_table(cur, list(df.columns))
        cn.commit()
        if added:
            print(f"{TABLE}: columnas agregadas: {', '.join(added)}")

        # Si el archivo ya esta cargado pero fue resubido al visor, se borran sus filas y se recarga.
        # El archivo de fin de mes conserva la primera carga marcada como pre-cierre (version_carga).
        fecha_visor = bench_recarga.fecha_visor_archivo(excel_path)
        if not bench_recarga.debe_cargar(cur, TABLE, source_file, fecha_visor, conservar_precierre=True):
            return

        inserted = insert_rows(cn, df, source_file, fecha_archivo)
        bench_recarga.registrar_fecha_visor(cur, TABLE, source_file, fecha_visor)
        cn.commit()

    print(f"OK: insertadas {inserted} filas en {TABLE}")


if __name__ == "__main__":
    main()
