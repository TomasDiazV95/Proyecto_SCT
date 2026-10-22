import argparse
import calendar
import json
import os
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pandas as pd
import pyodbc
import requests
from dotenv import load_dotenv


CASTIGO_TABLE = "dbo.tmp_BIT_castigo"
CONTENCION_TABLE = "dbo.tmp_BIT_contencion"
ASIGNACION_TABLE = "dbo.tmp_BIT_asignacion"
ASIGNACION_MENSUAL_TABLE = "dbo.tmp_BIT_asignacion_mensual"
# Contencion y castigo guardan una foto por archivo (fecha_archivo). Castigo tiene una vista con la ultima de cada
# periodo; contencion ya no: la web toma directo de la tabla la de mayor fecha_archivo (la vista vieja se elimina).
CONTENCION_VIEW_ELIMINADA = "dbo.vw_BIT_contencion_ultima"
CASTIGO_VIEW = "dbo.vw_BIT_castigo_ultima"
ASIGNACION_REMOTE_DIR = "/Entrada/Carga_Cobranza"
SEGUIMIENTOS_REMOTE_DIR = "/Entrada/Seguimientos"
MESES_HISTORICO = 4  # mes actual + 3 anteriores, los que compara el KPI Operacional
DEFAULT_BIT_FOLDER = Path(r"C:\Users\Analista de Datos\Desktop\AUTOMATIZACION\BIT")
CASTIGO_PATTERN = re.compile(r"^Detalle_Recuperos_Castigo_(\d{6}|\d{8})(?:_(PRECIERRE|CIERRE))?\.xlsx$", re.IGNORECASE)
CONTENCION_PATTERN = re.compile(r"^Seguimiento_Metas_PHOENIX_(\d{8})\.xlsx$", re.IGNORECASE)
ASIGNACION_PATTERN = re.compile(r"^ASIGNACION_PHOENIX_(\d{8})\.csv$", re.IGNORECASE)
CASTIGO_NUMERIC_COLUMNS = {"MTO_RECUPERO_FINAL", "GC_CASTIGO"}
CONTENCION_NUMERIC_COLUMNS = {
    "MTO_CUOTA",
    "MONTO_UF",
    "MTO_CUOTA_UF",
    "GASTO_COBRANZA",
    "GC_MUY_BAJO",
    "GC_BAJO",
    "GC_ESPERADO",
    "GC_SOBRE",
}
ASIGNACION_NUMERIC_COLUMNS = {
    "DEUDA_TOTAL",
    "CUOTAS_MOROSAS",
    "NRO_TOTAL_CUOTAS",
    "MTO_CUOTA",
    "DEUDA_FAC_PESOS_TOTAL",
    "PAGO_MINIMO",
    "PORC_DCTO_PUT",
    "PORC_DCTO_AP",
    "PORC_ABONO_EXIGIDO_AP",
    "PORC_ABONO_EXIGIDO_RENE",
    "MONTO_MORA_TOTAL",
}
RESERVED_METADATA_COLUMNS = {"ID", "PERIODO", "SOURCE_FILE", "FECHA_CARGA", "FECHA_ARCHIVO"}
UF_FALLBACK_BY_PERIOD = {
    "2026-06": Decimal("40820.31"),
}
UF_CACHE_PATH = Path(__file__).resolve().parents[1] / "Logs" / "bit_uf_cache.json"


@dataclass
class BitSources:
    cont: pd.DataFrame
    cont_source_file: str
    cont_period: str | None = None
    castigo: pd.DataFrame | None = None
    castigo_source_file: str | None = None
    castigo_period: str | None = None
    castigo_mtime: datetime | None = None
    asignacion: pd.DataFrame | None = None
    asignacion_source_file: str | None = None
    asignacion_period: str | None = None


def load_env_files() -> None:
    root_dir = Path(__file__).resolve().parents[1]
    load_dotenv(root_dir / ".env")
    load_dotenv(root_dir / "ETL" / ".env")


def pick_driver() -> str:
    available = list(pyodbc.drivers())
    preferred = [
        os.getenv("DB_DRIVER"),
        "ODBC Driver 18 for SQL Server",
        "ODBC Driver 17 for SQL Server",
        "SQL Server",
    ]
    for d in preferred:
        if d and d in available:
            return d
    raise RuntimeError(f"No hay driver ODBC para SQL Server. Drivers encontrados: {available}")


def connect() -> pyodbc.Connection:
    driver = pick_driver()
    server = os.getenv("DB_SERVER")
    database = os.getenv("DB_NAME")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    if not all([server, database, user, password]):
        raise RuntimeError("Faltan DB_SERVER, DB_NAME, DB_USER o DB_PASSWORD")

    conn_str = (
        f"Driver={{{driver}}};"
        f"Server={server};"
        f"Database={database};"
        f"Uid={user};"
        f"Pwd={password};"
        "TrustServerCertificate=yes;"
        "Encrypt=no;"
    )
    return pyodbc.connect(conn_str)


def normalize_col(name: str) -> str:
    return str(name).strip().upper().replace(" ", "_")


def load_sheet(path: Path, sheet_name: str | int) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=sheet_name, dtype=object, engine="openpyxl")
    df.columns = [normalize_col(c) for c in df.columns]
    duplicated = df.columns[df.columns.duplicated()].tolist()
    if duplicated:
        raise RuntimeError(f"Columnas duplicadas despues de normalizar en {path.name}: {duplicated}")
    return df.where(pd.notnull(df), None)


def load_csv(path: Path) -> pd.DataFrame:
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            df = pd.read_csv(path, sep=";", dtype=str, keep_default_na=False, encoding=encoding)
            break
        except UnicodeDecodeError as exc:
            last_error = exc
    else:
        raise RuntimeError(f"No se pudo leer {path.name}: {last_error}")
    df.columns = [normalize_col(c) for c in df.columns]
    duplicated = df.columns[df.columns.duplicated()].tolist()
    if duplicated:
        raise RuntimeError(f"Columnas duplicadas despues de normalizar en {path.name}: {duplicated}")
    return df


def clean_cell(value: object) -> object:
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def to_decimal(value: object, field_name: str = "valor") -> Decimal | None:
    value = clean_cell(value)
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return Decimal(str(value))

    text = str(value).strip().replace(" ", "")
    if not text:
        return None

    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(".", "").replace(",", ".")

    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise RuntimeError(f"No se pudo convertir a numero el valor '{value}' de {field_name}") from exc


def soft_decimal(value: object) -> Decimal | None:
    value = clean_cell(value)
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return Decimal(str(value))

    text = str(value).strip().replace(" ", "")
    if not text:
        return None

    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(".", "").replace(",", ".")

    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def parse_period(periodo: str) -> tuple[int, int]:
    match = re.fullmatch(r"(\d{4})-(\d{2})", str(periodo).strip())
    if not match:
        raise RuntimeError(f"Periodo invalido para UF: {periodo}. Se esperaba YYYY-MM")
    return int(match.group(1)), int(match.group(2))


def _period_sort_key(periodo: str) -> tuple[int, int]:
    return parse_period(periodo)


def _read_uf_cache() -> dict[str, str]:
    if not UF_CACHE_PATH.exists():
        return {}
    try:
        payload = json.loads(UF_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    return {str(key): str(value) for key, value in payload.items()}


def _write_uf_cache(cache: dict[str, str]) -> None:
    UF_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    UF_CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _save_uf_cache(periodo: str, valor: Decimal) -> None:
    if valor <= 0:
        return
    cache = _read_uf_cache()
    cache[str(periodo)] = str(valor)
    _write_uf_cache(cache)


def _lookup_cached_uf(periodo: str) -> tuple[Decimal | None, str | None]:
    cache = _read_uf_cache()
    exact = soft_decimal(cache.get(periodo))
    if exact is not None and exact > 0:
        return exact, "cache_exact"

    eligible = []
    for key, raw_value in cache.items():
        try:
            if _period_sort_key(key) <= _period_sort_key(periodo):
                value = soft_decimal(raw_value)
                if value is not None and value > 0:
                    eligible.append((key, value))
        except Exception:
            continue
    if eligible:
        key, value = max(eligible, key=lambda item: _period_sort_key(item[0]))
        return value, f"cache_previous:{key}"
    return None, None


def _lookup_db_uf(periodo: str) -> tuple[Decimal | None, str | None]:
    try:
        with connect() as cn:
            cur = cn.cursor()
            cur.execute(
                f"""
                SELECT TOP 1 MONTO_UF
                FROM {CONTENCION_TABLE}
                WHERE periodo = ? AND MONTO_UF IS NOT NULL AND MONTO_UF > 0
                ORDER BY ID DESC
                """,
                (periodo,),
            )
            row = cur.fetchone()
            if row:
                value = soft_decimal(row[0])
                if value is not None and value > 0:
                    return value, "db_exact"

            cur.execute(
                f"""
                SELECT TOP 1 periodo, MONTO_UF
                FROM {CONTENCION_TABLE}
                WHERE periodo <= ? AND MONTO_UF IS NOT NULL AND MONTO_UF > 0
                ORDER BY periodo DESC, ID DESC
                """,
                (periodo,),
            )
            row = cur.fetchone()
            if row:
                value = soft_decimal(row[1])
                source_period = str(row[0]).strip()
                if value is not None and value > 0:
                    return value, f"db_previous:{source_period}"
    except Exception:
        return None, None
    return None, None


def resolve_monto_uf(periodo: str) -> tuple[Decimal, str, str | None]:
    year, month = parse_period(periodo)
    api_url = f"https://mindicador.cl/api/uf/{year}"
    api_error = None

    try:
        response = requests.get(api_url, timeout=20)
        response.raise_for_status()
        payload = response.json()
        serie = payload.get("serie") or []
        registros_mes = [item for item in serie if str(item.get("fecha") or "")[5:7] == f"{month:02d}"]
        if registros_mes:
            ultimo_dia = calendar.monthrange(year, month)[1]
            registros_validos = []
            for item in registros_mes:
                valor = soft_decimal(item.get("valor"))
                fecha = str(item.get("fecha") or "")
                if valor is not None and valor > 0 and fecha:
                    registros_validos.append((fecha, valor))

            if registros_validos:
                ultimo_registro_fecha, ultimo_registro_valor = max(registros_validos, key=lambda item: item[0])
                ultimo_registro_dia = int(ultimo_registro_fecha[8:10])
                if ultimo_registro_dia == ultimo_dia:
                    _save_uf_cache(periodo, ultimo_registro_valor)
                    return ultimo_registro_valor, "mindicador", None
                _save_uf_cache(periodo, ultimo_registro_valor)
                return (
                    ultimo_registro_valor,
                    "mindicador_last_available",
                    (
                        f"Mindicador no devolvio el ultimo dia calendario de {periodo}. "
                        f"Se esperaba dia {ultimo_dia:02d} y se uso el ultimo dia disponible {ultimo_registro_dia:02d}"
                    ),
                )
            api_error = f"Mindicador no devolvio un valor UF valido para {periodo}"
        elif not api_error:
            api_error = f"Mindicador no devolvio registros UF para {periodo}"
    except Exception as exc:
        api_error = f"Error consultando Mindicador para {periodo}: {exc}"

    fallback_value = UF_FALLBACK_BY_PERIOD.get(periodo)
    if fallback_value is not None and fallback_value > 0:
        _save_uf_cache(periodo, fallback_value)
        return fallback_value, "fallback", api_error

    cached_value, cached_source = _lookup_cached_uf(periodo)
    if cached_value is not None and cached_source:
        return cached_value, cached_source, api_error

    db_value, db_source = _lookup_db_uf(periodo)
    if db_value is not None and db_source:
        _save_uf_cache(periodo, db_value)
        return db_value, db_source, api_error

    raise RuntimeError(
        f"No se pudo obtener MONTO_UF para {periodo} desde Mindicador y no existe fallback local. "
        f"Detalle: {api_error}"
    )


def resolve_contencion_tramo(value: object) -> str | None:
    prefix = str(clean_cell(value) or "").upper()[:2]
    if prefix in {"T1", "T2", "T3"}:
        return "30-90"
    if prefix in {"T4", "T5", "T6", "T7"}:
        return "90+"
    return None


def contiene_aplica(value: object) -> bool:
    cleaned = clean_cell(value)
    if cleaned is None:
        return False

    parsed = soft_decimal(cleaned)
    if parsed is not None:
        return parsed == Decimal("1")

    return str(cleaned).strip().upper() in {"1", "SI", "SÍ", "TRUE", "X"}


def calculate_gasto_cobranza(mto_cuota_uf: Decimal, monto_uf: Decimal, contiene: object) -> Decimal:
    if not contiene_aplica(contiene):
        return Decimal("0")
    if mto_cuota_uf <= 0 or monto_uf <= 0:
        return Decimal("0")

    if mto_cuota_uf <= Decimal("10"):
        gasto_base_uf = mto_cuota_uf * Decimal("0.09")
    elif mto_cuota_uf <= Decimal("50"):
        gasto_base_uf = (Decimal("10") * Decimal("0.09")) + ((mto_cuota_uf - Decimal("10")) * Decimal("0.06"))
    else:
        gasto_base_uf = (
        (Decimal("10") * Decimal("0.09"))
        + (Decimal("40") * Decimal("0.06"))
        + ((mto_cuota_uf - Decimal("50")) * Decimal("0.03"))
        )

    return gasto_base_uf * monto_uf


def read_metadata(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"No se pudo leer metadata {path.name}: {exc}") from exc


def find_unique_file(folder: Path, glob_pattern: str, label: str, required: bool = True) -> Path | None:
    matches = sorted(
        [path for path in folder.glob(glob_pattern) if path.is_file()],
        key=lambda path: (path.stat().st_mtime, path.name),
        reverse=True,
    )
    if not matches:
        if required:
            raise FileNotFoundError(f"No se encontro archivo {label} con patron {glob_pattern} en {folder}")
        return None
    if len(matches) > 1:
        names = ", ".join(path.name for path in matches)
        raise RuntimeError(f"Se encontraron multiples archivos {label} en {folder}: {names}")
    return matches[0]


def extract_castigo_period(file_name: str) -> str:
    match = CASTIGO_PATTERN.match(Path(file_name).name)
    if not match:
        raise RuntimeError(
            "No se pudo obtener el periodo del archivo castigo. "
            f"Nombre recibido: {file_name}. Se esperaba Detalle_Recuperos_Castigo_YYYYMM[DD][_PRECIERRE|_CIERRE].xlsx"
        )
    raw_period = match.group(1)
    return f"{raw_period[:4]}-{raw_period[4:6]}"


def extract_contencion_period(file_name: str) -> str:
    match = CONTENCION_PATTERN.match(Path(file_name).name)
    if not match:
        raise RuntimeError(
            "Nombre de contencion invalido. "
            f"Se esperaba Seguimiento_Metas_PHOENIX_YYYYMMDD.xlsx y se encontro {file_name}"
        )
    raw_date = match.group(1)
    return f"{raw_date[:4]}-{raw_date[4:6]}"


def fecha_de_archivo(file_name: str, mtime: datetime | None = None) -> date:
    """Fecha de la foto: la del nombre (YYYYMMDD). Castigo YYYYMM_PRECIERRE / YYYYMM_CIERRE = ultimo dia del mes
    (misma foto: el cierre pisa al precierre). Castigo YYYYMM sin variante = fecha del archivo en el SFTP o hoy,
    sin pasar del ultimo dia del mes (para no quedar despues del cierre)."""
    name = Path(file_name).name
    match = re.search(r"_(\d{8})(?=[_.])", name)
    if match:
        return datetime.strptime(match.group(1), "%Y%m%d").date()
    match = re.search(r"_(\d{4})(\d{2})(?:_(PRECIERRE|CIERRE))?\.", name, re.IGNORECASE)
    if not match:
        return (mtime or datetime.now()).date()
    year, month = int(match.group(1)), int(match.group(2))
    fin_mes = date(year, month, calendar.monthrange(year, month)[1])
    return fin_mes if match.group(3) else min((mtime or datetime.now()).date(), fin_mes)


def extract_asignacion_period(file_name: str) -> str:
    match = ASIGNACION_PATTERN.match(Path(file_name).name)
    if not match:
        raise RuntimeError(
            "Nombre de asignacion invalido. "
            f"Se esperaba ASIGNACION_PHOENIX_YYYYMMDD.csv y se encontro {file_name}"
        )
    raw_date = match.group(1)
    return f"{raw_date[:4]}-{raw_date[4:6]}"


def resolve_asignacion_source(folder: Path) -> tuple[Path, str, str] | None:
    asignacion_path = find_unique_file(folder, "ASIGNACION_PHOENIX_*.csv", "asignacion", required=False)
    if asignacion_path is None:
        return None

    source_file = asignacion_path.name
    asignacion_period = extract_asignacion_period(source_file)

    metadata = read_metadata(folder / "ASIGNACION.meta.json")
    metadata_name = str(metadata.get("original_filename") or "").strip()
    if metadata_name and metadata_name != source_file:
        raise RuntimeError(
            f"Metadata de asignacion inconsistente. original_filename={metadata_name}, archivo={source_file}"
        )
    metadata_period = str(metadata.get("periodo_detectado") or "").strip()
    if metadata_period and metadata_period != asignacion_period:
        raise RuntimeError(
            f"Metadata de asignacion inconsistente. periodo_detectado={metadata_period}, archivo={source_file}"
        )

    return asignacion_path, source_file, asignacion_period


def quote_ident(name: str) -> str:
    return f"[{str(name).replace(']', ']]')}]"


def split_table_name(table_name: str) -> tuple[str, str]:
    if "." in table_name:
        schema, table = table_name.split(".", 1)
        return schema, table
    return "dbo", table_name


def get_table_columns(cur: pyodbc.Cursor, table_name: str) -> set[str]:
    schema, table = split_table_name(table_name)
    cur.execute(
        """
        SELECT COLUMN_NAME
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?
        """,
        (schema, table),
    )
    return {str(row[0]).upper() for row in cur.fetchall()}


def is_table_column_nullable(cur: pyodbc.Cursor, table_name: str, column_name: str) -> bool:
    schema, table = split_table_name(table_name)
    cur.execute(
        """
        SELECT IS_NULLABLE
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ? AND UPPER(COLUMN_NAME) = UPPER(?)
        """,
        (schema, table, column_name),
    )
    row = cur.fetchone()
    return bool(row and str(row[0]).strip().upper() == "YES")


def sanitize_excel_columns(excel_columns: list[str]) -> list[str]:
    clean_columns = []
    for col in excel_columns:
        normalized = str(col).strip().upper()
        if not normalized or normalized in RESERVED_METADATA_COLUMNS:
            continue
        clean_columns.append(str(col))
    return clean_columns


def ensure_dynamic_table(
    cur: pyodbc.Cursor,
    table_name: str,
    excel_columns: list[str],
    numeric_columns: set[str] | None = None,
    include_source_file: bool = True,
) -> tuple[list[str], list[str]]:
    if not excel_columns:
        raise RuntimeError(f"El archivo para {table_name} no tiene columnas para cargar.")

    numeric_columns = {str(col).upper() for col in (numeric_columns or set())}
    excel_columns = sanitize_excel_columns(excel_columns)
    if not excel_columns:
        raise RuntimeError(f"Todas las columnas del archivo para {table_name} entran en conflicto con metadatos.")

    _schema, table = split_table_name(table_name)
    existing = get_table_columns(cur, table_name)

    if not existing:
        dynamic_cols = ",\n                    ".join(
            f"{quote_ident(col)} {'DECIMAL(18,2)' if col.upper() in numeric_columns else 'NVARCHAR(MAX)'} NULL"
            for col in excel_columns
        )
        cur.execute(
            f"""
            CREATE TABLE {table_name} (
                id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                periodo NVARCHAR(7) NOT NULL,
                {"source_file NVARCHAR(260) NOT NULL," if include_source_file else ""}
                fecha_carga DATE NOT NULL CONSTRAINT DF_{table}_fecha_carga DEFAULT (CONVERT(date, GETDATE())),
                {dynamic_cols}
            )
            """
        )
        return excel_columns, list(excel_columns)

    missing = [col for col in excel_columns if col.upper() not in existing]
    for col in missing:
        column_type = "DECIMAL(18,2)" if col.upper() in numeric_columns else "NVARCHAR(MAX)"
        cur.execute(f"ALTER TABLE {table_name} ADD {quote_ident(col)} {column_type} NULL")

    return excel_columns, missing


def ensure_fecha_archivo(cur: pyodbc.Cursor, table_name: str) -> None:
    """Columna fecha_archivo (fecha de la foto) con su indice. Las filas cargadas antes la toman del nombre del
    archivo con la regla de fecha_de_archivo y, si el nombre no la trae, de la fecha de carga."""
    if "FECHA_ARCHIVO" in get_table_columns(cur, table_name):
        return
    _schema, table = split_table_name(table_name)
    cur.execute(f"ALTER TABLE {table_name} ADD fecha_archivo DATE NULL")
    cur.execute(
        f"""
        UPDATE {table_name}
        SET fecha_archivo = COALESCE(
            TRY_CAST(SUBSTRING(source_file, NULLIF(PATINDEX('%[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]%', source_file), 0), 8) AS date),
            CASE WHEN UPPER(source_file) LIKE '%[_][0-9][0-9][0-9][0-9][0-9][0-9][_]%CIERRE.XLSX' THEN
                EOMONTH(TRY_CAST(SUBSTRING(source_file, PATINDEX('%[_][0-9][0-9][0-9][0-9][0-9][0-9][_]%', source_file) + 1, 6) + '01' AS date))
            END,
            -- Castigo YYYYMM sin variante: la fecha de carga, sin pasar del ultimo dia del mes.
            CASE WHEN UPPER(source_file) LIKE '%[_][0-9][0-9][0-9][0-9][0-9][0-9].XLSX'
                  AND fecha_carga > EOMONTH(TRY_CAST(SUBSTRING(source_file, PATINDEX('%[_][0-9][0-9][0-9][0-9][0-9][0-9].%', source_file) + 1, 6) + '01' AS date))
                THEN EOMONTH(TRY_CAST(SUBSTRING(source_file, PATINDEX('%[_][0-9][0-9][0-9][0-9][0-9][0-9].%', source_file) + 1, 6) + '01' AS date))
            END,
            fecha_carga
        )
        """
    )
    # Lo cargado antes era la foto vigente del periodo (cierre incluido, con cargas manuales): en un mes cerrado
    # queda como una sola foto al ultimo dia del mes, no con la fecha en que se cargo despues.
    cur.execute(
        f"""
        UPDATE {table_name}
        SET fecha_archivo = EOMONTH(TRY_CAST(periodo + '-01' AS date))
        WHERE fecha_archivo > EOMONTH(TRY_CAST(periodo + '-01' AS date))
        """
    )
    cur.execute(f"CREATE INDEX IX_{table}_periodo_fecha_archivo ON {table_name}(periodo, fecha_archivo)")


def ensure_vistas(cur: pyodbc.Cursor) -> None:
    """Vista con la ultima foto de castigo de cada periodo. Se recrea en cada carga para que tome las columnas
    nuevas de los archivos."""
    cur.execute(f"IF OBJECT_ID('{CONTENCION_VIEW_ELIMINADA}', 'V') IS NOT NULL DROP VIEW {CONTENCION_VIEW_ELIMINADA}")
    for view_name, table_name in ((CASTIGO_VIEW, CASTIGO_TABLE),):
        if "FECHA_ARCHIVO" not in get_table_columns(cur, table_name):
            continue
        cur.execute(f"IF OBJECT_ID('{view_name}', 'V') IS NOT NULL DROP VIEW {view_name}")
        cur.execute(
            f"""
            CREATE VIEW {view_name} AS
            SELECT t.*
            FROM {table_name} t
            WHERE t.fecha_archivo = (SELECT MAX(u.fecha_archivo) FROM {table_name} u WHERE u.periodo = t.periodo)
            """
        )


def fotos_cargadas(cur: pyodbc.Cursor, table_name: str) -> dict[tuple[str, str], set[str]]:
    """(periodo, fecha_archivo ISO) -> archivos (en mayusculas) con que se cargo esa foto."""
    if "FECHA_ARCHIVO" not in get_table_columns(cur, table_name):
        return {}
    cur.execute(f"SELECT DISTINCT periodo, fecha_archivo, source_file FROM {table_name} WHERE fecha_archivo IS NOT NULL")
    out: dict[tuple[str, str], set[str]] = {}
    for row in cur.fetchall():
        # El driver "SQL Server" devuelve las fechas como texto.
        out.setdefault((str(row[0]).strip(), str(row[1])[:10]), set()).add(str(row[2] or "").strip().upper())
    return out


CASTIGO_VARIANTES = {"": 0, "PRECIERRE": 1, "CIERRE": 2}


def variante_castigo(file_name: str) -> int:
    """Prioridad del castigo dentro de una misma foto: CIERRE > PRECIERRE > sin variante."""
    match = CASTIGO_PATTERN.match(Path(str(file_name)).name)
    return CASTIGO_VARIANTES.get((match.group(2) or "").upper(), 0) if match else 0


def ensure_castigo_table(cur: pyodbc.Cursor, excel_columns: list[str]) -> tuple[list[str], list[str]]:
    requested_columns = [str(col) for col in excel_columns]
    if "GC_CASTIGO" not in {col.upper() for col in requested_columns}:
        requested_columns.append("GC_CASTIGO")
    return ensure_dynamic_table(cur, CASTIGO_TABLE, requested_columns, CASTIGO_NUMERIC_COLUMNS)


def prepare_contencion_dataframe(
    df: pd.DataFrame,
    periodo: str | None = None,
    uf: tuple[Decimal, str, str | None] | None = None,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """uf: resultado de resolve_monto_uf(periodo) ya resuelto (la carga historica lo reutiliza entre archivos)."""
    if not periodo:
        raise RuntimeError("No se puede preparar contencion sin periodo para resolver MONTO_UF")

    resolved_monto_uf, uf_source, uf_error = uf or resolve_monto_uf(periodo)
    prepared = df.copy()
    stats = {
        "invalid_mto_cuota": 0,
        "invalid_monto_uf_original": 0,
        "monto_uf_aplicado": 0,
        "unknown_tramo": 0,
        "monto_uf_source": uf_source,
        "monto_uf_error": uf_error,
    }
    for column in ["MTO_CUOTA_UF", "GASTO_COBRANZA", "GC_MUY_BAJO", "GC_BAJO", "GC_ESPERADO", "GC_SOBRE"]:
        if column not in prepared.columns:
            prepared[column] = None

    for index, row in prepared.iterrows():
        cuota = soft_decimal(row.get("MTO_CUOTA"))
        original_monto_uf = soft_decimal(row.get("MONTO_UF"))
        if original_monto_uf is None or original_monto_uf <= 0:
            stats["invalid_monto_uf_original"] += 1
        monto_uf = resolved_monto_uf
        prepared.at[index, "MONTO_UF"] = monto_uf
        stats["monto_uf_aplicado"] += 1
        tramo = resolve_contencion_tramo(row.get("TRAMO_PROYECTADO_NUEVO"))

        if cuota is None:
            stats["invalid_mto_cuota"] += 1
        if tramo is None:
            stats["unknown_tramo"] += 1

        if cuota is None or monto_uf <= 0:
            prepared.at[index, "MTO_CUOTA_UF"] = Decimal("0")
        else:
            prepared.at[index, "MTO_CUOTA_UF"] = cuota / monto_uf

        mto_cuota_uf = prepared.at[index, "MTO_CUOTA_UF"]
        gasto_cobranza = calculate_gasto_cobranza(mto_cuota_uf, monto_uf, row.get("CONTIENE"))
        prepared.at[index, "GASTO_COBRANZA"] = gasto_cobranza

        if tramo == "30-90":
            prepared.at[index, "GC_MUY_BAJO"] = Decimal("0.20")
            prepared.at[index, "GC_BAJO"] = Decimal("0.25")
            prepared.at[index, "GC_ESPERADO"] = Decimal("0.30")
            prepared.at[index, "GC_SOBRE"] = Decimal("0.35")
        elif tramo == "90+":
            prepared.at[index, "GC_MUY_BAJO"] = Decimal("0.45")
            prepared.at[index, "GC_BAJO"] = Decimal("0.50")
            prepared.at[index, "GC_ESPERADO"] = Decimal("0.60")
            prepared.at[index, "GC_SOBRE"] = Decimal("0.65")
        else:
            prepared.at[index, "GC_MUY_BAJO"] = None
            prepared.at[index, "GC_BAJO"] = None
            prepared.at[index, "GC_ESPERADO"] = None
            prepared.at[index, "GC_SOBRE"] = None

    return prepared, stats


def resolve_castigo_source(folder: Path) -> tuple[Path, str, str, datetime | None]:
    metadata_path = folder / "CASTIGO.meta.json"
    metadata = read_metadata(metadata_path)
    castigo_path = find_unique_file(folder, "Detalle_Recuperos_Castigo_*.xlsx", "castigo", required=True)

    source_file = castigo_path.name
    castigo_period = extract_castigo_period(source_file)

    metadata_period = str(metadata.get("periodo_detectado") or "").strip()
    if metadata_period and metadata_period != castigo_period:
        raise RuntimeError(
            f"Metadata de castigo inconsistente. periodo_detectado={metadata_period}, archivo={source_file}"
        )
    metadata_name = str(metadata.get("original_filename") or "").strip()
    if metadata_name and metadata_name != source_file:
        raise RuntimeError(
            f"Metadata de castigo inconsistente. original_filename={metadata_name}, archivo={source_file}"
        )

    # Fecha del archivo en el SFTP: es la fecha de la foto cuando el nombre solo trae el mes.
    try:
        castigo_mtime = datetime.fromisoformat(str(metadata.get("sftp_mtime") or "").strip())
    except ValueError:
        castigo_mtime = None

    return castigo_path, source_file, castigo_period, castigo_mtime


def _read_sources(file_path: str | None, folder_path: str | None) -> BitSources:
    if folder_path:
        folder = Path(folder_path)
        if not folder.exists():
            raise FileNotFoundError(f"No existe carpeta: {folder}")
        cont_path = find_unique_file(folder, "Seguimiento_Metas_PHOENIX_*.xlsx", "contencion", required=True)

        cont_source_name = cont_path.name
        cont_period = extract_contencion_period(cont_source_name)
        metadata_path = folder / "CONTENCION.meta.json"
        if metadata_path.exists():
            metadata = read_metadata(metadata_path)
            candidate = str(metadata.get("original_filename") or "").strip()
            if candidate and candidate != cont_source_name:
                raise RuntimeError(
                    f"Metadata de contencion inconsistente. original_filename={candidate}, archivo={cont_source_name}"
                )
            metadata_period = str(metadata.get("periodo_detectado") or "").strip()
            if metadata_period and metadata_period != cont_period:
                raise RuntimeError(
                    f"Metadata de contencion inconsistente. periodo_detectado={metadata_period}, archivo={cont_source_name}"
                )

        cont = load_sheet(cont_path, 0)
        castigo_path, castigo_source_file, castigo_period, castigo_mtime = resolve_castigo_source(folder)
        castigo_df = load_sheet(castigo_path, 0)
        if not len(castigo_df.columns):
            raise RuntimeError(f"El archivo de castigo {castigo_source_file} no tiene columnas.")

        asignacion_df = None
        asignacion_source_file = None
        asignacion_period = None
        asignacion_source = resolve_asignacion_source(folder)
        if asignacion_source:
            asignacion_path, asignacion_source_file, asignacion_period = asignacion_source
            asignacion_df = load_csv(asignacion_path)

        return BitSources(
            cont=cont,
            cont_source_file=cont_source_name,
            cont_period=cont_period,
            castigo=castigo_df,
            castigo_source_file=castigo_source_file,
            castigo_period=castigo_period,
            castigo_mtime=castigo_mtime,
            asignacion=asignacion_df,
            asignacion_source_file=asignacion_source_file,
            asignacion_period=asignacion_period,
        )

    if file_path:
        xlsx = Path(file_path)
        if not xlsx.exists():
            raise FileNotFoundError(f"No existe archivo: {xlsx}")
        cont = load_sheet(xlsx, "CONTENCION")
        cont_period = extract_contencion_period(xlsx.name) if CONTENCION_PATTERN.match(xlsx.name) else None
        return BitSources(
            cont=cont,
            cont_source_file=xlsx.name,
            cont_period=cont_period,
        )

    raise RuntimeError("Debes indicar --file o --folder")


def resolve_contencion_period(requested_periodo: str | None, sources: BitSources) -> str:
    if requested_periodo:
        periodo = str(requested_periodo).strip()
        if sources.cont_period and sources.cont_period != periodo:
            raise RuntimeError(
                f"El archivo contencion {sources.cont_source_file} corresponde al periodo {sources.cont_period} "
                f"y no al periodo solicitado {periodo}"
            )
        return periodo

    if sources.cont_period:
        return sources.cont_period

    raise RuntimeError(
        "No se pudo definir el periodo de contencion automaticamente desde el nombre del archivo. "
        "Indica --periodo o usa un archivo con nombre Seguimiento_Metas_PHOENIX_YYYYMMDD.xlsx."
    )


def insert_castigo(cur: pyodbc.Cursor, periodo: str, castigo_df: pd.DataFrame, source_file: str, fecha_archivo: date) -> int:
    """Reemplaza solo la foto de fecha_archivo del periodo; las de otros dias se conservan. Un archivo no pisa a
    otro de mayor variante en la misma foto (el CIERRE pisa al PRECIERRE, nunca al reves)."""
    excel_columns, added_columns = ensure_castigo_table(cur, [str(col) for col in castigo_df.columns])
    ensure_fecha_archivo(cur, CASTIGO_TABLE)
    # Fechas como texto ISO: el driver ODBC "SQL Server" no enlaza parametros date.
    fecha_iso = fecha_archivo.isoformat()
    cur.execute(
        f"SELECT DISTINCT source_file FROM {CASTIGO_TABLE} WHERE periodo = ? AND fecha_archivo = ?",
        (periodo, fecha_iso),
    )
    mayor = [row[0] for row in cur.fetchall() if variante_castigo(row[0]) > variante_castigo(source_file)]
    if mayor:
        print(f"{source_file} no se carga: la foto {fecha_iso} de {periodo} ya tiene {mayor[0]}.")
        return 0
    cur.execute(f"DELETE FROM {CASTIGO_TABLE} WHERE periodo = ? AND fecha_archivo = ?", (periodo, fecha_iso))

    insert_columns = ["periodo", "fecha_archivo", "source_file"] + excel_columns
    values_sql = ", ".join("?" for _ in insert_columns)
    cols_sql = ", ".join(quote_ident(col) for col in insert_columns)
    insert_sql = f"INSERT INTO {CASTIGO_TABLE} ({cols_sql}) VALUES ({values_sql})"

    castigo_rows = []
    for _, row in castigo_df.iterrows():
        out = [periodo, fecha_iso, source_file]
        for col in excel_columns:
            if col.upper() == "GC_CASTIGO":
                out.append(Decimal("0.25"))
                continue

            value = row.get(col)
            if col.upper() in CASTIGO_NUMERIC_COLUMNS:
                out.append(to_decimal(value, col))
            else:
                out.append(clean_cell(value))
        castigo_rows.append(tuple(out))

    if castigo_rows:
        cur.executemany(insert_sql, castigo_rows)

    if added_columns:
        print(f"{CASTIGO_TABLE}: columnas nuevas detectadas y agregadas: {', '.join(added_columns)}")

    return len(castigo_rows)


def insert_dynamic_sheet(
    cur: pyodbc.Cursor,
    table_name: str,
    periodo: str,
    df: pd.DataFrame,
    source_file: str,
    numeric_columns: set[str] | None = None,
    skip_null_column: str | None = None,
    include_source_file: bool = True,
    replace_period: bool = True,
    fecha_archivo: date | None = None,
) -> tuple[int, int]:
    """Con fecha_archivo se reemplaza solo la foto de ese dia del periodo; sin ella, el periodo completo
    (si replace_period)."""
    excel_columns, added_columns = ensure_dynamic_table(
        cur,
        table_name,
        [str(col) for col in df.columns],
        numeric_columns,
        include_source_file=include_source_file,
    )
    # Fechas como texto ISO: el driver ODBC "SQL Server" no enlaza parametros date.
    fecha_iso = fecha_archivo.isoformat() if fecha_archivo else None
    if fecha_iso:
        ensure_fecha_archivo(cur, table_name)
        cur.execute(f"DELETE FROM {table_name} WHERE periodo = ? AND fecha_archivo = ?", (periodo, fecha_iso))
    elif replace_period:
        cur.execute(f"DELETE FROM {table_name} WHERE periodo = ?", (periodo,))

    insert_columns = (
        ["periodo"]
        + (["fecha_archivo"] if fecha_iso else [])
        + (["source_file"] if include_source_file else [])
        + excel_columns
    )
    values_sql = ", ".join("?" for _ in insert_columns)
    cols_sql = ", ".join(quote_ident(col) for col in insert_columns)
    insert_sql = f"INSERT INTO {table_name} ({cols_sql}) VALUES ({values_sql})"

    numeric_columns = {str(col).upper() for col in (numeric_columns or set())}
    skip_null_column = str(skip_null_column or "").upper() or None
    rows = []
    skipped_rows = 0
    for _, row in df.iterrows():
        if skip_null_column and clean_cell(row.get(skip_null_column)) is None:
            skipped_rows += 1
            continue

        out = [periodo]
        if fecha_iso:
            out.append(fecha_iso)
        if include_source_file:
            out.append(source_file)
        for col in excel_columns:
            value = row.get(col)
            if col.upper() in numeric_columns:
                out.append(soft_decimal(value))
            else:
                out.append(clean_cell(value))
        rows.append(tuple(out))

    if rows:
        cur.executemany(insert_sql, rows)

    if added_columns:
        print(f"{table_name}: columnas nuevas detectadas y agregadas: {', '.join(added_columns)}")

    return len(rows), skipped_rows


def _connect_bit_sftp():
    import paramiko

    host = (os.getenv("BIT_SFTP_HOST") or os.getenv("SFTP_HOST") or "").strip()
    port = int((os.getenv("BIT_SFTP_PORT") or os.getenv("SFTP_PORT") or "22").strip() or "22")
    user = (os.getenv("BIT_SFTP_USER") or os.getenv("SFTP_USER") or "").strip()
    password = (os.getenv("BIT_SFTP_PASSWORD") or os.getenv("SFTP_PASSWORD") or "").strip()
    if not host or not user or not password:
        raise RuntimeError("Faltan variables BIT_SFTP_HOST, BIT_SFTP_USER o BIT_SFTP_PASSWORD en .env")

    transport = paramiko.Transport((host, port))
    transport.connect(username=user, password=password)
    return transport, paramiko.SFTPClient.from_transport(transport)


def sync_asignacion_cierre(periodos: list[str] | None = None) -> None:
    """Sincroniza desde el SFTP la asignacion de los meses con recupero castigo cargado.

    - ASIGNACION_TABLE: cada mes cerrado queda con la ultima asignacion diaria del mes (la del ultimo dia).
    - ASIGNACION_MENSUAL_TABLE: consolidado del mes con todo RUT asignado algun dia; cada RUT queda con las
      filas del ultimo archivo diario en que aparece (los que pagan salen de la asignacion antes del cierre).
    Solo descarga cuando el ultimo archivo del mes en el SFTP no es el que esta cargado.
    """
    periodo_actual = date.today().strftime("%Y-%m")

    with connect() as cn:
        cn.autocommit = False
        cur = cn.cursor()

        if periodos is None:
            cur.execute(f"SELECT DISTINCT periodo FROM {CASTIGO_TABLE} WHERE periodo IS NOT NULL")
            periodos = [str(row[0]).strip() for row in cur.fetchall()]
        pendientes = sorted({p for p in periodos if p})
        if not pendientes:
            return

        def loaded_files(table_name: str) -> dict[str, set[str]]:
            loaded: dict[str, set[str]] = {}
            if get_table_columns(cur, table_name):
                cur.execute(f"SELECT DISTINCT periodo, source_file FROM {table_name}")
                for row in cur.fetchall():
                    loaded.setdefault(str(row[0]).strip(), set()).add(str(row[1]).strip().upper())
            return loaded

        cargados = loaded_files(ASIGNACION_TABLE)
        cargados_mensual = loaded_files(ASIGNACION_MENSUAL_TABLE)

        transport, sftp = _connect_bit_sftp()
        try:
            archivos_por_periodo: dict[str, list[str]] = {}
            for entry in sftp.listdir_attr(ASIGNACION_REMOTE_DIR):
                match = ASIGNACION_PATTERN.match(entry.filename)
                if not match:
                    continue
                raw_date = match.group(1)
                archivos_por_periodo.setdefault(f"{raw_date[:4]}-{raw_date[4:6]}", []).append(entry.filename)

            for periodo in pendientes:
                # El nombre termina en YYYYMMDD: el orden alfabetico (sin mayusculas) es el cronologico.
                archivos = sorted(archivos_por_periodo.get(periodo, []), key=str.upper)
                if not archivos:
                    print(f"Advertencia: no hay ASIGNACION_PHOENIX_*.csv de {periodo} en el SFTP; no se actualizo la asignacion.")
                    continue
                cierre = archivos[-1]
                falta_cierre = periodo < periodo_actual and cargados.get(periodo) != {cierre.upper()}
                falta_mensual = cierre.upper() not in cargados_mensual.get(periodo, set())
                if not falta_cierre and not falta_mensual:
                    continue

                diarios: list[pd.DataFrame] = []
                with TemporaryDirectory() as tmp_dir:
                    for archivo in archivos if falta_mensual else [cierre]:
                        local_path = Path(tmp_dir) / archivo
                        sftp.get(f"{ASIGNACION_REMOTE_DIR}/{archivo}", str(local_path))
                        diario = load_csv(local_path)
                        diario["__ARCHIVO"] = archivo
                        diarios.append(diario)

                if falta_cierre:
                    rows, _ = insert_dynamic_sheet(
                        cur,
                        ASIGNACION_TABLE,
                        periodo,
                        diarios[-1].drop(columns="__ARCHIVO"),
                        cierre,
                        numeric_columns=ASIGNACION_NUMERIC_COLUMNS,
                    )
                    print(f"Asignacion de cierre {periodo} cargada desde {cierre}: {rows} filas.")

                if falta_mensual:
                    todo = pd.concat(diarios, ignore_index=True).fillna("")
                    todo["__RUT"] = todo["RUT"].astype(str).str.strip()
                    todo = todo[todo["__RUT"] != ""]
                    ultimo_archivo = todo.groupby("__RUT")["__ARCHIVO"].transform("max")
                    todo = todo[todo["__ARCHIVO"] == ultimo_archivo]

                    rows = 0
                    replace_period = True
                    for archivo, grupo in todo.groupby("__ARCHIVO", sort=True):
                        inserted, _ = insert_dynamic_sheet(
                            cur,
                            ASIGNACION_MENSUAL_TABLE,
                            periodo,
                            grupo.drop(columns=["__ARCHIVO", "__RUT"]),
                            str(archivo),
                            numeric_columns=ASIGNACION_NUMERIC_COLUMNS,
                            replace_period=replace_period,
                        )
                        replace_period = False
                        rows += inserted
                    print(
                        f"Asignacion mensual {periodo} consolidada desde {len(archivos)} archivos "
                        f"({archivos[0]} a {cierre}): {rows} filas, {todo['__RUT'].nunique()} RUT."
                    )

                cn.commit()
        finally:
            sftp.close()
            transport.close()


def _periodos_recientes(meses: int) -> set[str]:
    year, month = date.today().year, date.today().month
    out = set()
    for _ in range(meses):
        out.add(f"{year:04d}-{month:02d}")
        year, month = (year - 1, 12) if month == 1 else (year, month - 1)
    return out


def cargar_historico(meses: int = MESES_HISTORICO) -> None:
    """Carga desde el SFTP las fotos de contencion y castigo de los ultimos `meses` meses que falten.

    Una foto por (periodo, fecha_archivo); un archivo ya cargado en su foto no se vuelve a descargar. Con varios castigos de una
    misma fecha queda el de mayor variante (CIERRE > PRECIERRE > base) y luego el mas reciente. Un castigo sin dia
    en el nombre que se sobrescribe en el SFTP solo trae su ultima version.
    """
    periodos = _periodos_recientes(meses)

    transport, sftp = _connect_bit_sftp()
    try:
        contencion: dict[tuple[str, date], str] = {}
        castigo: dict[tuple[str, date], tuple[tuple, str]] = {}
        for entry in sftp.listdir_attr(SEGUIMIENTOS_REMOTE_DIR):
            name = entry.filename
            mtime = datetime.fromtimestamp(entry.st_mtime)
            if CONTENCION_PATTERN.match(name):
                periodo = extract_contencion_period(name)
                if periodo in periodos:
                    contencion[(periodo, fecha_de_archivo(name))] = name
                continue
            match = CASTIGO_PATTERN.match(name)
            if match:
                periodo = extract_castigo_period(name)
                if periodo in periodos:
                    key = (periodo, fecha_de_archivo(name, mtime))
                    rank = (variante_castigo(name), mtime)
                    if key not in castigo or rank > castigo[key][0]:
                        castigo[key] = (rank, name)

        with connect() as cn:
            cn.autocommit = False
            cur = cn.cursor()
            for table_name in (CONTENCION_TABLE, CASTIGO_TABLE):
                if get_table_columns(cur, table_name):
                    ensure_fecha_archivo(cur, table_name)
            cn.commit()
            cargadas = {t: fotos_cargadas(cur, t) for t in (CONTENCION_TABLE, CASTIGO_TABLE)}
            uf_por_periodo: dict[str, tuple[Decimal, str, str | None]] = {}

            with TemporaryDirectory() as tmp_dir:
                for (periodo, fecha), name in sorted(contencion.items()):
                    if name.upper() in cargadas[CONTENCION_TABLE].get((periodo, fecha.isoformat()), set()):
                        continue
                    local_path = Path(tmp_dir) / name
                    sftp.get(f"{SEGUIMIENTOS_REMOTE_DIR}/{name}", str(local_path))
                    if periodo not in uf_por_periodo:
                        uf_por_periodo[periodo] = resolve_monto_uf(periodo)
                    prepared, _ = prepare_contencion_dataframe(load_sheet(local_path, 0), periodo, uf_por_periodo[periodo])
                    rows, _ = insert_dynamic_sheet(
                        cur,
                        CONTENCION_TABLE,
                        periodo,
                        prepared,
                        name,
                        numeric_columns=CONTENCION_NUMERIC_COLUMNS,
                        fecha_archivo=fecha,
                    )
                    cn.commit()
                    local_path.unlink(missing_ok=True)
                    print(f"Contencion {periodo} foto {fecha.isoformat()} cargada desde {name}: {rows} filas.")

                for (periodo, fecha), (_rank, name) in sorted(castigo.items()):
                    if name.upper() in cargadas[CASTIGO_TABLE].get((periodo, fecha.isoformat()), set()):
                        continue
                    local_path = Path(tmp_dir) / name
                    sftp.get(f"{SEGUIMIENTOS_REMOTE_DIR}/{name}", str(local_path))
                    rows = insert_castigo(cur, periodo, load_sheet(local_path, 0), name, fecha)
                    cn.commit()
                    local_path.unlink(missing_ok=True)
                    print(f"Castigo {periodo} foto {fecha.isoformat()} cargada desde {name}: {rows} filas.")

            ensure_vistas(cur)
            cn.commit()
    finally:
        sftp.close()
        transport.close()


def run(periodo: str | None, file_path: str | None, folder_path: str | None) -> None:
    sources = _read_sources(file_path, folder_path)
    cont_period = resolve_contencion_period(periodo, sources)
    castigo_period = sources.castigo_period
    prepared_cont, contencion_stats = prepare_contencion_dataframe(sources.cont, cont_period)

    with connect() as cn:
        cn.autocommit = False
        cur = cn.cursor()

        cont_rows, _ = insert_dynamic_sheet(
            cur,
            CONTENCION_TABLE,
            cont_period,
            prepared_cont,
            sources.cont_source_file,
            numeric_columns=CONTENCION_NUMERIC_COLUMNS,
            fecha_archivo=fecha_de_archivo(sources.cont_source_file),
        )

        castigo_rows = insert_castigo(
            cur,
            castigo_period,
            sources.castigo,
            sources.castigo_source_file,
            fecha_de_archivo(sources.castigo_source_file, sources.castigo_mtime),
        )
        ensure_vistas(cur)

        # Igual que contencion: se reemplaza el periodo completo, asi queda solo el ultimo archivo del mes.
        asignacion_rows = 0
        if sources.asignacion is not None:
            asignacion_rows, _ = insert_dynamic_sheet(
                cur,
                ASIGNACION_TABLE,
                sources.asignacion_period,
                sources.asignacion,
                sources.asignacion_source_file,
                numeric_columns=ASIGNACION_NUMERIC_COLUMNS,
            )
        else:
            print(f"Advertencia: no se encontro archivo ASIGNACION_PHOENIX_*.csv; {ASIGNACION_TABLE} no se actualizo.")

        cn.commit()

    print(
        f"Carga BIT completada. periodo_contencion={cont_period}, contencion={cont_rows}, "
        f"contencion_mto_cuota_invalido={contencion_stats['invalid_mto_cuota']}, "
        f"contencion_monto_uf_invalido_original={contencion_stats['invalid_monto_uf_original']}, "
        f"contencion_monto_uf_aplicado={contencion_stats['monto_uf_aplicado']}, "
        f"contencion_monto_uf_source={contencion_stats['monto_uf_source']}, "
        f"contencion_monto_uf_error={contencion_stats['monto_uf_error'] or 'none'}, "
        f"contencion_tramo_desconocido={contencion_stats['unknown_tramo']}, "
        f"periodo_castigo={castigo_period}, castigo={castigo_rows}, "
        f"periodo_asignacion={sources.asignacion_period or 'none'}, asignacion={asignacion_rows}"
    )

    # Asignacion de cierre de los meses cerrados y consolidado mensual; lo que falte se trae del SFTP.
    try:
        sync_asignacion_cierre()
    except Exception as exc:
        print(f"Advertencia: no se pudo sincronizar la asignacion de cierre: {exc}")


if __name__ == "__main__":
    load_env_files()
    parser = argparse.ArgumentParser(description="Carga ETL BIT")
    parser.add_argument("--file", required=False, help="Ruta del Excel SEGUIMIENTO BIT")
    parser.add_argument(
        "--periodo",
        required=False,
        help="Periodo YYYY-MM solo para contencion. Si se omite, se infiere del nombre del archivo.",
    )
    parser.add_argument(
        "--asignacion-cierre",
        action="store_true",
        help="Solo sincroniza desde el SFTP la asignacion de cierre y el consolidado mensual.",
    )
    parser.add_argument(
        "--historico",
        action="store_true",
        help="Solo carga desde el SFTP las fotos diarias de contencion y castigo que falten.",
    )
    parser.add_argument(
        "--meses",
        type=int,
        default=MESES_HISTORICO,
        help=f"Meses hacia atras para --historico, contando el actual (por defecto {MESES_HISTORICO}).",
    )
    args = parser.parse_args()
    if args.historico:
        cargar_historico(args.meses)
    elif args.asignacion_cierre:
        sync_asignacion_cierre()
    else:
        run(args.periodo, args.file, str(DEFAULT_BIT_FOLDER))

