import os
import re
from decimal import Decimal
from io import BytesIO
from pathlib import Path

import data_cleaners
import pandas as pd
import pyodbc
from dotenv import load_dotenv

def load_env_files() -> None:
    root_dir = Path(__file__).resolve().parents[1]
    load_dotenv(root_dir / ".env")


load_env_files()


def require_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or not str(value).strip():
        raise RuntimeError(f"Falta definir {name} en .env")
    return str(value).strip()


# ========= DB desde .env =========
SERVER = os.getenv("DB_SERVER")
DATABASE = os.getenv("DB_NAME")
USER = os.getenv("DB_USER")
PASSWORD = os.getenv("DB_PASSWORD")
DRIVER_ENV = os.getenv("DB_DRIVER")

# ========= BENCH MORA TEMPRANA =========

BENCH_FOLDER = Path(require_env("BENCH_TEMP_FOLDER"))
BENCH_PATTERN = require_env("BENCH_TEMP_PATTERN")
SHEET_NAME = require_env("BENCH_TEMP_SHEET_NAME")

TABLE = "dbo.tmp_bench_temp_STC"
NUMERIC_COLS = {"DEUDA_INI", "DEUDA_ACT", "CONTENIDO", "NORMALIZADO"}
BATCH_SIZE = 10000


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


def connect():
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
    return "[" + str(name).replace("]", "]]" ) + "]"


def normalize_excel_col(c: str) -> str:
    return str(c).strip()


def col_is_numeric(col: str) -> bool:
    return normalize_excel_col(col).upper() in NUMERIC_COLS


def sql_type_for(col: str) -> str:
    return "DECIMAL(38,0) NULL" if col_is_numeric(col) else "NVARCHAR(MAX) NULL"


def clean_numeric_to_str(x):
    if x is None or x is pd.NA:
        return None
    s = str(x).strip()
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
    else:
        if "," in s and "." not in s:
            if s.count(",") > 1:
                s = s.replace(",", "")
            else:
                s = s.replace(",", ".")
        if "." in s and "," not in s:
            if s.count(".") > 1:
                s = s.replace(".", "")

    try:
        d = Decimal(s)
    except Exception:
        return None

    return str(int(d))


def read_excel(path: str, sheet: str | None) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"No existe el Excel en: {path}")

    raw = p.read_bytes()
    if sheet:
        df = pd.read_excel(BytesIO(raw), sheet_name=sheet, dtype=str, engine="openpyxl")
    else:
        df = pd.read_excel(BytesIO(raw), sheet_name=0, dtype=str, engine="openpyxl")

    df.columns = [normalize_excel_col(c) for c in df.columns]

    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].map(lambda v: v.replace("\x00", "") if isinstance(v, str) else v)

    df = df.where(pd.notnull(df), None)
    return df


def ensure_table_and_columns(df: pd.DataFrame):
    excel_cols = [normalize_excel_col(c) for c in df.columns]
    fld_cols = [f"fld_{c}" for c in excel_cols]

    with connect() as cn:
        cur = cn.cursor()

        cur.execute(f"""
        IF OBJECT_ID('{TABLE}', 'U') IS NULL
        BEGIN
            CREATE TABLE {TABLE} (
                id_bench_temp_stc BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                fecha_carga  DATE         NOT NULL CONSTRAINT DF_tmp_bench_temp_STC_fecha_carga DEFAULT (CONVERT(date, GETDATE())),
                ts_carga     DATETIME2(0) NOT NULL CONSTRAINT DF_tmp_bench_temp_STC_ts_carga    DEFAULT (SYSDATETIME()),
                source_file  NVARCHAR(260) NULL
            );
            CREATE INDEX IX_tmp_bench_temp_STC_fecha_carga ON {TABLE}(fecha_carga);
        END
        """)
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

        for n in NUMERIC_COLS:
            colname = f"fld_{n}"
            if colname in existing or colname in fld_cols:
                cur.execute(f"ALTER TABLE {TABLE} ALTER COLUMN {sql_ident(colname)} DECIMAL(38,0) NULL;")
        cn.commit()


def insert_append(df: pd.DataFrame, source_file: str):
    excel_cols = [normalize_excel_col(c) for c in df.columns]
    fld_cols = [f"fld_{c}" for c in excel_cols]

    insert_cols = ["source_file"] + fld_cols
    placeholders = ",".join(["?"] * len(insert_cols))

    sql = f"""
    INSERT INTO {TABLE} ({','.join(map(sql_ident, insert_cols))})
    VALUES ({placeholders})
    """

    rows = []
    for row in df.itertuples(index=False, name=None):
        out = [source_file]
        for c, v in zip(excel_cols, row):
            if col_is_numeric(c):
                out.append(clean_numeric_to_str(v))
            else:
                if v is None or v is pd.NA:
                    out.append(None)
                else:
                    vv = str(v)
                    out.append(vv if vv.strip() != "" and vv.lower() != "nan" else None)

        rows.append(tuple(out))

    with connect() as cn:
        cn.autocommit = False
        cur = cn.cursor()
        cur.fast_executemany = True

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


def get_last_source_file() -> str | None:
    try:
        with connect() as cn:
            cur = cn.cursor()
            cur.execute(f"SELECT TOP (1) source_file FROM {TABLE} ORDER BY id_bench_temp_stc DESC")
            row = cur.fetchone()
            if not row:
                return None
            return row[0]
    except pyodbc.Error:
        return None


def should_skip_load(current_source_file: str) -> bool:
    last_source_file = get_last_source_file()
    if last_source_file is None:
        print("No hay carga previa en la tabla; se cargara el archivo actual.")
        return False

    current_norm = str(current_source_file).strip().upper()
    last_norm = str(last_source_file).strip().upper()

    print(f"source_file actual: {current_source_file}")
    print(f"ultimo source_file en BD: {last_source_file}")

    if current_norm == last_norm:
        print("El ultimo source_file coincide con el archivo actual. Se omite la carga.")
        return True

    print("El source_file es distinto al ultimo en BD. Se continuara con la carga.")
    return False


def pick_files_to_process() -> list[Path]:
    files = [p for p in BENCH_FOLDER.glob(BENCH_PATTERN) if not p.name.startswith("~$")]
    files.sort(key=lambda p: p.name)
    return files


def main():
    files = pick_files_to_process()
    if not files:
        available = []
        if BENCH_FOLDER.exists():
            available = [p.name for p in BENCH_FOLDER.glob("*.xlsx") if not p.name.startswith("~$")]
        raise FileNotFoundError(
            f"No se encontraron archivos de BENCH MORA TEMPRANA para procesar en {BENCH_FOLDER} "
            f"con el patrón {BENCH_PATTERN}. Archivos vistos: {available}"
        )

    for excel_file in files:
        if not excel_file.exists():
            print(f"No existe archivo: {excel_file}")
            continue

        source_file = excel_file.name
        if should_skip_load(source_file):
            print(f"Ya cargado, se omite: {source_file}")
            continue

        df = read_excel(str(excel_file), SHEET_NAME)

        print(f"Archivo: {source_file}")
        print(f"Filas: {len(df)} | Columnas: {len(df.columns)}")

        df = data_cleaners.apply_fuzzy_matching_to_cobrador(df, threshold=90)

        found_numeric = [c for c in df.columns if col_is_numeric(c)]
        print("Columnas numericas detectadas:", found_numeric if found_numeric else "ninguna")

        ensure_table_and_columns(df)
        insert_append(df, source_file)


if __name__ == "__main__":
    main()
