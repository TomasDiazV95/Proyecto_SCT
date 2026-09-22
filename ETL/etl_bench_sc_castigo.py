import os
import re
from datetime import datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path

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


def parse_sheet_name(raw_value: str) -> int | str:
    value = raw_value.strip()
    return int(value) if value.isdigit() else value


SERVER = os.getenv("DB_SERVER")
DATABASE = os.getenv("DB_NAME")
USER = os.getenv("DB_USER")
PASSWORD = os.getenv("DB_PASSWORD")
DRIVER_ENV = os.getenv("DB_DRIVER")

BENCH_FOLDER = Path(require_env("BENCH_SC_CASTIGO_FOLDER"))
BENCH_PATTERN = require_env("BENCH_SC_CASTIGO_PATTERN")
SHEET_NAME = parse_sheet_name(os.getenv("BENCH_SC_CASTIGO_SHEET_NAME", "0"))

TABLE = "dbo.tmp_bench_SC_Castigo"
BATCH_SIZE = 5000

COLUMN_SPECS = [
    ("FECHA", "text8"),
    ("PERIODO", "text6"),
    ("RUT", "integer"),
    ("OPERACION", "integer"),
    ("NOMBRE", "text100"),
    ("REGION", "text40"),
    ("COMUNA", "text40"),
    ("ZONA", "text20"),
    ("EMPRESA", "text20"),
    ("TIPO_EMP", "text20"),
    ("SUPER_EXT", "text40"),
    ("COBRADOR", "text40"),
    ("CONCURSO_BENCH", "text100"),
    ("AVAN_BENCH", "text10"),
    ("CUOTAS_PLA", "integer"),
    ("TRAMO_MORA", "text5"),
    ("DEUDA_AP", "integer"),
    ("DEUDA_ACT", "integer"),
    ("DM_INI", "integer"),
    ("DM_ACT", "integer"),
    ("DM_CIERRE", "integer"),
    ("RECUP", "integer"),
    ("ESTADO_JUICIO", "text100"),
    ("SUBESTADO_JUICIO", "text100"),
    ("ABOGADO", "text40"),
    ("DACION", "text10"),
    ("MARCA_RENE", "text10"),
    ("CAMPAÑA_PUT", "text100"),
    ("CAMPAÑA_RECON", "text100"),
    ("CONTACTO", "text40"),
    ("CANAL", "text20"),
    ("ORIGENGESTION", "text20"),
    ("CLASIFICACIONGESTION", "text20"),
    ("ACCION", "text40"),
    ("ESTADO", "text100"),
    ("SUBESTADO", "text40"),
    ("FECH_INGR", "date_ddmmyyyy"),
    ("COMENTARIO", "textmax"),
    ("FECHA_COMP", "date_ddmmyyyy"),
    ("REGION_DRIVE", "text40"),
    ("ZONA_DRIVE", "text20"),
    ("COMUNA_DRIVE", "text40"),
    ("DIRECCION_DRIVE", "textmax"),
    ("TELEFONO_CASA_DRIVE", "phone"),
    ("TELEFONO_MOVIL_DRIVE", "phone"),
    ("TELEFONO_COMERCIAL_DRIVE", "phone"),
    ("EMAIL_DRIVE", "text100"),
]

COLUMN_KINDS = dict(COLUMN_SPECS)
EXPECTED_COLUMNS = [name for name, _ in COLUMN_SPECS]


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


def normalize_excel_col(value: object) -> str:
    text = str(value).replace("\x00", "").replace("\ufeff", "")
    text = re.sub(r"[\u0000-\u001f\u007f]+", "", text)
    return re.sub(r"\s+", "_", text.strip()).upper()


def clean_cell(value: object) -> str | None:
    if value is None or value is pd.NA:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    text = str(value).replace("\x00", "").strip()
    if not text or text.lower() == "nan":
        return None
    return text


def clean_text(value: object) -> str | None:
    text = clean_cell(value)
    if text is None:
        return None
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def clean_numeric(value: object) -> str | None:
    text = clean_cell(value)
    if text is None:
        return None

    text = re.sub(r"[^0-9,\.\-]", "", text)
    if text in {"", "-", ".", ","}:
        return None

    if "." in text and "," in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        if text.count(",") > 1:
            text = text.replace(",", "")
        else:
            text = text.replace(",", ".")
    elif text.count(".") > 1:
        text = text.replace(".", "")

    try:
        return str(int(Decimal(text)))
    except Exception:
        return None


def clean_text_digits(value: object, max_len: int | None = None) -> str | None:
    text = clean_numeric(value)
    if text is None:
        return None
    text = text.lstrip("-")
    if max_len is not None and len(text) > max_len:
        text = text[:max_len]
    return text or None


def parse_date_ddmmyyyy(value: object):
    text = clean_cell(value)
    if text is None:
        return None

    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, pd.Timestamp):
        return value.date()

    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def clean_phone(value: object) -> str | None:
    text = clean_cell(value)
    if text is None:
        return None

    digits = re.sub(r"\D", "", text)
    if not digits:
        return None

    if len(digits) > 9:
        digits = digits[-9:]
    if len(digits) == 8:
        digits = "9" + digits
    if len(digits) != 9 or digits.startswith("1"):
        return None
    return digits


def sql_type_for(kind: str) -> str:
    if kind == "integer":
        return "DECIMAL(38,0) NULL"
    if kind == "phone":
        return "NVARCHAR(9) NULL"
    if kind == "date_ddmmyyyy":
        return "DATE NULL"
    if kind == "textmax":
        return "NVARCHAR(MAX) NULL"
    if kind.startswith("text") and kind[4:].isdigit():
        return f"NVARCHAR({kind[4:]}) NULL"
    return "NVARCHAR(MAX) NULL"


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
    df = pd.read_excel(BytesIO(raw), sheet_name=SHEET_NAME, dtype=object, engine="openpyxl")
    df.columns = [normalize_excel_col(c) for c in df.columns]
    df = df.where(pd.notnull(df), None)

    missing = [col for col in EXPECTED_COLUMNS if col not in df.columns]
    if missing:
        raise RuntimeError("Faltan columnas esperadas en el Excel: " + ", ".join(missing))

    return df[EXPECTED_COLUMNS]


def ensure_table() -> None:
    column_definitions = ",\n                    ".join(
        f"{sql_ident('fld_' + name)} {sql_type_for(kind)}" for name, kind in COLUMN_SPECS
    )

    with connect() as cn:
        cur = cn.cursor()
        cur.execute(
            f"""
            IF OBJECT_ID('{TABLE}', 'U') IS NULL
            BEGIN
                CREATE TABLE {TABLE} (
                    id_bench_sc_castigo BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                    fecha_carga DATE NOT NULL CONSTRAINT DF_tmp_bench_SC_Castigo_fecha_carga DEFAULT (CONVERT(date, GETDATE())),
                    ts_carga DATETIME2(0) NOT NULL CONSTRAINT DF_tmp_bench_SC_Castigo_ts_carga DEFAULT (SYSDATETIME()),
                    source_file NVARCHAR(260) NULL,
                    {column_definitions}
                );
                CREATE INDEX IX_tmp_bench_SC_Castigo_fecha_carga ON {TABLE}(fecha_carga);
                CREATE INDEX IX_tmp_bench_SC_Castigo_source_file ON {TABLE}(source_file);
            END
            """
        )
        cn.commit()

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
        existing = {row[0] for row in cur.fetchall()}

        for name, kind in COLUMN_SPECS:
            column_name = "fld_" + name
            if column_name not in existing:
                cur.execute(f"ALTER TABLE {TABLE} ADD {sql_ident(column_name)} {sql_type_for(kind)};")
        cn.commit()


def get_last_source_file() -> str | None:
    try:
        with connect() as cn:
            cur = cn.cursor()
            cur.execute(f"SELECT TOP (1) source_file FROM {TABLE} ORDER BY id_bench_sc_castigo DESC")
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


def value_for_insert(column: str, value: object):
    kind = COLUMN_KINDS[column]
    if kind == "integer":
        return clean_numeric(value)
    if kind == "phone":
        return clean_phone(value)
    if kind == "date_ddmmyyyy":
        return parse_date_ddmmyyyy(value)
    if column in {"FECHA", "PERIODO"}:
        return clean_text_digits(value, 8 if column == "FECHA" else 6)
    return clean_text(value)


def insert_append(df: pd.DataFrame, source_file: str) -> None:
    insert_cols = ["source_file"] + ["fld_" + col for col in EXPECTED_COLUMNS]
    placeholders = ",".join(["?"] * len(insert_cols))
    sql = f"""
    INSERT INTO {TABLE} ({','.join(map(sql_ident, insert_cols))})
    VALUES ({placeholders})
    """

    rows = []
    for row in df.itertuples(index=False, name=None):
        out = [source_file]
        for column, value in zip(EXPECTED_COLUMNS, row):
            out.append(value_for_insert(column, value))
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
            except pyodbc.Error as exc:
                cn.rollback()
                print(f"Error en batch {i + 1}-{i + len(batch)}: {exc}")
                for j, item in enumerate(batch):
                    try:
                        cur.execute(sql, item)
                        cn.commit()
                        inserted += 1
                    except pyodbc.Error as row_exc:
                        cn.rollback()
                        global_idx = i + j
                        print(f"Saltando fila problematica global #{global_idx} (Excel aprox fila {global_idx + 2})")
                        print("Detalle:", row_exc)

    print(f"OK: insertadas {inserted} filas en {TABLE}")


def main() -> None:
    excel_path = get_input_excel_path()
    source_file = excel_path.name

    print(f"Archivo SC Castigo: {excel_path}")

    ensure_table()

    if should_skip_load(source_file):
        print(f"Ya cargado, se omite: {source_file}")
        return

    df = read_excel(excel_path)
    print(f"Filas: {len(df)} | Columnas: {len(df.columns)}")
    insert_append(df, source_file)


if __name__ == "__main__":
    main()
