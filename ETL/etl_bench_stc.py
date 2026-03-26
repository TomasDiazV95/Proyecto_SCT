import os
import re
import data_cleaners
from pathlib import Path
from io import BytesIO
from decimal import Decimal

import pandas as pd
import pyodbc
from dotenv import load_dotenv

load_dotenv()

# ========= DB desde .env =========
SERVER = os.getenv("DB_SERVER")
DATABASE = os.getenv("DB_NAME")
USER = os.getenv("DB_USER")
PASSWORD = os.getenv("DB_PASSWORD")
DRIVER_ENV = os.getenv("DB_DRIVER")  # opcional

# ========= BENCH (hardcodeado, NO .env) =========
#EXCEL_PATH = "C:\\Users\\PC del Marrón\\Desktop\\Paso\\20260323 - BENCH MORA TARDIA - PHOENIX.xlsx"
EXCEL_PATH = "C:\\Users\\Analista de Datos\\Desktop\\Paso\\20260323 - BENCH MORA TARDIA - PHOENIX.xlsx"
SHEET_NAME = "PHOENIX"

TABLE = "dbo.tmp_bench_STC"
NUMERIC_COLS = {"DEUDA_INI", "DEUDA_ACT", "CONTENIDO", "NORMALIZADO"}
BATCH_SIZE = 200


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
    return "[" + str(name).replace("]", "]]") + "]"


def normalize_excel_col(c: str) -> str:
    return str(c).strip()


def col_is_numeric(col: str) -> bool:
    return normalize_excel_col(col).upper() in NUMERIC_COLS


def sql_type_for(col: str) -> str:
    # Para SQL Server 2016, DECIMAL(38,2) es seguro para montos grandes
    return "DECIMAL(38,2) NULL" if col_is_numeric(col) else "NVARCHAR(MAX) NULL"


def clean_numeric_to_str(x):
    """
    Normaliza número a string con punto decimal (ej: '1234.56').
    Si viene basura -> None.
    """
    if x is None or x is pd.NA:
        return None
    s = str(x).strip()
    if s == "" or s.lower() == "nan":
        return None

    # deja dígitos, punto, coma, signo
    s = re.sub(r"[^0-9,\.\-]", "", s)
    if s in ("", "-", ".", ","):
        return None

    # '.' y ',' -> el último separador es decimal
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

    # valida que sea número
    try:
        Decimal(s)
    except Exception:
        return None

    return s


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

    # limpiar \x00 sin applymap
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

        # 1) crear tabla base si no existe
        cur.execute(f"""
        IF OBJECT_ID('{TABLE}', 'U') IS NULL
        BEGIN
            CREATE TABLE {TABLE} (
                id_bench_stc BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                fecha_carga  DATE        NOT NULL CONSTRAINT DF_tmp_bench_STC_fecha_carga DEFAULT (CONVERT(date, GETDATE())),
                ts_carga     DATETIME2(0) NOT NULL CONSTRAINT DF_tmp_bench_STC_ts_carga    DEFAULT (SYSDATETIME()),
                source_file  NVARCHAR(260) NULL
            );
            CREATE INDEX IX_tmp_bench_STC_fecha_carga ON {TABLE}(fecha_carga);
        END
        """)
        cn.commit()

        # 2) columnas existentes
        schema, table_name = TABLE.split(".")
        schema = schema.replace("[", "").replace("]", "")
        table_name = table_name.replace("[", "").replace("]", "")

        cur.execute("""
            SELECT c.name
            FROM sys.columns c
            INNER JOIN sys.tables t ON c.object_id = t.object_id
            INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
            WHERE s.name = ? AND t.name = ?
        """, (schema, table_name))
        existing = {row[0] for row in cur.fetchall()}

        # 3) agregar columnas faltantes
        alters = []
        for original, fld in zip(excel_cols, fld_cols):
            if fld not in existing:
                alters.append(f"ALTER TABLE {TABLE} ADD {sql_ident(fld)} {sql_type_for(original)};")

        if alters:
            print(f"Agregando {len(alters)} columnas nuevas a {TABLE}...")
            for stmt in alters:
                cur.execute(stmt)
            cn.commit()

        # 4) asegurar que las 4 numéricas queden DECIMAL(38,2)
        for n in NUMERIC_COLS:
            colname = f"fld_{n}"
            if colname in existing or colname in fld_cols:
                cur.execute(f"ALTER TABLE {TABLE} ALTER COLUMN {sql_ident(colname)} DECIMAL(38,2) NULL;")
        cn.commit()


def insert_append(df: pd.DataFrame, source_file: str):
    excel_cols = [normalize_excel_col(c) for c in df.columns]
    fld_cols = [f"fld_{c}" for c in excel_cols]

    insert_cols = ["source_file"] + fld_cols
    placeholders = ",".join(["?"] * len(insert_cols))

    sql = f"""
    INSERT INTO {TABLE} ({",".join(map(sql_ident, insert_cols))})
    VALUES ({placeholders})
    """

    rows = []
    for row in df.itertuples(index=False, name=None):
        out = [source_file]
        for c, v in zip(excel_cols, row):
            if col_is_numeric(c):
                out.append(clean_numeric_to_str(v))  # '1234.56' o None
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
        cur.fast_executemany = False  # evita crashes/segfault

        inserted = 0
        for i in range(0, len(rows), BATCH_SIZE):
            batch = rows[i:i+BATCH_SIZE]
            try:
                cur.executemany(sql, batch)
                cn.commit()
                inserted += len(batch)
                print(f"OK batch {i+1}-{i+len(batch)}")
            except pyodbc.Error as e:
                cn.rollback()
                print(f"❌ Error en batch {i+1}-{i+len(batch)}: {e}")
                # aislar filas malas
                for j, r in enumerate(batch):
                    try:
                        cur.execute(sql, r)
                        cn.commit()
                        inserted += 1
                    except pyodbc.Error as e2:
                        cn.rollback()
                        global_idx = i + j
                        print(f"🚫 Saltando fila problemática global #{global_idx} (Excel aprox fila {global_idx+2})")
                        print("Detalle:", e2)
                        continue

    print(f"✅ OK: insertadas {inserted} filas")


def main():
    df = read_excel(EXCEL_PATH, SHEET_NAME)

    print(f"Archivo: {Path(EXCEL_PATH).name}")
    print(f"Filas: {len(df)} | Columnas: {len(df.columns)}")

    df = data_cleaners.apply_fuzzy_matching_to_cobrador(df, threshold=90)

    found_numeric = [c for c in df.columns if col_is_numeric(c)]
    print("Columnas numéricas detectadas:", found_numeric if found_numeric else "ninguna")

    ensure_table_and_columns(df)
    insert_append(df, Path(EXCEL_PATH).name)


if __name__ == "__main__":
    main()