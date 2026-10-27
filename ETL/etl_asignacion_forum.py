import os
import re
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path

import pandas as pd
import pyodbc
from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[1]


def load_env_files() -> None:
    load_dotenv(ROOT_DIR / ".env")
    load_dotenv(ROOT_DIR / "ETL" / ".env")


load_env_files()

SERVER = os.getenv("DB_SERVER")
DATABASE = os.getenv("DB_NAME")
USER = os.getenv("DB_USER")
PASSWORD = os.getenv("DB_PASSWORD")
DRIVER_ENV = os.getenv("DB_DRIVER")

# Ruta del Excel de asignacion: se puede definir en .env; por defecto el archivo en la raiz del proyecto.
ASIGNACION_FOLDER = (os.getenv("ASIGNACION_FORUM_FOLDER") or "").strip() or str(ROOT_DIR)
ASIGNACION_FILENAME = (os.getenv("ASIGNACION_FORUM_FILENAME") or "").strip() or "ASIGNACION FORUM.xlsx"
SHEET_NAME = "DATA DEMOGRAFICA.csv"

TABLE = "dbo.tmp_asignacion_forum"
BATCH_SIZE = 5000

# Columnas con tipo propio; el resto del Excel se guarda como texto.
# RUT y DV salen de CRUT (ej. 12487164-6); el Excel no trae saldo asignado, los montos son solo dato.
INTEGER_COLUMNS = {"RUT"}
DECIMAL_COLUMNS = {"MONTO_CASTIGO", "MONTO_OFERTA", "OFERTA_CONVENIO"}


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


def clean_text(value: object) -> str | None:
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
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.isoformat()
    text = re.sub(r"\s+", " ", str(value).replace("\x00", "")).strip()
    if not text or text.lower() == "nan":
        return None
    return text


def clean_decimal(value: object) -> Decimal | None:
    text = clean_text(value)
    if text is None:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def split_rut(value: object) -> tuple[str | None, str | None]:
    text = clean_text(value)
    if text is None:
        return None, None
    text = text.replace(".", "").replace(" ", "").upper()
    match = re.fullmatch(r"(\d+)-?([\dK])", text)
    if not match:
        return None, None
    return match.group(1), match.group(2)


def sql_type_for(column: str) -> str:
    if column in INTEGER_COLUMNS:
        return "DECIMAL(38,0) NULL"
    if column in DECIMAL_COLUMNS:
        return "DECIMAL(38,4) NULL"
    if column == "DV":
        return "NVARCHAR(1) NULL"
    return "NVARCHAR(MAX) NULL"


def cleaner_for(column: str):
    if column in INTEGER_COLUMNS or column in DECIMAL_COLUMNS:
        return clean_decimal
    return clean_text


def read_excel(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"No existe el Excel en: {path}")

    raw = path.read_bytes()
    df = pd.read_excel(BytesIO(raw), sheet_name=SHEET_NAME, dtype=object, engine="openpyxl")
    df.columns = [normalize_excel_col(c) for c in df.columns]
    df = df.loc[:, [bool(c) and not c.startswith("UNNAMED:") for c in df.columns]]

    # El archivo trae CONTRATO dos veces (pandas lee la segunda como CONTRATO.1) con el mismo valor.
    df = df.loc[:, [not re.fullmatch(r".+\.\d+", c) for c in df.columns]]

    duplicated = df.columns[df.columns.duplicated()].tolist()
    if duplicated:
        raise RuntimeError(f"Columnas duplicadas en el Excel: {duplicated}")
    for required in ("CONTRATO", "CRUT", "CARTERA"):
        if required not in df.columns:
            raise RuntimeError(f"La hoja '{SHEET_NAME}' no tiene la columna {required}.")

    df = df.dropna(how="all")
    ruts = [split_rut(v) for v in df["CRUT"]]
    df["RUT"] = [r for r, _ in ruts]
    df["DV"] = [dv for _, dv in ruts]
    return df


def resolve_periodo(argv: list[str]) -> str:
    # El Excel no trae periodo: se usa el del argumento (YYYYMM) o el mes de carga.
    periodo = argv[1].strip() if len(argv) > 1 else date.today().strftime("%Y%m")
    if not re.fullmatch(r"\d{4}(0[1-9]|1[0-2])", periodo):
        raise RuntimeError(f"PERIODO invalido: {periodo}. Se esperaba YYYYMM")
    return periodo


def ensure_table(cur: pyodbc.Cursor, excel_columns: list[str]) -> list[str]:
    cur.execute(
        f"""
        IF OBJECT_ID('{TABLE}', 'U') IS NULL
        BEGIN
            CREATE TABLE {TABLE} (
                id_asignacion_forum BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                fecha_carga DATE NOT NULL CONSTRAINT DF_tmp_asignacion_forum_fecha_carga DEFAULT (CONVERT(date, GETDATE())),
                ts_carga DATETIME2(0) NOT NULL CONSTRAINT DF_tmp_asignacion_forum_ts_carga DEFAULT (SYSDATETIME()),
                source_file NVARCHAR(260) NULL,
                [PERIODO] NVARCHAR(6) NULL
            );
            CREATE INDEX IX_tmp_asignacion_forum_periodo ON {TABLE}([PERIODO]);
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
        if column.upper() not in existing:
            cur.execute(f"ALTER TABLE {TABLE} ADD {sql_ident(column)} {sql_type_for(column)};")
            added.append(column)
    return added


def main() -> None:
    excel_path = Path(ASIGNACION_FOLDER) / ASIGNACION_FILENAME
    source_file = excel_path.name
    print(f"Archivo asignacion FORUM: {excel_path}")

    periodo = resolve_periodo(sys.argv)
    df = read_excel(excel_path)
    print(f"Hoja: {SHEET_NAME} | Periodo: {periodo} | Filas: {len(df)} | Columnas: {len(df.columns)}")

    sin_rut = int(df["RUT"].isna().sum())
    if sin_rut:
        print(f"Aviso: {sin_rut} filas con CRUT invalido (quedan fuera del KPI)")

    excel_columns = list(df.columns)
    cleaners = [cleaner_for(col) for col in excel_columns]
    insert_cols = ["source_file", "PERIODO"] + excel_columns
    placeholders = ",".join(["?"] * len(insert_cols))
    sql = f"INSERT INTO {TABLE} ({','.join(map(sql_ident, insert_cols))}) VALUES ({placeholders})"

    rows = [
        tuple([source_file, periodo] + [clean(value) for clean, value in zip(cleaners, row)])
        for row in df.itertuples(index=False, name=None)
    ]

    with connect() as cn:
        cn.autocommit = False
        cur = cn.cursor()

        added = ensure_table(cur, excel_columns)
        cn.commit()
        if added:
            print(f"{TABLE}: columnas agregadas: {len(added)}")

        # Se reemplaza el periodo completo: queda solo la ultima asignacion del mes.
        cur.execute(f"DELETE FROM {TABLE} WHERE [PERIODO] = ?", (periodo,))
        deleted = cur.rowcount

        inserted = 0
        for i in range(0, len(rows), BATCH_SIZE):
            batch = rows[i : i + BATCH_SIZE]
            cur.executemany(sql, batch)
            inserted += len(batch)
            print(f"OK batch {i + 1}-{i + len(batch)}")

        cn.commit()

    print(f"OK: periodo {periodo} reemplazado ({deleted} filas anteriores), insertadas {inserted} filas en {TABLE}")


if __name__ == "__main__":
    main()
