import csv
import os
import re
from datetime import datetime
from decimal import Decimal
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

DEFAULT_FOLDER = Path(__file__).resolve().parents[1] / "archivos"
CSV_FOLDER = Path(os.getenv("CUOTAS_ITAU_VENCIDA_FOLDER", str(DEFAULT_FOLDER)))
CSV_PATTERN = os.getenv("CUOTAS_ITAU_VENCIDA_PATTERN", "*.csv")

TABLE = "dbo.cuotas_itau_vencida"
BATCH_SIZE = 10000

SOURCE_COLUMN_SPECS = [
    ("FechaDeProceso", "date"),
    ("RutCliente", "text13"),
    ("NumeroOperacion", "text24"),
    ("NumeroCuota", "integer"),
    ("FechaVencimiento", "date"),
    ("ValorCuota", "integer"),
    ("capital", "integer"),
    ("InteresesSimple", "integer"),
    ("InteresMora", "integer"),
    ("ImporteOtros", "integer"),
    ("ImporteTotal", "integer"),
    ("Estado", "text24"),
]

TABLE_COLUMN_SPECS = [
    ("FechaDeProceso", "date"),
    ("RutCliente", "text13"),
    ("Rut", "integer"),
    ("Dv", "text1"),
    ("NumeroOperacion", "text24"),
    ("NumeroCuota", "integer"),
    ("FechaVencimiento", "date"),
    ("ValorCuota", "integer"),
    ("capital", "integer"),
    ("InteresesSimple", "integer"),
    ("InteresMora", "integer"),
    ("ImporteOtros", "integer"),
    ("ImporteTotal", "integer"),
    ("Estado", "text24"),
]

SOURCE_COLUMNS = [name for name, _ in SOURCE_COLUMN_SPECS]
TABLE_COLUMNS = [name for name, _ in TABLE_COLUMN_SPECS]
COLUMN_KINDS = dict(TABLE_COLUMN_SPECS)


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
    return "[" + str(name).replace("]", "]]" ) + "]"


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


def parse_decimal(value: object, scale: int = 0) -> str | None:
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
        number = Decimal(text)
    except Exception:
        return None

    if scale == 0:
        return str(int(number))
    return str(number.quantize(Decimal("1." + "0" * scale)))


def parse_date(value: object):
    text = clean_cell(value)
    if text is None:
        return None

    for fmt in (
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d-%m-%Y %H:%M:%S.%f",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y",
        "%d/%m/%Y %H:%M:%S.%f",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y",
        "%Y/%m/%d %H:%M:%S.%f",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d",
    ):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def split_rut_dv(value: object) -> tuple[str | None, str | None]:
    text = clean_cell(value)
    if text is None:
        return None, None

    normalized = re.sub(r"[^0-9Kk]", "", text).upper()
    if len(normalized) < 2:
        return None, None

    rut = normalized[:-1]
    dv = normalized[-1]
    if not rut.isdigit() or not re.fullmatch(r"[0-9K]", dv):
        return None, None
    return rut, dv


def sql_type_for(kind: str) -> str:
    if kind == "integer":
        return "DECIMAL(38,0) NULL"
    if kind == "date":
        return "DATE NULL"
    if kind.startswith("text") and kind[4:].isdigit():
        return f"NVARCHAR({kind[4:]}) NULL"
    return "NVARCHAR(MAX) NULL"


def value_for_insert(column: str, value: object):
    kind = COLUMN_KINDS[column]
    if kind == "integer":
        return parse_decimal(value, 0)
    if kind == "date":
        return parse_date(value)
    return clean_text(value)


def get_input_csv_path() -> Path:
    if not CSV_FOLDER.exists():
        raise FileNotFoundError(f"La carpeta no existe: {CSV_FOLDER}")

    files = [path for path in CSV_FOLDER.glob(CSV_PATTERN) if not path.name.startswith("~$")]
    if not files:
        raise FileNotFoundError(
            f"No se encontro ningun archivo que cumpla el patron '{CSV_PATTERN}' en {CSV_FOLDER}"
        )
    return max(files, key=lambda path: path.stat().st_mtime)


def read_csv_file(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"No existe el CSV en: {path}")

    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "utf-16", "utf-16-le", "cp1252", "latin1"):
        try:
            with path.open("r", encoding=encoding, newline="") as handle:
                sample = handle.read(4096)
                handle.seek(0)
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=[",", ";", "|", "\t"])
                    sep = dialect.delimiter
                except Exception:
                    sep = None

                df = pd.read_csv(
                    handle,
                    dtype=object,
                    sep=sep,
                    engine="python",
                    header=None,
                    keep_default_na=False,
                )

            if len(df.columns) != len(SOURCE_COLUMNS):
                raise RuntimeError(
                    f"El CSV trae {len(df.columns)} columnas, pero se esperaban {len(SOURCE_COLUMNS)}"
                )

            df.columns = SOURCE_COLUMNS
            df = df.replace({"": None, "nan": None, "NaN": None})
            rut_dv = df["RutCliente"].apply(split_rut_dv)
            df.insert(df.columns.get_loc("RutCliente") + 1, "Rut", rut_dv.apply(lambda item: item[0]))
            df.insert(df.columns.get_loc("Rut") + 1, "Dv", rut_dv.apply(lambda item: item[1]))

            invalid_rut = df["RutCliente"].apply(clean_cell).notna() & (
                df["Rut"].isna() | df["Dv"].isna()
            )
            if invalid_rut.any():
                print(f"Advertencia: {int(invalid_rut.sum())} filas tienen RutCliente invalido")

            return df[TABLE_COLUMNS]
        except Exception as exc:
            last_error = exc

    raise RuntimeError(f"No se pudo leer el CSV {path.name}: {last_error}")


def ensure_table() -> None:
    column_definitions = ",\n                    ".join(
        f"{sql_ident(name)} {sql_type_for(kind)}" for name, kind in TABLE_COLUMN_SPECS
    )

    with connect() as cn:
        cur = cn.cursor()
        cur.execute(
            f"""
            IF OBJECT_ID('{TABLE}', 'U') IS NULL
            BEGIN
                CREATE TABLE {TABLE} (
                    id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                    fecha_carga DATE NOT NULL CONSTRAINT DF_cuotas_itau_vencida_fecha_carga DEFAULT (CONVERT(date, GETDATE())),
                    ts_carga DATETIME2(0) NOT NULL CONSTRAINT DF_cuotas_itau_vencida_ts_carga DEFAULT (SYSDATETIME()),
                    source_file NVARCHAR(260) NULL,
                    {column_definitions}
                );
                CREATE INDEX IX_cuotas_itau_vencida_fecha_carga ON {TABLE}(fecha_carga);
                CREATE INDEX IX_cuotas_itau_vencida_source_file ON {TABLE}(source_file);
                CREATE INDEX IX_cuotas_itau_vencida_rut ON {TABLE}(Rut);
                CREATE INDEX IX_cuotas_itau_vencida_operacion ON {TABLE}(NumeroOperacion);
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

        for name, kind in TABLE_COLUMN_SPECS:
            if name not in existing:
                cur.execute(f"ALTER TABLE {TABLE} ADD {sql_ident(name)} {sql_type_for(kind)};")
        cn.commit()


def insert_append(df: pd.DataFrame, source_file: str) -> None:
    insert_cols = ["source_file"] + TABLE_COLUMNS
    placeholders = ",".join(["?"] * len(insert_cols))
    sql = f"""
    INSERT INTO {TABLE} ({','.join(map(sql_ident, insert_cols))})
    VALUES ({placeholders})
    """

    rows = []
    for row in df.itertuples(index=False, name=None):
        out = [source_file]
        for column, value in zip(TABLE_COLUMNS, row):
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
                        print(f"Saltando fila problematica global #{global_idx} (CSV aprox fila {global_idx + 1})")
                        print("Detalle:", row_exc)

    print(f"OK: insertadas {inserted} filas en {TABLE}")


def main() -> None:
    csv_path = get_input_csv_path()
    source_file = csv_path.name
    print(f"Archivo cuotas Itau vencida: {csv_path}")

    df = read_csv_file(csv_path)
    print(f"Filas: {len(df)} | Columnas cargadas: {len(df.columns)}")

    ensure_table()
    insert_append(df, source_file)


if __name__ == "__main__":
    main()
