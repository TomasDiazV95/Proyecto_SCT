import os
import re
import csv
from dataclasses import dataclass
from datetime import datetime, timedelta
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
DATABASE = os.getenv("DB_NAME", "bdphoenixconsultas")
USER = os.getenv("DB_USER")
PASSWORD = os.getenv("DB_PASSWORD")
DRIVER_ENV = os.getenv("DB_DRIVER")

DEFAULT_FOLDER = Path(r"C:\Users\Analista de Datos\Desktop\ARAUCANA")
MESES = {
    1: "Enero",
    2: "Febrero",
    3: "Marzo",
    4: "Abril",
    5: "Mayo",
    6: "Junio",
    7: "Julio",
    8: "Agosto",
    9: "Septiembre",
    10: "Octubre",
    11: "Noviembre",
    12: "Diciembre",
}
MES_NUM_BY_NAME = {name.upper(): f"{num:02d}" for num, name in MESES.items()}
FECHA_REFERENCIA = datetime.now() - timedelta(days=1)
MES_TEXTO = MESES[FECHA_REFERENCIA.month]
MES_NUM_STR = str(FECHA_REFERENCIA.month).zfill(2)
NOMBRE_ASIGNACION = f"Asignacion_PHOENIX_financiera_{MES_TEXTO}{FECHA_REFERENCIA.year}.csv"
NOMBRE_RECUPERACION = f"RECUPERACION_Phoenix_{FECHA_REFERENCIA.year}{MES_NUM_STR}.csv"
ASIGNACION_PATH = Path(os.getenv("LA_ASIGNACION_PATH", str(DEFAULT_FOLDER / NOMBRE_ASIGNACION)))
RECUPERACION_PATH = Path(os.getenv("LA_RECUPERACION_PATH", str(DEFAULT_FOLDER / NOMBRE_RECUPERACION)))

TABLE_ASIGNACION = "dbo.tmp_LA_asignacion"
TABLE_PAGOS = "dbo.tmp_LA_pagos"

BATCH_SIZE = 500

NUMERIC_COLUMNS_BY_FILE = {
    "ASIGNACION": {
        "CAPITAL",
        "INTERESES",
        "TOTAL_DEUDA",
        "SALDO_CUOT_MORA",
        "TOTAL_MORA",
        "VALOR_CUOTA",
    },
    "RECUPERACION": {"RECUPERACION"},
}

TIPO_PAGO_BY_KEY = {
    "EACTSEGCES": "E-ACTSEGCES",
    "EMANUAL": "E-MANUAL",
    "EINTERCC": "E-INTER-CC",
    "ECC": "E-CC",
}


@dataclass(frozen=True)
class ColumnSpec:
    name: str
    sql_type: str
    kind: str


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
    return "[" + str(name).replace("]", "]]" ) + "]"


def normalize_col_name(value: str) -> str:
    text = str(value).replace("\x00", "").replace("\ufeff", "")
    text = re.sub(r"[\u0000-\u001f\u007f]+", "", text)
    return re.sub(r"\s+", " ", text).strip()


def make_unique_names(names: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    unique: list[str] = []

    for name in names:
        base = name or "COL"
        count = seen.get(base, 0)
        if count == 0:
            unique_name = base
        else:
            unique_name = f"{base}_{count + 1}"
        seen[base] = count + 1
        unique.append(unique_name)

    return unique


def read_csv_file(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"No existe el archivo: {path}")

    last_error: Exception | None = None

    for encoding in ("utf-8-sig", "utf-16", "utf-16-le", "cp1252", "latin1"):
        try:
            with open(path, "r", encoding=encoding, newline="") as handle:
                sample = handle.read(4096)
                handle.seek(0)
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=[",", ";", "|", "\t"])
                    sep = dialect.delimiter
                except Exception:
                    sep = None

                df = pd.read_csv(
                    handle,
                    dtype=str,
                    sep=sep,
                    engine="python",
                    keep_default_na=False,
                )
            df.columns = make_unique_names([normalize_col_name(c) for c in df.columns])
            df = df.replace({"": None, "nan": None, "NaN": None})
            return df
        except Exception as exc:
            last_error = exc

    raise RuntimeError(f"No se pudo leer el CSV {path.name}: {last_error}")


def clean_cell(value):
    if value is None or value is pd.NA:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    return text


def is_text_only_field(field_name: str) -> bool:
    token = re.sub(r"[^A-Z0-9]+", "", str(field_name).upper())
    return any(
        marker in token
        for marker in ("FOLIOCREDITO", "CONTRATO", "RUTAFILIADO", "RUTASIGNADO")
    )


def normalize_tipo_pago(value: str) -> str | None:
    text = clean_cell(value)
    if text is None:
        return None

    text = text.upper()
    text = text.replace("–", "-").replace("—", "-")
    text = re.sub(r"\s*-\s*", "-", text)
    text = re.sub(r"\s+", " ", text).strip()

    if text.startswith("E "):
        text = "E-" + text[2:].lstrip("-").strip()
    text = text.replace("E -", "E-")
    text = text.replace("E- ", "E-")
    text = text.replace(" ", "")

    key = re.sub(r"[^A-Z]", "", text)
    if key in TIPO_PAGO_BY_KEY:
        return TIPO_PAGO_BY_KEY[key]

    return text if text.startswith("E-") else text


def parse_decimal(value: str) -> Decimal | None:
    text = clean_cell(value)
    if text is None:
        return None

    text = re.sub(r"[^0-9,\.\-]", "", text)
    if text in {"", "-", ".", ","}:
        return None

    if "." in text and "," in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "")
            text = text.replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        if text.count(",") > 1:
            text = text.replace(",", "")
        else:
            text = text.replace(",", ".")
    elif "." in text and text.count(".") > 1:
        text = text.replace(".", "")

    try:
        return Decimal(text)
    except Exception:
        return None


def infer_column_spec(series: pd.Series, forced_numeric: bool = False) -> ColumnSpec:
    if is_text_only_field(series.name):
        return ColumnSpec(name=series.name, sql_type="NVARCHAR(MAX) NULL", kind="text")

    values = [clean_cell(v) for v in series.tolist()]
    non_empty = [v for v in values if v is not None]

    if not non_empty:
        return ColumnSpec(name=series.name, sql_type="NVARCHAR(MAX) NULL", kind="text")

    if forced_numeric:
        return ColumnSpec(name=series.name, sql_type="DECIMAL(38,0) NULL", kind="numeric")

    return ColumnSpec(name=series.name, sql_type="NVARCHAR(MAX) NULL", kind="text")


def infer_schema(df: pd.DataFrame, forced_numeric: set[str]) -> list[ColumnSpec]:
    base_names = [normalize_col_name(c) for c in df.columns]
    unique_names = make_unique_names(base_names)
    specs: list[ColumnSpec] = []

    for idx, name in enumerate(unique_names):
        series = df.iloc[:, idx].copy()
        series.name = name
        specs.append(infer_column_spec(series, forced_numeric=base_names[idx].upper() in forced_numeric))

    return specs


def existing_columns(table_name: str) -> set[str]:
    with connect() as cn:
        cur = cn.cursor()
        schema, table = table_name.split(".", 1)
        cur.execute(
            """
            SELECT c.name
            FROM sys.columns c
            INNER JOIN sys.tables t ON c.object_id = t.object_id
            INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
            WHERE s.name = ? AND t.name = ?
            """,
            (schema, table),
        )
        return {row[0] for row in cur.fetchall()}


def ensure_table_and_columns(table_name: str, specs: list[ColumnSpec]) -> None:
    with connect() as cn:
        cur = cn.cursor()

        cur.execute(
            f"""
            IF OBJECT_ID('{table_name}', 'U') IS NULL
            BEGIN
                CREATE TABLE {table_name} (
                    id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                    fecha_carga DATE NOT NULL CONSTRAINT DF_{table_name.replace('.', '_')}_fecha_carga DEFAULT (CONVERT(date, GETDATE())),
                    source_file NVARCHAR(260) NOT NULL
                );
                CREATE INDEX IX_{table_name.replace('.', '_')}_source_file ON {table_name}(source_file);
            END
            """
        )
        cn.commit()

        existing = existing_columns(table_name)

        rename_map = {
            "fld_\xff\xfeEmpresaExterna": "fld_EmpresaExterna",
        }
        for old_name, new_name in rename_map.items():
            if old_name in existing:
                if new_name not in existing:
                    cur.execute(f"ALTER TABLE {table_name} ADD {sql_ident(new_name)} NVARCHAR(MAX) NULL;")
                    existing.add(new_name)
                cur.execute(
                    f"UPDATE {table_name} SET {sql_ident(new_name)} = COALESCE({sql_ident(new_name)}, {sql_ident(old_name)}) WHERE {sql_ident(old_name)} IS NOT NULL"
                )
                cur.execute(f"ALTER TABLE {table_name} DROP COLUMN {sql_ident(old_name)};")
                existing.remove(old_name)

        for spec in specs:
            fld_name = f"fld_{spec.name}"
            if fld_name not in existing:
                try:
                    cur.execute(f"ALTER TABLE {table_name} ADD {sql_ident(fld_name)} {spec.sql_type};")
                except pyodbc.Error as exc:
                    if "2705" in str(exc) or "42S21" in str(exc):
                        continue
                    raise

        for spec in specs:
            if spec.kind == "numeric":
                fld_name = f"fld_{spec.name}"
                if fld_name in existing:
                    cur.execute(f"ALTER TABLE {table_name} ALTER COLUMN {sql_ident(fld_name)} DECIMAL(38,0) NULL;")

        if "fecha_carga" not in existing:
            cur.execute(
                f"ALTER TABLE {table_name} ADD fecha_carga DATE NOT NULL CONSTRAINT DF_{table_name.replace('.', '_')}_fecha_carga DEFAULT (CONVERT(date, GETDATE()));"
            )
        if "source_file" not in existing:
            cur.execute(f"ALTER TABLE {table_name} ADD source_file NVARCHAR(260) NOT NULL DEFAULT ('');")
        if table_name in (TABLE_PAGOS, TABLE_ASIGNACION):
            if "mes_proceso" not in existing:
                cur.execute(f"ALTER TABLE {table_name} ADD mes_proceso VARCHAR(7) NULL;")
            if "periodo" not in existing:
                cur.execute(f"ALTER TABLE {table_name} ADD periodo VARCHAR(7) NULL;")

        if table_name == TABLE_PAGOS:
            if "fecha_negocio" not in existing:
                cur.execute(f"ALTER TABLE {table_name} ADD fecha_negocio DATE NULL;")
            # Backfill de columnas operativas para mantener consistencia en datos historicos.
            cur.execute(
                f"""
                UPDATE {table_name}
                SET
                    fecha_carga = COALESCE(fecha_negocio, fecha_carga),
                    mes_proceso = CASE
                        WHEN COALESCE(fecha_negocio, fecha_carga) IS NULL THEN mes_proceso
                        WHEN mes_proceso IS NOT NULL THEN mes_proceso
                        ELSE RIGHT('0' + CAST(MONTH(COALESCE(fecha_negocio, fecha_carga)) AS varchar(2)), 2)
                             + '-' + CAST(YEAR(COALESCE(fecha_negocio, fecha_carga)) AS varchar(4))
                    END,
                    periodo = CASE
                        WHEN COALESCE(fecha_negocio, fecha_carga) IS NULL THEN periodo
                        WHEN periodo IS NOT NULL THEN periodo
                        ELSE RIGHT('0' + CAST(MONTH(COALESCE(fecha_negocio, fecha_carga)) AS varchar(2)), 2)
                             + '-' + CAST(YEAR(COALESCE(fecha_negocio, fecha_carga)) AS varchar(4))
                    END
                WHERE COALESCE(fecha_negocio, fecha_carga) IS NOT NULL
                  AND (
                        fecha_carga <> COALESCE(fecha_negocio, fecha_carga)
                        OR mes_proceso IS NULL
                        OR periodo IS NULL
                      )
                """
            )
        elif table_name == TABLE_ASIGNACION:
            cur.execute(
                f"""
                UPDATE {table_name}
                SET
                    mes_proceso = RIGHT('0' + CAST(MONTH(fecha_carga) AS varchar(2)), 2)
                                  + '-' + CAST(YEAR(fecha_carga) AS varchar(4)),
                    periodo = RIGHT('0' + CAST(MONTH(fecha_carga) AS varchar(2)), 2)
                              + '-' + CAST(YEAR(fecha_carga) AS varchar(4))
                WHERE fecha_carga IS NOT NULL
                  AND (
                        mes_proceso IS NULL
                        OR periodo IS NULL
                      )
                """
            )

        cn.commit()


def convert_row_value(value, kind: str, field_name: str):
    if is_text_only_field(field_name):
        return clean_cell(value)
    if kind == "numeric":
        parsed = parse_decimal(value)
        return int(parsed) if parsed is not None else None
    if field_name.upper() == "TIPOPAGO":
        return normalize_tipo_pago(value)
    return clean_cell(value)


def mes_proceso_from_source_file(source_file: str) -> str:
    text = source_file.upper()

    match = re.search(r"RECUPERACION_PHOENIX_(\d{4})(\d{2})", text)
    if match:
        year, month = match.groups()
        return f"{month}-{year}"

    match = re.search(r"ASIGNACION_PHOENIX_FINANCIERA_([A-Z]+)(\d{4})", text)
    if match:
        month_name, year = match.groups()
        month = MES_NUM_BY_NAME.get(month_name)
        if month:
            return f"{month}-{year}"

    raise ValueError(f"No se pudo obtener mes_proceso desde el nombre del archivo: {source_file}")


def source_file_exists(table_name: str, source_file: str) -> bool:
    try:
        with connect() as cn:
            cur = cn.cursor()
            cur.execute(f"SELECT COUNT(1) FROM {table_name} WHERE source_file = ?", (source_file,))
            return (cur.fetchone()[0] or 0) > 0
    except pyodbc.Error:
        return False


def insert_append(
    df: pd.DataFrame,
    table_name: str,
    source_file: str,
    specs: list[ColumnSpec],
    replace_existing_source: bool,
) -> None:
    existing = existing_columns(table_name)
    insert_cols = ["source_file"] + [f"fld_{spec.name}" for spec in specs]
    mes_proceso_value = mes_proceso_from_source_file(source_file)
    month_start = datetime.strptime(mes_proceso_value, "%m-%Y").date().replace(day=1)
    business_date_value = month_start.isoformat()

    if "fecha_negocio" in existing:
        insert_cols.append("fecha_negocio")
    if table_name == TABLE_PAGOS and "fecha_carga" in existing:
        insert_cols.append("fecha_carga")
    if "mes_proceso" in existing:
        insert_cols.append("mes_proceso")
    if "periodo" in existing:
        insert_cols.append("periodo")

    placeholders = ",".join(["?"] * len(insert_cols))
    sql = f"INSERT INTO {table_name} ({','.join(map(sql_ident, insert_cols))}) VALUES ({placeholders})"

    rows = []
    for row in df.itertuples(index=False, name=None):
        out = [source_file]
        for value, spec in zip(row, specs):
            out.append(convert_row_value(value, spec.kind, spec.name))
        if "fecha_negocio" in existing:
            out.append(business_date_value)
        if table_name == TABLE_PAGOS and "fecha_carga" in existing:
            out.append(business_date_value)
        if "mes_proceso" in existing:
            out.append(mes_proceso_value)
        if "periodo" in existing:
            out.append(mes_proceso_value)
        rows.append(tuple(out))

    with connect() as cn:
        cn.autocommit = False
        cur = cn.cursor()
        cur.fast_executemany = True

        if replace_existing_source:
            cur.execute(f"DELETE FROM {table_name} WHERE source_file = ?", (source_file,))
            deleted_rows = cur.rowcount if cur.rowcount is not None else 0
            if deleted_rows:
                print(f"Reemplazo por archivo en {table_name}: {source_file}, filas borradas {deleted_rows}")
            else:
                print(f"Archivo nuevo en {table_name}: {source_file}")
        else:
            print(f"Archivo nuevo en {table_name}: {source_file}")

        inserted = 0
        for i in range(0, len(rows), BATCH_SIZE):
            batch = rows[i : i + BATCH_SIZE]
            try:
                cur.executemany(sql, batch)
                inserted += len(batch)
                print(f"OK batch {i + 1}-{i + len(batch)} en {table_name}")
            except pyodbc.Error as exc:
                print(f"Error en batch {i + 1}-{i + len(batch)} en {table_name}: {exc}")
                for j, record in enumerate(batch):
                    try:
                        cur.execute(sql, record)
                        inserted += 1
                    except pyodbc.Error as exc2:
                        global_idx = i + j
                        print(
                            f"Saltando fila problemática #{global_idx} en {table_name} (aprox fila Excel/CSV {global_idx + 2})"
                        )
                        print("Detalle:", exc2)

        cn.commit()

    print(f"OK: insertadas {inserted} filas en {table_name}")


def process_file(path: Path, table_name: str, file_type: str, skip_if_loaded: bool, replace_existing_source: bool) -> None:
    source_file = path.name
    forced_numeric = NUMERIC_COLUMNS_BY_FILE.get(file_type.upper(), set())

    if skip_if_loaded and source_file_exists(table_name, source_file):
        print(f"Ya cargado este archivo, se omite {file_type}: {source_file}")
        return

    df = read_csv_file(path)
    specs = infer_schema(df, forced_numeric=forced_numeric)

    print(f"Archivo: {path.name}")
    print(f"Tabla destino: {table_name}")
    print(f"Filas: {len(df)} | Columnas: {len(df.columns)}")
  
  
    ensure_table_and_columns(table_name, specs)
    insert_append(df, table_name, source_file, specs, replace_existing_source)


def validate_required_inputs(jobs: list[tuple[Path, str, str, bool, bool]]) -> None:
    missing = [(file_type, path) for path, _table_name, file_type, _skip_if_loaded, _replace_existing_source in jobs if not path.exists()]
    if not missing:
        return

    detail = "; ".join(f"{file_type}: {path}" for file_type, path in missing)
    raise FileNotFoundError(f"No se ejecuta ETL La Araucana: faltan archivos obligatorios ({detail})")


def main() -> None:
    jobs = [
        (ASIGNACION_PATH, TABLE_ASIGNACION, "ASIGNACION", True, False),
        (RECUPERACION_PATH, TABLE_PAGOS, "RECUPERACION", False, True),
    ]

    validate_required_inputs(jobs)

    for path, table_name, file_type, skip_if_loaded, replace_existing_source in jobs:
        process_file(path, table_name, file_type, skip_if_loaded, replace_existing_source)


if __name__ == "__main__":
    main()
