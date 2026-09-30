import os
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path

import pandas as pd
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

DEFAULT_FOLDER = Path(r"C:\Users\Analista de Datos\Desktop\ITAU CASTIGO")
ASIGNACION_FOLDER = Path(os.getenv("ASIGNACION_ITAU_CASTIGO_FOLDER") or DEFAULT_FOLDER)
ASIGNACION_FILENAME = os.getenv("ASIGNACION_ITAU_CASTIGO_FILENAME") or "Asignacion_Phoenix.xlsx"
SHEET_NAME = "Asignacion Phoenix"

TABLE = "dbo.tmp_itau_castigo_asignacion"
BATCH_SIZE = 5000

# Columnas con tipo propio; el resto del Excel se guarda como texto.
INTEGER_COLUMNS = {"RUT", "OPERACIONES", "MOB", "ANO_DEL_CASTIGO"}
DECIMAL_COLUMNS = {"SDO_CAST_ACTUAL", "PAGO_TOTAL", "META"}
# FACTOR trae muchos decimales (ej. 0.0016841774...), no se debe redondear a 4.
PRECISE_DECIMAL_COLUMNS = {"FACTOR"}
DATE_COLUMNS = {"MAX_FECHA_CAST", "MIN_FECHA_CAST", "FECHA_ASIGNACION"}


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
    text = str(value).replace("\x00", "").replace("\ufeff", "")
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


def clean_date(value: object) -> date | None:
    if value is None or value is pd.NA:
        return None
    if isinstance(value, (pd.Timestamp, datetime)):
        return None if pd.isna(value) else value.date()
    if isinstance(value, date):
        return value
    text = clean_text(value)
    if text is None:
        return None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            pass
    return None


def sql_type_for(column: str) -> str:
    if column in INTEGER_COLUMNS:
        return "DECIMAL(38,0) NULL"
    if column in DECIMAL_COLUMNS:
        return "DECIMAL(38,4) NULL"
    if column in PRECISE_DECIMAL_COLUMNS:
        return "DECIMAL(38,12) NULL"
    if column in DATE_COLUMNS:
        return "DATE NULL"
    if column == "PERIODO":
        return "NVARCHAR(6) NULL"
    return "NVARCHAR(MAX) NULL"


def cleaner_for(column: str):
    if column in INTEGER_COLUMNS or column in DECIMAL_COLUMNS or column in PRECISE_DECIMAL_COLUMNS:
        return clean_decimal
    if column in DATE_COLUMNS:
        return clean_date
    return clean_text


def read_excel(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"No existe el Excel en: {path}")

    raw = path.read_bytes()
    df = pd.read_excel(BytesIO(raw), sheet_name=SHEET_NAME, dtype=object, engine="openpyxl")
    df.columns = [normalize_excel_col(c) for c in df.columns]
    df = df.loc[:, [bool(c) and not c.startswith("UNNAMED:") for c in df.columns]]

    duplicated = df.columns[df.columns.duplicated()].tolist()
    if duplicated:
        raise RuntimeError(f"Columnas duplicadas en el Excel: {duplicated}")
    if "PERIODO" not in df.columns:
        raise RuntimeError(f"La hoja '{SHEET_NAME}' no tiene la columna PERIODO.")

    return df.dropna(how="all")


def resolve_periodo(df: pd.DataFrame) -> str:
    periodos = sorted({p for p in (clean_text(v) for v in df["PERIODO"]) if p})
    if len(periodos) != 1:
        raise RuntimeError(f"Se esperaba un unico PERIODO en la asignacion y se encontro: {periodos}")
    periodo = periodos[0]
    if not re.fullmatch(r"\d{6}", periodo):
        raise RuntimeError(f"PERIODO invalido en la asignacion: {periodo}. Se esperaba YYYYMM")
    return periodo


def ensure_table(cur: pyodbc.Cursor, excel_columns: list[str]) -> list[str]:
    cur.execute(
        f"""
        IF OBJECT_ID('{TABLE}', 'U') IS NULL
        BEGIN
            CREATE TABLE {TABLE} (
                id_itau_castigo_asignacion BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                fecha_carga DATE NOT NULL CONSTRAINT DF_tmp_itau_castigo_asignacion_fecha_carga DEFAULT (CONVERT(date, GETDATE())),
                ts_carga DATETIME2(0) NOT NULL CONSTRAINT DF_tmp_itau_castigo_asignacion_ts_carga DEFAULT (SYSDATETIME()),
                source_file NVARCHAR(260) NULL,
                [PERIODO] NVARCHAR(6) NULL
            );
            CREATE INDEX IX_tmp_itau_castigo_asignacion_periodo ON {TABLE}([PERIODO]);
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
    excel_path = ASIGNACION_FOLDER / ASIGNACION_FILENAME
    source_file = excel_path.name
    print(f"Archivo asignacion ITAU castigo: {excel_path}")

    df = read_excel(excel_path)
    periodo = resolve_periodo(df)
    print(f"Hoja: {SHEET_NAME} | Periodo: {periodo} | Filas: {len(df)} | Columnas: {len(df.columns)}")

    excel_columns = list(df.columns)
    cleaners = [cleaner_for(col) for col in excel_columns]
    insert_cols = ["source_file"] + excel_columns
    placeholders = ",".join(["?"] * len(insert_cols))
    sql = f"INSERT INTO {TABLE} ({','.join(map(sql_ident, insert_cols))}) VALUES ({placeholders})"

    rows = [
        tuple([source_file] + [clean(value) for clean, value in zip(cleaners, row)])
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
