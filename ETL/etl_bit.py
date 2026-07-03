import argparse
import calendar
import json
import os
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd
import pyodbc
import requests
from dotenv import load_dotenv


CASTIGO_TABLE = "dbo.tmp_BIT_castigo"
CONTENCION_TABLE = "dbo.tmp_BIT_contencion"
CARTERIZADO_TABLE = "dbo.tmp_BIT_carterizado"
CASTIGO_PATTERN = re.compile(r"^Detalle_Recuperos_Castigo_(\d{6}|\d{8})(?:_(PRECIERRE|CIERRE))?\.xlsx$", re.IGNORECASE)
CONTENCION_PATTERN = re.compile(r"^Seguimiento_Metas_PHOENIX_(\d{8})\.xlsx$", re.IGNORECASE)
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
RESERVED_METADATA_COLUMNS = {"ID", "PERIODO", "SOURCE_FILE", "FECHA_CARGA"}
UF_FALLBACK_BY_PERIOD = {
    "2026-06": Decimal("40820.31"),
}


@dataclass
class BitSources:
    cont: pd.DataFrame
    cart: pd.DataFrame
    cont_source_file: str
    cart_source_file: str
    cont_period: str | None = None
    castigo: pd.DataFrame | None = None
    castigo_source_file: str | None = None
    castigo_period: str | None = None


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
        "Encrypt=yes;"
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
            ultimo_registro = max(registros_mes, key=lambda item: str(item.get("fecha") or ""))
            ultimo_registro_dia = int(str(ultimo_registro.get("fecha") or "")[8:10])
            valor = soft_decimal(ultimo_registro.get("valor"))
            if valor is not None and valor > 0:
                warning = None
                if ultimo_registro_dia != ultimo_dia:
                    warning = (
                        f"Mindicador no devolvio el ultimo dia calendario de {periodo}. "
                        f"Se esperaba dia {ultimo_dia:02d} y se uso el ultimo valor disponible del mes: dia {ultimo_registro_dia:02d}"
                    )
                return valor, "mindicador", warning
            api_error = f"Mindicador devolvio un valor UF invalido para {periodo}"
        elif not api_error:
            api_error = f"Mindicador no devolvio registros UF para {periodo}"
    except Exception as exc:
        api_error = f"Error consultando Mindicador para {periodo}: {exc}"

    fallback_value = UF_FALLBACK_BY_PERIOD.get(periodo)
    if fallback_value is not None and fallback_value > 0:
        return fallback_value, "fallback", api_error

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


def ensure_castigo_table(cur: pyodbc.Cursor, excel_columns: list[str]) -> tuple[list[str], list[str]]:
    requested_columns = [str(col) for col in excel_columns]
    if "GC_CASTIGO" not in {col.upper() for col in requested_columns}:
        requested_columns.append("GC_CASTIGO")
    return ensure_dynamic_table(cur, CASTIGO_TABLE, requested_columns, CASTIGO_NUMERIC_COLUMNS)


def ensure_carterizado_table(cur: pyodbc.Cursor, excel_columns: list[str]) -> tuple[list[str], list[str]]:
    excel_columns, added_columns = ensure_dynamic_table(
        cur,
        CARTERIZADO_TABLE,
        excel_columns,
        include_source_file=False,
    )
    existing = get_table_columns(cur, CARTERIZADO_TABLE)
    if "SOURCE_FILE" in existing:
        cur.execute(f"ALTER TABLE {CARTERIZADO_TABLE} DROP COLUMN [source_file]")
    return excel_columns, added_columns


def prepare_contencion_dataframe(df: pd.DataFrame, periodo: str | None = None) -> tuple[pd.DataFrame, dict[str, object]]:
    if not periodo:
        raise RuntimeError("No se puede preparar contencion sin periodo para resolver MONTO_UF")

    resolved_monto_uf, uf_source, uf_error = resolve_monto_uf(periodo)
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


def resolve_castigo_source(folder: Path) -> tuple[Path, str, str]:
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

    return castigo_path, source_file, castigo_period


def _read_sources(file_path: str | None, folder_path: str | None) -> BitSources:
    if file_path:
        xlsx = Path(file_path)
        if not xlsx.exists():
            raise FileNotFoundError(f"No existe archivo: {xlsx}")
        cont = load_sheet(xlsx, "CONTENCION")
        cart = load_sheet(xlsx, "CARTERIZADO")
        cont_period = extract_contencion_period(xlsx.name) if CONTENCION_PATTERN.match(xlsx.name) else None
        return BitSources(
            cont=cont,
            cart=cart,
            cont_source_file=xlsx.name,
            cart_source_file=xlsx.name,
            cont_period=cont_period,
        )

    if folder_path:
        folder = Path(folder_path)
        if not folder.exists():
            raise FileNotFoundError(f"No existe carpeta: {folder}")
        cont_path = find_unique_file(folder, "Seguimiento_Metas_PHOENIX_*.xlsx", "contencion", required=True)
        cart_path = folder / "CARTERIZADO.xlsx"
        if not cont_path.exists() or not cart_path.exists():
            raise FileNotFoundError(
                "En la carpeta deben existir un archivo Seguimiento_Metas_PHOENIX_*.xlsx y CARTERIZADO.xlsx"
            )

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
        cart = load_sheet(cart_path, 0)
        castigo_path, castigo_source_file, castigo_period = resolve_castigo_source(folder)
        castigo_df = load_sheet(castigo_path, 0)
        if not len(castigo_df.columns):
            raise RuntimeError(f"El archivo de castigo {castigo_source_file} no tiene columnas.")

        return BitSources(
            cont=cont,
            cart=cart,
            cont_source_file=cont_source_name,
            cart_source_file=cart_path.name,
            cont_period=cont_period,
            castigo=castigo_df,
            castigo_source_file=castigo_source_file,
            castigo_period=castigo_period,
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


def insert_castigo(cur: pyodbc.Cursor, periodo: str, castigo_df: pd.DataFrame, source_file: str) -> int:
    excel_columns, added_columns = ensure_castigo_table(cur, [str(col) for col in castigo_df.columns])
    cur.execute(f"DELETE FROM {CASTIGO_TABLE} WHERE periodo = ?", (periodo,))

    insert_columns = ["periodo", "source_file"] + excel_columns
    values_sql = ", ".join("?" for _ in insert_columns)
    cols_sql = ", ".join(quote_ident(col) for col in insert_columns)
    insert_sql = f"INSERT INTO {CASTIGO_TABLE} ({cols_sql}) VALUES ({values_sql})"

    castigo_rows = []
    for _, row in castigo_df.iterrows():
        out = [periodo, source_file]
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
) -> tuple[int, int]:
    if table_name == CARTERIZADO_TABLE and not include_source_file:
        excel_columns, added_columns = ensure_carterizado_table(cur, [str(col) for col in df.columns])
    else:
        excel_columns, added_columns = ensure_dynamic_table(
            cur,
            table_name,
            [str(col) for col in df.columns],
            numeric_columns,
            include_source_file=include_source_file,
        )
    cur.execute(f"DELETE FROM {table_name} WHERE periodo = ?", (periodo,))

    insert_columns = ["periodo"] + (["source_file"] if include_source_file else []) + excel_columns
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


def run(periodo: str | None, file_path: str | None, folder_path: str | None) -> None:
    sources = _read_sources(file_path, folder_path)
    cont_period = resolve_contencion_period(periodo, sources)
    castigo_period = sources.castigo_period
    skipped_cart_rows = 0
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
        )
        cart_rows, skipped_cart_rows = insert_dynamic_sheet(
            cur,
            CARTERIZADO_TABLE,
            cont_period,
            sources.cart,
            sources.cart_source_file,
            skip_null_column="NRO_OPERACION",
            include_source_file=False,
        )

        castigo_rows = insert_castigo(cur, castigo_period, sources.castigo, sources.castigo_source_file)

        cn.commit()

    print(
        f"Carga BIT completada. periodo_contencion={cont_period}, contencion={cont_rows}, "
        f"carterizado={cart_rows}, carterizado_omitido_sin_nro_operacion={skipped_cart_rows}, "
        f"contencion_mto_cuota_invalido={contencion_stats['invalid_mto_cuota']}, "
        f"contencion_monto_uf_invalido_original={contencion_stats['invalid_monto_uf_original']}, "
        f"contencion_monto_uf_aplicado={contencion_stats['monto_uf_aplicado']}, "
        f"contencion_monto_uf_source={contencion_stats['monto_uf_source']}, "
        f"contencion_monto_uf_error={contencion_stats['monto_uf_error'] or 'none'}, "
        f"contencion_tramo_desconocido={contencion_stats['unknown_tramo']}, "
        f"periodo_castigo={castigo_period}, castigo={castigo_rows}"
    )


if __name__ == "__main__":
    load_env_files()
    parser = argparse.ArgumentParser(description="Carga ETL BIT")
    parser.add_argument("--file", required=False, help="Ruta del Excel SEGUIMIENTO BIT")
    parser.add_argument(
        "--folder",
        required=False,
        help="Carpeta con Seguimiento_Metas_PHOENIX_*.xlsx, CARTERIZADO.xlsx y Detalle_Recuperos_Castigo_*.xlsx",
    )
    parser.add_argument(
        "--periodo",
        required=False,
        help="Periodo YYYY-MM solo para contencion/carterizado. Si se omite, se infiere del nombre del archivo.",
    )
    args = parser.parse_args()
    run(args.periodo, args.file, args.folder)
