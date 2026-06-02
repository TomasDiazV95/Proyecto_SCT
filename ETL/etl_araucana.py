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
TABLE_PERFORMANCE_CACHE = "dbo.tmp_LA_performance_cache"
TABLE_RESPUESTA_RANK = "dbo.tmp_LA_respuesta"

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

CANONICAL_TIPO_PAGO = {
    "E-ACTSEGCES",
    "E-MANUAL",
    "E-INTER-CC",
    "E-CC",
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


def normalize_text_identifier(value) -> str | None:
    text = clean_cell(value)
    if text is None:
        return None
    return text


def normalize_key(value: str) -> str | None:
    text = clean_cell(value)
    if text is None:
        return None
    text = text.upper().replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", text).strip()


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


def prepare_dataframe(df: pd.DataFrame, file_type: str) -> pd.DataFrame:
    file_type = file_type.upper()
    prepared = df.copy()

    if file_type == "ASIGNACION":
        base_index = prepared.index
        prepared["FOLIO_CREDITO_NORM"] = prepared.get(
            "fld_FOLIO_CREDITO", pd.Series([None] * len(prepared), index=base_index)
        ).map(normalize_key)
        prepared["RUT_ASIGNADO_NORM"] = prepared.get(
            "fld_RUT_ASIGNADO", pd.Series([None] * len(prepared), index=base_index)
        ).map(normalize_key)
        prepared["TIPO_CARTERA_NORM"] = prepared.get(
            "fld_TIPO_CARTERA", pd.Series([None] * len(prepared), index=base_index)
        ).map(normalize_key)
    elif file_type == "RECUPERACION":
        base_index = prepared.index
        prepared["CONTRATO_NORM"] = prepared.get(
            "fld_CONTRATO", pd.Series([None] * len(prepared), index=base_index)
        ).map(normalize_key)
        prepared["TipoPago_NORM"] = prepared.get(
            "fld_TipoPago", pd.Series([None] * len(prepared), index=base_index)
        ).map(normalize_tipo_pago)

    return prepared


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


def norm_text_sql(col: str) -> str:
    return (
        "UPPER(REPLACE(REPLACE(REPLACE("
        f"LTRIM(RTRIM(ISNULL({col}, ''))), "
        "NCHAR(8211), '-'), NCHAR(8212), '-'), ' ', ''))"
    )


def safe_int_sql(col: str, sql_type: str = "int") -> str:
    value = f"LTRIM(RTRIM(CONVERT(varchar(50), {col})))"
    return (
        "CASE "
        f"WHEN {col} IS NULL THEN NULL "
        f"WHEN {value} = '' THEN NULL "
        f"WHEN {value} LIKE '%[^0-9]%' THEN NULL "
        f"ELSE CAST({value} AS {sql_type}) "
        "END"
    )


def resolve_respuesta_ranking_config() -> dict:
    cols = existing_columns(TABLE_RESPUESTA_RANK)
    if not cols:
        return {"enabled": False}

    def pick(candidates: list[str]) -> str | None:
        for col in candidates:
            if col in cols:
                return col
        return None

    respuesta_col = pick(
        [
            "respuesta_gestion",
            "RespuestaGestion",
            "Respuesta",
            "respuesta",
            "RESPUESTA",
            "fld_respuesta_gestion",
            "fld_RespuestaGestion",
        ]
    )
    rank_col = pick(
        [
            "ranking",
            "RANKING",
            "rank",
            "RANK",
            "prioridad",
            "PRIORIDAD",
            "orden",
            "ORDEN",
        ]
    )

    if not respuesta_col or not rank_col:
        return {"enabled": False}

    return {
        "enabled": True,
        "respuesta_col": respuesta_col,
        "rank_col": rank_col,
    }


def latest_source_file(table_name: str) -> str | None:
    with connect() as cn:
        cur = cn.cursor()
        cur.execute(
            f"SELECT TOP 1 source_file FROM {table_name} WHERE source_file IS NOT NULL ORDER BY fecha_carga DESC, id DESC"
        )
        row = cur.fetchone()
        return row[0] if row else None


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


def ensure_indexes(table_name: str, file_type: str) -> None:
    prefix = table_name.replace(".", "_")
    with connect() as cn:
        cur = cn.cursor()

        def create_index(name: str, ddl: str) -> None:
            cur.execute(
                f"""
                IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = ?)
                BEGIN
                    {ddl}
                END
                """,
                (name,),
            )

        if file_type.upper() == "ASIGNACION":
            create_index(
                f"IX_{prefix}_sf_folio",
                f"CREATE INDEX IX_{prefix}_sf_folio ON {table_name}(source_file, [fld_FOLIO_CREDITO_NORM]) INCLUDE ([fld_RUT_ASIGNADO_NORM], [fld_TIPO_CARTERA_NORM])",
            )
            create_index(
                f"IX_{prefix}_sf_rut",
                f"CREATE INDEX IX_{prefix}_sf_rut ON {table_name}(source_file, [fld_RUT_ASIGNADO_NORM]) INCLUDE ([fld_FOLIO_CREDITO_NORM], [fld_TIPO_CARTERA_NORM])",
            )
        elif file_type.upper() == "RECUPERACION":
            create_index(
                f"IX_{prefix}_sf_fecha_contrato",
                f"CREATE INDEX IX_{prefix}_sf_fecha_contrato ON {table_name}(source_file, fecha_carga, [fld_CONTRATO_NORM]) INCLUDE ([fld_TipoPago_NORM], [fld_Recuperacion])",
            )
            create_index(
                f"IX_{prefix}_sf_tipopago",
                f"CREATE INDEX IX_{prefix}_sf_tipopago ON {table_name}(source_file, fecha_carga, [fld_TipoPago_NORM]) INCLUDE ([fld_CONTRATO_NORM], [fld_Recuperacion])",
            )

        cn.commit()


def ensure_la_schema_optimizations() -> None:
    asignacion_source = latest_source_file(TABLE_ASIGNACION)
    pagos_source = latest_source_file(TABLE_PAGOS)

    with connect() as cn:
        cur = cn.cursor()

        def add_column_if_missing(table_name: str, column_name: str, sql_type: str) -> None:
            existing = existing_columns(table_name)
            if column_name not in existing:
                cur.execute(f"ALTER TABLE {table_name} ADD {sql_ident(column_name)} {sql_type} NULL;")

        def create_index(name: str, ddl: str) -> None:
            cur.execute(
                f"""
                IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = ?)
                BEGIN
                    {ddl}
                END
                """,
                (name,),
            )

        # ASIGNACION normalized helpers
        add_column_if_missing(TABLE_ASIGNACION, "fld_FOLIO_CREDITO_NORM", "NVARCHAR(260)")
        add_column_if_missing(TABLE_ASIGNACION, "fld_RUT_ASIGNADO_NORM", "NVARCHAR(120)")
        add_column_if_missing(TABLE_ASIGNACION, "fld_TIPO_CARTERA_NORM", "NVARCHAR(120)")
        cur.execute(
            f"""
            UPDATE {TABLE_ASIGNACION}
            SET
                fld_FOLIO_CREDITO_NORM = UPPER(LTRIM(RTRIM(ISNULL(fld_FOLIO_CREDITO, '')))),
                fld_RUT_ASIGNADO_NORM = UPPER(LTRIM(RTRIM(ISNULL(fld_RUT_ASIGNADO, '')))),
                fld_TIPO_CARTERA_NORM = UPPER(LTRIM(RTRIM(ISNULL(fld_TIPO_CARTERA, ''))))
            WHERE source_file = ?
            """
            ,
            (asignacion_source,),
        )

        # PAGOS normalized helpers
        add_column_if_missing(TABLE_PAGOS, "fld_CONTRATO_NORM", "NVARCHAR(260)")
        add_column_if_missing(TABLE_PAGOS, "fld_TipoPago_NORM", "NVARCHAR(80)")
        cur.execute(
            f"""
            UPDATE {TABLE_PAGOS}
            SET
                fld_CONTRATO_NORM = UPPER(LTRIM(RTRIM(ISNULL(fld_CONTRATO, '')))),
                fld_TipoPago_NORM = CASE
                    WHEN UPPER(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(ISNULL(fld_TipoPago, ''))), '–', '-'), '—', '-'), ' ', '')) IN ('EACTSEGCES', 'E-ACTSEGCES') THEN 'E-ACTSEGCES'
                    WHEN UPPER(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(ISNULL(fld_TipoPago, ''))), '–', '-'), '—', '-'), ' ', '')) IN ('EMANUAL', 'E-MANUAL') THEN 'E-MANUAL'
                    WHEN UPPER(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(ISNULL(fld_TipoPago, ''))), '–', '-'), '—', '-'), ' ', '')) IN ('EINTERCC', 'E-INTER-CC') THEN 'E-INTER-CC'
                    WHEN UPPER(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(ISNULL(fld_TipoPago, ''))), '–', '-'), '—', '-'), ' ', '')) IN ('ECC', 'E-CC') THEN 'E-CC'
                    ELSE UPPER(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(ISNULL(fld_TipoPago, ''))), '–', '-'), '—', '-'), ' ', ''))
                END
            WHERE source_file = ?
            """
            ,
            (pagos_source,),
        )

        create_index(
            f"IX_{TABLE_ASIGNACION.replace('.', '_')}_sf_folio",
            f"CREATE INDEX IX_{TABLE_ASIGNACION.replace('.', '_')}_sf_folio ON {TABLE_ASIGNACION}(source_file, [fld_FOLIO_CREDITO_NORM]) INCLUDE ([fld_RUT_ASIGNADO_NORM], [fld_TIPO_CARTERA_NORM])",
        )
        create_index(
            f"IX_{TABLE_ASIGNACION.replace('.', '_')}_sf_rut",
            f"CREATE INDEX IX_{TABLE_ASIGNACION.replace('.', '_')}_sf_rut ON {TABLE_ASIGNACION}(source_file, [fld_RUT_ASIGNADO_NORM]) INCLUDE ([fld_FOLIO_CREDITO_NORM], [fld_TIPO_CARTERA_NORM])",
        )
        create_index(
            f"IX_{TABLE_PAGOS.replace('.', '_')}_sf_fecha_contrato",
            f"CREATE INDEX IX_{TABLE_PAGOS.replace('.', '_')}_sf_fecha_contrato ON {TABLE_PAGOS}(source_file, fecha_carga, [fld_CONTRATO_NORM]) INCLUDE ([fld_TipoPago_NORM], [fld_Recuperacion])",
        )
        create_index(
            f"IX_{TABLE_PAGOS.replace('.', '_')}_sf_tipopago",
            f"CREATE INDEX IX_{TABLE_PAGOS.replace('.', '_')}_sf_tipopago ON {TABLE_PAGOS}(source_file, fecha_carga, [fld_TipoPago_NORM]) INCLUDE ([fld_CONTRATO_NORM], [fld_Recuperacion])",
        )

        # Runtime tables used by the join path.
        create_index(
            "IX_tmp_GEST_CRM_rut_usuario",
            "CREATE INDEX IX_tmp_GEST_CRM_rut_usuario ON dbo.tmp_GEST_CRM(rut, UsuarioGestion) INCLUDE (ContactoGestion, GestionFecha, GestionHora, id)",
        )
        create_index(
            "IX_tmp_ejecutivos_usuario",
            "CREATE INDEX IX_tmp_ejecutivos_usuario ON dbo.tmp_ejecutivos(usuario_ejecutivo) INCLUDE (nombre_ejecutivo, cartera)",
        )

        cn.commit()


def ensure_performance_cache_table() -> None:
    with connect() as cn:
        cur = cn.cursor()
        cur.execute(
            f"""
            IF OBJECT_ID('{TABLE_PERFORMANCE_CACHE}', 'U') IS NULL
            BEGIN
                CREATE TABLE {TABLE_PERFORMANCE_CACHE} (
                    id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                    source_file_asignacion NVARCHAR(260) NOT NULL,
                    source_file_pagos NVARCHAR(260) NOT NULL,
                    fecha_carga DATE NOT NULL,
                    cartera NVARCHAR(120) NOT NULL,
                    nombre_ejecutivo NVARCHAR(260) NOT NULL,
                    usuario_gestion NVARCHAR(260) NULL,
                    recupero_gestor DECIMAL(38,0) NOT NULL,
                    recupero_total_cartera DECIMAL(38,0) NOT NULL,
                    aporte_grupal_pct DECIMAL(9,2) NOT NULL
                );
                CREATE INDEX IX_tmp_LA_performance_cache_lookup ON {TABLE_PERFORMANCE_CACHE}(source_file_asignacion, source_file_pagos, fecha_carga, cartera) INCLUDE (nombre_ejecutivo, recupero_gestor, recupero_total_cartera, aporte_grupal_pct);
            END
            """
        )
        cn.commit()


def refresh_performance_cache() -> None:
    asignacion_source = latest_source_file(TABLE_ASIGNACION)
    pagos_source = latest_source_file(TABLE_PAGOS)
    if not asignacion_source or not pagos_source:
        return

    ensure_performance_cache_table()
    ranking_cfg = resolve_respuesta_ranking_config()

    ranking_cte_sql = ""
    ranking_join_sql = ""
    ranking_select_sql = "999999 AS respuesta_ranking,"
    ranking_order_sql = "CASE WHEN g.rut IS NULL THEN 999999 ELSE 999999 END"

    if ranking_cfg.get("enabled"):
        respuesta_expr = norm_text_sql(f"r.{ranking_cfg['respuesta_col']}")
        rank_expr = safe_int_sql(f"r.{ranking_cfg['rank_col']}")
        ranking_cte_sql = f"""
            ranking_respuesta AS (
                SELECT
                    {respuesta_expr} AS respuesta_norm,
                    MIN({rank_expr}) AS respuesta_ranking
                FROM {TABLE_RESPUESTA_RANK} r
                WHERE r.{ranking_cfg['respuesta_col']} IS NOT NULL
                GROUP BY {respuesta_expr}
            ),
"""
        ranking_join_sql = "LEFT JOIN ranking_respuesta rr ON rr.respuesta_norm = g.respuesta_norm"
        ranking_select_sql = "COALESCE(rr.respuesta_ranking, 999999) AS respuesta_ranking,"
        ranking_order_sql = "COALESCE(rr.respuesta_ranking, 999999)"

    with connect() as cn:
        cur = cn.cursor()
        cur.execute(
            f"DELETE FROM {TABLE_PERFORMANCE_CACHE} WHERE source_file_asignacion = ? AND source_file_pagos = ?",
            (asignacion_source, pagos_source),
        )
        cur.execute(
            f"""
            ;WITH {ranking_cte_sql}gest_best AS (
                SELECT *
                FROM (
                    SELECT
                        UPPER(LTRIM(RTRIM(ISNULL(g.rut, '')))) AS rut_norm,
                        UPPER(LTRIM(RTRIM(ISNULL(g.UsuarioGestion, '')))) AS usuario_gestion_norm,
                        UPPER(LTRIM(RTRIM(ISNULL(e.nombre_ejecutivo, '')))) AS nombre_ejecutivo_norm,
                        {norm_text_sql("g.RespuestaGestion")} AS respuesta_norm,
                        {ranking_select_sql}
                        ROW_NUMBER() OVER (
                            PARTITION BY UPPER(LTRIM(RTRIM(ISNULL(g.rut, ''))))
                            ORDER BY
                                CASE UPPER(LTRIM(RTRIM(ISNULL(g.ContactoGestion, ''))))
                                    WHEN 'CONTACTO DIRECTO' THEN 0
                                    WHEN 'CONTACTO INDIRECTO' THEN 1
                                    WHEN 'GESTION DISCADOR' THEN 2
                                    WHEN 'NO CONTACTADO' THEN 3
                                    ELSE 99
                                END ASC,
                                {ranking_order_sql} ASC,
                                g.GestionFecha DESC,
                                g.GestionHora DESC,
                                g.id DESC
                        ) AS rn
                    FROM dbo.tmp_GEST_CRM g
                    INNER JOIN dbo.tmp_ejecutivos e
                        ON UPPER(LTRIM(RTRIM(ISNULL(g.UsuarioGestion, '')))) = UPPER(LTRIM(RTRIM(ISNULL(e.usuario_ejecutivo, ''))))
                    {ranking_join_sql}
                ) x
                WHERE rn = 1
            ),
            pagos_norm AS (
                SELECT
                    CONVERT(date, COALESCE(p.fecha_negocio, p.fecha_carga)) AS fecha_carga,
                    UPPER(LTRIM(RTRIM(ISNULL(p.fld_CONTRATO, '')))) AS contrato,
                    SUM(CONVERT(DECIMAL(38,0), ISNULL(p.fld_Recuperacion, 0))) AS recupero
                FROM dbo.tmp_LA_pagos p
                WHERE p.source_file = ?
                  AND COALESCE(p.fecha_negocio, p.fecha_carga) IS NOT NULL
                  AND UPPER(REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(ISNULL(p.fld_TipoPago, ''))), '–', '-'), '—', '-'), ' ', '')) IN ('E-ACTSEGCES','E-CC','E-INTER-CC','E-MANUAL')
                GROUP BY
                    CONVERT(date, COALESCE(p.fecha_negocio, p.fecha_carga)),
                    UPPER(LTRIM(RTRIM(ISNULL(p.fld_CONTRATO, ''))))
            ),
            asignacion_norm AS (
                SELECT
                    UPPER(LTRIM(RTRIM(ISNULL(a.fld_TIPO_CARTERA, '')))) AS cartera,
                    UPPER(LTRIM(RTRIM(ISNULL(a.fld_FOLIO_CREDITO, '')))) AS folio_credito,
                    UPPER(LTRIM(RTRIM(ISNULL(a.fld_RUT_ASIGNADO, '')))) AS rut_asignado
                FROM dbo.tmp_LA_asignacion a
                WHERE a.source_file = ?
                  AND a.fld_TIPO_CARTERA IS NOT NULL
            ),
            contrato_recupero AS (
                SELECT
                    pn.fecha_carga,
                    a.cartera,
                    gb.nombre_ejecutivo_norm AS nombre_ejecutivo,
                    gb.usuario_gestion_norm AS usuario_gestion,
                    a.folio_credito,
                    SUM(pn.recupero) AS recupero
                FROM asignacion_norm a
                INNER JOIN pagos_norm pn
                    ON a.folio_credito = pn.contrato
                INNER JOIN gest_best gb
                    ON a.rut_asignado = gb.rut_norm
                WHERE gb.nombre_ejecutivo_norm IS NOT NULL
                GROUP BY
                    pn.fecha_carga,
                    a.cartera,
                    gb.nombre_ejecutivo_norm,
                    gb.usuario_gestion_norm,
                    a.folio_credito
            ),
            por_ejecutivo AS (
                SELECT
                    fecha_carga,
                    cartera,
                    nombre_ejecutivo,
                    usuario_gestion,
                    SUM(recupero) AS recupero_gestor
                FROM contrato_recupero
                GROUP BY fecha_carga, cartera, nombre_ejecutivo, usuario_gestion
            )
            INSERT INTO {TABLE_PERFORMANCE_CACHE} (
                source_file_asignacion,
                source_file_pagos,
                fecha_carga,
                cartera,
                nombre_ejecutivo,
                usuario_gestion,
                recupero_gestor,
                recupero_total_cartera,
                aporte_grupal_pct
            )
            SELECT
                ?,
                ?,
                fecha_carga,
                cartera,
                nombre_ejecutivo,
                usuario_gestion,
                recupero_gestor,
                SUM(recupero_gestor) OVER (PARTITION BY fecha_carga, cartera) AS recupero_total_cartera,
                CAST(
                    CASE
                        WHEN SUM(recupero_gestor) OVER (PARTITION BY fecha_carga, cartera) = 0 THEN 0
                        ELSE 100.0 * recupero_gestor / SUM(recupero_gestor) OVER (PARTITION BY fecha_carga, cartera)
                    END AS DECIMAL(9,2)
                ) AS aporte_grupal_pct
            FROM por_ejecutivo
            """,
            (pagos_source, asignacion_source, asignacion_source, pagos_source),
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
