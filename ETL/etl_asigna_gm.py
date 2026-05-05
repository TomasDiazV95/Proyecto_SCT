import os
import re
from decimal import Decimal
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

DEFAULT_EXCEL_PATH = ""
EXCEL_PATH = os.getenv("ASIG_GM_EXCEL_PATH", DEFAULT_EXCEL_PATH).strip()
GM_FOLDER = Path(r"C:\Users\PC del Marrón\Desktop\Paso")
GM_PATTERN = "*AllocationReport*.xlsx"

TABLE = "dbo.tmp_asig_GM"
BATCH_SIZE = 200
NUMERIC_TARGET_COLS = {
    "POS/CURR. ACC. BAL.*",
    "EMI",
    "TOTAL AMOUNT DUE",
    "TOTAL PAST DUE",
}


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
    for d in preferred:
        if d in available:
            return d
    raise RuntimeError(f"No hay driver ODBC para SQL Server. Drivers encontrados: {available}")


def connect() -> pyodbc.Connection:
    driver = pick_driver()
    print(f"ODBC driver usado: {driver}")

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


def normalize_excel_col(col: str) -> str:
    return str(col).strip()


def normalize_for_match(col: str) -> str:
    s = normalize_excel_col(col).upper()
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def is_numeric_target(col: str) -> bool:
    return normalize_for_match(col) in NUMERIC_TARGET_COLS


def sql_type_for(col: str) -> str:
    return "DECIMAL(38,0) NULL" if is_numeric_target(col) else "NVARCHAR(MAX) NULL"


def clean_numeric_to_str(value):
    if value is None or value is pd.NA:
        return None

    s = str(value).strip()
    if s == "" or s.lower() == "nan":
        return None

    s = re.sub(r"[^0-9,\.\-]", "", s)
    if s in ("", "-", ".", ","):
        return None

    s = s.replace(",", "")

    try:
        d = Decimal(s)
    except Exception:
        return None

    return str(int(d))


def mapear_rango(queue_value):
    if pd.isna(queue_value):
        return "0"

    bucket = str(queue_value).strip()
    if bucket == "":
        return "0"

    if "Q_91_150_ALL" in bucket:
        return "91 a 150"
    if "Q_DPD1_5" in bucket:
        return "6 a 30"
    if "Q_DPD31_60" in bucket:
        return "31 a 60"
    if "Q_DPD6_30" in bucket or "LEA_6_45" in bucket:
        return "6 a 30"
    if "Q_DPD61_90" in bucket:
        return "61 a 90"
    return "0"


def read_excel(path: str) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"No existe el Excel en: {path}")

    raw = p.read_bytes()
    df = pd.read_excel(BytesIO(raw), sheet_name=0, dtype=str, engine="openpyxl")

    df.columns = [normalize_excel_col(c) for c in df.columns]

    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].map(lambda v: v.replace("\x00", "") if isinstance(v, str) else v)

    queue_col = next((c for c in df.columns if normalize_for_match(c) == "QUEUE"), None)
    if queue_col is None:
        df["fld_bucket"] = "0"
    else:
        df["fld_bucket"] = df[queue_col].map(mapear_rango)

    df = df.where(pd.notnull(df), None)
    return df


def get_latest_gm_file(folder: Path, pattern: str) -> str:
    if not folder.exists():
        raise FileNotFoundError(f"La carpeta no existe: {folder}")

    files = [p for p in folder.glob(pattern) if not p.name.startswith("~$")]
    if not files:
        raise FileNotFoundError(
            f"No se encontro ningun archivo que cumpla el patron '{pattern}' en {folder}"
        )

    latest_file = max(files, key=lambda f: f.stat().st_mtime)
    return str(latest_file)


def ensure_table_and_columns(df: pd.DataFrame):
    excel_cols = [normalize_excel_col(c) for c in df.columns]
    base_cols = [c for c in excel_cols if c != "fld_bucket"]

    with connect() as cn:
        cur = cn.cursor()

        cur.execute(
            f"""
            IF OBJECT_ID('{TABLE}', 'U') IS NULL
            BEGIN
                CREATE TABLE {TABLE} (
                    id_tmp_asig_gm BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                    fecha_carga DATE NOT NULL CONSTRAINT DF_tmp_asig_GM_fecha_carga DEFAULT (CONVERT(date, GETDATE())),
                    ts_carga DATETIME2(0) NOT NULL CONSTRAINT DF_tmp_asig_GM_ts_carga DEFAULT (SYSDATETIME()),
                    source_file NVARCHAR(260) NULL
                );
                CREATE INDEX IX_tmp_asig_GM_fecha_carga ON {TABLE}(fecha_carga);
            END
            """
        )
        cn.commit()

        schema, table_name = TABLE.split(".")
        schema = schema.replace("[", "").replace("]", "")
        table_name = table_name.replace("[", "").replace("]", "")

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
        existing = {row[0] for row in cur.fetchall()}

        if "bucket" in existing:
            cur.execute(f"ALTER TABLE {TABLE} DROP COLUMN {sql_ident('bucket')};")
            cn.commit()
            existing.remove("bucket")

        alters = []
        for original in base_cols:
            fld = f"fld_{original}"
            if fld not in existing:
                alters.append(f"ALTER TABLE {TABLE} ADD {sql_ident(fld)} {sql_type_for(original)};")

        if "fld_bucket" not in existing:
            alters.append(f"ALTER TABLE {TABLE} ADD {sql_ident('fld_bucket')} NVARCHAR(50) NULL;")

        if alters:
            print(f"Agregando {len(alters)} columnas nuevas a {TABLE}...")
            for stmt in alters:
                cur.execute(stmt)
            cn.commit()

        for original in excel_cols:
            if is_numeric_target(original):
                cur.execute(
                    f"ALTER TABLE {TABLE} ALTER COLUMN {sql_ident(f'fld_{normalize_excel_col(original)}')} DECIMAL(38,0) NULL;"
                )
        cn.commit()


def insert_append(df: pd.DataFrame, source_file: str):
    excel_cols = [normalize_excel_col(c) for c in df.columns]

    base_cols = [c for c in excel_cols if c != "fld_bucket"]
    fld_cols = [f"fld_{c}" for c in base_cols] + ["fld_bucket"]
    insert_cols = ["source_file"] + fld_cols
    placeholders = ",".join(["?"] * len(insert_cols))

    sql = f"""
    INSERT INTO {TABLE} ({','.join(map(sql_ident, insert_cols))})
    VALUES ({placeholders})
    """

    rows = []
    for row in df.itertuples(index=False, name=None):
        out = [source_file]
        row_values = dict(zip(excel_cols, list(row)))

        for c in base_cols:
            v = row_values.get(c)
            if is_numeric_target(c):
                out.append(clean_numeric_to_str(v))
            else:
                if v is None or v is pd.NA:
                    out.append(None)
                else:
                    vv = str(v)
                    out.append(vv if vv.strip() != "" and vv.lower() != "nan" else None)

        bucket_value = row_values.get("fld_bucket")
        out.append(bucket_value if bucket_value is not None else "0")
        rows.append(tuple(out))

    with connect() as cn:
        cn.autocommit = False
        cur = cn.cursor()
        cur.fast_executemany = False

        inserted = 0
        for i in range(0, len(rows), BATCH_SIZE):
            batch = rows[i : i + BATCH_SIZE]
            try:
                cur.executemany(sql, batch)
                cn.commit()
                inserted += len(batch)
                print(f"OK batch {i + 1}-{i + len(batch)}")
            except pyodbc.Error as e:
                cn.rollback()
                print(f"Error en batch {i + 1}-{i + len(batch)}: {e}")
                for j, r in enumerate(batch):
                    try:
                        cur.execute(sql, r)
                        cn.commit()
                        inserted += 1
                    except pyodbc.Error as e2:
                        cn.rollback()
                        global_idx = i + j
                        print(f"Saltando fila problematica global #{global_idx} (Excel aprox fila {global_idx + 2})")
                        print("Detalle:", e2)
                        continue

    print(f"OK: insertadas {inserted} filas")


def main():
    if EXCEL_PATH:
        excel_file = Path(EXCEL_PATH)
    else:
        auto_path = get_latest_gm_file(GM_FOLDER, GM_PATTERN)
        excel_file = Path(auto_path)
        print(f"Archivo AllocationReport encontrado: {excel_file}")

    if not excel_file.exists():
        raise FileNotFoundError(f"No existe archivo: {excel_file}")

    source_file = excel_file.name
    df = read_excel(str(excel_file))

    print(f"Archivo: {source_file}")
    print(f"Filas: {len(df)} | Columnas: {len(df.columns)}")

    found_numeric = [c for c in df.columns if is_numeric_target(c)]
    print("Columnas numericas detectadas:", found_numeric if found_numeric else "ninguna")

    ensure_table_and_columns(df)
    insert_append(df, source_file)


if __name__ == "__main__":
    main()
