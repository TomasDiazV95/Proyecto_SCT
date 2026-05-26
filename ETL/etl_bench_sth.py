import os
import re
import unicodedata
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
# ========= DB desde .env =========
SERVER = os.getenv("DB_SERVER")
DATABASE = os.getenv("DB_NAME")
USER = os.getenv("DB_USER")
PASSWORD = os.getenv("DB_PASSWORD")
DRIVER_ENV = os.getenv("DB_DRIVER")
# ========= BENCH STH =========
BENCH_FOLDER = Path(r"C:\Users\PC del Marrón\Desktop\Paso")
BENCH_PATTERN = "seguimiento al 22-05 Phoenix.xlsx"
TABLE = "dbo.tmp_bench_STH"
BATCH_SIZE = 2000
NUMERIC_COLS = {
    "CONTENIDO",
    "CICLO",
    "CAMPANA",
    "COMPROMISO",
    "MARCO MORA",
    "MM MONTO",
}
MM_MONTO_COL_KEY = "MM MONTO"
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
    print(f"ODBC driver usado: {driver}")
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
def normalize_col_key(col: str) -> str:
    text = normalize_excel_col(col)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("utf-8")
    text = text.upper()
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text
def col_is_numeric(col: str) -> bool:
    return normalize_col_key(col) in NUMERIC_COLS
def col_is_mm_monto(col: str) -> bool:
    return normalize_col_key(col) == MM_MONTO_COL_KEY
def sql_type_for(col: str) -> str:
    if col_is_mm_monto(col):
        return "DECIMAL(38,2) NULL"
    return "DECIMAL(38,0) NULL" if col_is_numeric(col) else "NVARCHAR(MAX) NULL"
def clean_numeric(value) -> Decimal | None:
    if value is None or value is pd.NA:
        return None
    s = str(value).strip()
    if s == "" or s.lower() == "nan":
        return None
    s = re.sub(r"[^0-9,\.\-]", "", s)
    if s in ("", "-", ".", ","):
        return None
    if "." in s and "," in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "")
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        if s.count(",") > 1:
            s = s.replace(",", "")
        else:
            s = s.replace(",", ".")
    elif "." in s and s.count(".") > 1:
        s = s.replace(".", "")
    try:
        return Decimal(s)
    except Exception:
        return None
def to_sql_numeric(col: str, value):
    number = clean_numeric(value)
    if number is None:
        return None
    if col_is_mm_monto(col):
        return number * Decimal("1000000")
    if col_is_numeric(col):
        return int(number)
    return number
def get_input_excel_path() -> Path:
    if not BENCH_FOLDER.exists():
        raise FileNotFoundError(f"La carpeta no existe: {BENCH_FOLDER}")
    files = [p for p in BENCH_FOLDER.glob(BENCH_PATTERN) if not p.name.startswith("~$")]
    if not files:
        raise FileNotFoundError(
            f"No se encontro ningun archivo que cumpla el patron '{BENCH_PATTERN}' en {BENCH_FOLDER}"
        )
    return max(files, key=lambda p: p.stat().st_mtime)
def read_excel(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"No existe el Excel en: {path}")
    raw = path.read_bytes()
    # Siempre primera hoja
    df = pd.read_excel(BytesIO(raw), sheet_name=0, dtype=str, engine="openpyxl")
    df.columns = [normalize_excel_col(c) for c in df.columns]
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].map(lambda v: v.replace("\x00", "") if isinstance(v, str) else v)
    df = df.where(pd.notnull(df), None)
    return df
def ensure_table_and_columns(df: pd.DataFrame) -> None:
    excel_cols = [normalize_excel_col(c) for c in df.columns]
    fld_cols = [f"fld_{c}" for c in excel_cols]
    with connect() as cn:
        cur = cn.cursor()
        cur.execute(
            f"""
            IF OBJECT_ID('{TABLE}', 'U') IS NULL
            BEGIN
                CREATE TABLE {TABLE} (
                    id_bench_sth BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                    fecha_carga DATE NOT NULL CONSTRAINT DF_tmp_bench_STH_fecha_carga DEFAULT (CONVERT(date, GETDATE())),
                    ts_carga DATETIME2(0) NOT NULL CONSTRAINT DF_tmp_bench_STH_ts_carga DEFAULT (SYSDATETIME()),
                    source_file NVARCHAR(260) NULL
                );
                CREATE INDEX IX_tmp_bench_STH_fecha_carga ON {TABLE}(fecha_carga);
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
        alters = []
        for original, fld in zip(excel_cols, fld_cols):
            if fld not in existing:
                alters.append(f"ALTER TABLE {TABLE} ADD {sql_ident(fld)} {sql_type_for(original)};")
        if alters:
            print(f"Agregando {len(alters)} columnas nuevas a {TABLE}...")
            for stmt in alters:
                cur.execute(stmt)
            cn.commit()
        for original in excel_cols:
            if col_is_mm_monto(original):
                cur.execute(
                    f"ALTER TABLE {TABLE} ALTER COLUMN {sql_ident(f'fld_{original}')} DECIMAL(38,0) NULL;"
                )
            elif col_is_numeric(original):
                cur.execute(
                    f"ALTER TABLE {TABLE} ALTER COLUMN {sql_ident(f'fld_{original}')} DECIMAL(38,0) NULL;"
                )
        cn.commit()
def insert_append(df: pd.DataFrame, source_file: str) -> None:
    excel_cols = [normalize_excel_col(c) for c in df.columns]
    fld_cols = [f"fld_{c}" for c in excel_cols]
    insert_cols = ["source_file"] + fld_cols
    placeholders = ",".join(["?"] * len(insert_cols))
    sql = f"INSERT INTO {TABLE} ({','.join(map(sql_ident, insert_cols))}) VALUES ({placeholders})"
    rows = []
    for row in df.itertuples(index=False, name=None):
        out = [source_file]
        for col, value in zip(excel_cols, row):
            if col_is_numeric(col):
                out.append(to_sql_numeric(col, value))
            else:
                if value is None or value is pd.NA:
                    out.append(None)
                else:
                    text = str(value)
                    out.append(text if text.strip() != "" and text.lower() != "nan" else None)
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
                for j, record in enumerate(batch):
                    try:
                        cur.execute(sql, record)
                        cn.commit()
                        inserted += 1
                    except pyodbc.Error as e2:
                        cn.rollback()
                        global_idx = i + j
                        print(
                            f"Saltando fila problematica global #{global_idx} (Excel aprox fila {global_idx + 2})"
                        )
                        print("Detalle:", e2)
                        continue
    print(f"OK: insertadas {inserted} filas")
def main() -> None:
    excel_path = get_input_excel_path()
    if not excel_path.exists():
        raise FileNotFoundError(f"No existe archivo: {excel_path}")
    df = read_excel(excel_path)
    source_file = excel_path.name
    print(f"Archivo: {source_file}")
    print(f"Filas: {len(df)} | Columnas: {len(df.columns)}")
    found_numeric = [c for c in df.columns if col_is_numeric(c)]
    print("Columnas numericas detectadas:", found_numeric if found_numeric else "ninguna")
    ensure_table_and_columns(df)
    insert_append(df, source_file)
if __name__ == "__main__":
    main()