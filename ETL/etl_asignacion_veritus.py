"""Asignacion VERITUS (cartera castigo) -> dbo.tmp_asignacion_veritus, para el KPI Operacional.

El archivo es 'cartera_Firma_Phoenix_YYYY-MM-DD*.xlsx' (hoja Cartera): la fila 1 trae nombres tecnicos
(rut, nombre, ad1...) y la fila 2 los nombres reales (RUT, ID Contrato, Deuda castigada, BANCO, CARTERA, LOTE...);
se usan los de la fila 2. Una fila por operacion (ID Contrato).

Periodo = mes de FECHA_ASIGNACION del archivo (o el YYYYMM del argumento). Se reemplaza el periodo completo:
queda solo la ultima asignacion del mes.

Uso:
  python ETL/etl_asignacion_veritus.py                       # el cartera_Firma_Phoenix_*.xlsx mas reciente
  python ETL/etl_asignacion_veritus.py "ruta\\archivo.xlsx"   # un archivo
  python ETL/etl_asignacion_veritus.py "ruta\\archivo.xlsx" 202611
"""

import os
import re
import sys
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
from etl_asignacion_forum import clean_text, connect, sql_ident  # noqa: E402


ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")
load_dotenv(ROOT_DIR / "ETL" / ".env")

# Carpeta y patron del Excel: se pueden definir en .env; por defecto la raiz del proyecto.
ASIGNACION_FOLDER = (os.getenv("ASIGNACION_VERITUS_FOLDER") or "").strip() or str(ROOT_DIR)
ASIGNACION_PATTERN = (os.getenv("ASIGNACION_VERITUS_PATTERN") or "").strip() or "cartera_Firma_Phoenix_*.xlsx"
SHEET_NAME = "Cartera"
HEADER_ROW = 1  # fila 2 del Excel

TABLE = "dbo.tmp_asignacion_veritus"
BATCH_SIZE = 5000

# Columnas con tipo propio (nombres ya normalizados); el resto se guarda como texto.
INTEGER_COLUMNS = {"RUT"}
DECIMAL_COLUMNS = {
    "DEUDA_CASTIGADA", "IMPORTE_CONCEDIDO", "VALOR_CONDONACION_MAX", "INTERESES", "GASTOS", "SALDO_FINAL",
    "VALOR_VEHICULO", "DEUDA_TOTAL_RUT", "PUT_TOTAL_A_PAGAR", "PLAN_PAGO_TOTAL_A_PAGAR",
}
DATE_COLUMNS = {
    "FECHA_CASTIGO", "FECHA_OTORGAMIENTO_DEL_CREDITO", "FECHA_ULTIMO_PAGO", "FECHA_ASIGNACION", "FECHA_RECALL",
}
REQUIRED = ("RUT", "ID_CONTRATO", "DEUDA_CASTIGADA", "BANCO", "CARTERA", "FECHA_ASIGNACION")


def normalize_excel_col(value: object) -> str:
    """'Fecha último Pago' -> 'FECHA_ULTIMO_PAGO' (sin tildes ni simbolos)."""
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^0-9A-Za-z]+", "_", text).strip("_")
    return text.upper()


def clean_decimal(value: object) -> Decimal | None:
    text = clean_text(value)
    if text is None:
        return None
    try:
        return Decimal(text.replace(",", "."))
    except InvalidOperation:
        return None


def clean_date(value: object) -> date | None:
    if value is None or value is pd.NA:
        return None
    if isinstance(value, (pd.Timestamp, datetime)):
        return None if pd.isna(value) else value.date()
    if isinstance(value, date):
        return value
    text = clean_text(value)
    if text is None:
        return None
    parsed = pd.to_datetime(text, errors="coerce", dayfirst=True)
    return None if pd.isna(parsed) else parsed.date()


def sql_type_for(column: str) -> str:
    if column in INTEGER_COLUMNS:
        return "DECIMAL(38,0) NULL"
    if column in DECIMAL_COLUMNS:
        return "DECIMAL(38,4) NULL"
    if column in DATE_COLUMNS:
        return "DATE NULL"
    if column == "DV":
        return "NVARCHAR(1) NULL"
    return "NVARCHAR(MAX) NULL"


def cleaner_for(column: str):
    if column in INTEGER_COLUMNS or column in DECIMAL_COLUMNS:
        return clean_decimal
    if column in DATE_COLUMNS:
        return clean_date
    return clean_text


def resolve_excel(argv: list[str]) -> Path:
    if len(argv) > 1 and not re.fullmatch(r"\d{6}", argv[1].strip()):
        return Path(argv[1].strip().strip('"').lstrip("& ").strip("'"))
    files = [p for p in Path(ASIGNACION_FOLDER).glob(ASIGNACION_PATTERN) if not p.name.startswith("~$")]
    if not files:
        raise FileNotFoundError(f"No hay archivos {ASIGNACION_PATTERN} en {ASIGNACION_FOLDER}")
    return max(files, key=lambda p: p.stat().st_mtime)


def read_excel(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"No existe el Excel en: {path}")
    df = pd.read_excel(BytesIO(path.read_bytes()), sheet_name=SHEET_NAME, header=HEADER_ROW, dtype=object,
                       engine="openpyxl")
    df.columns = [normalize_excel_col(c) for c in df.columns]
    df = df.loc[:, [bool(c) and not c.startswith("UNNAMED") for c in df.columns]]
    duplicated = df.columns[df.columns.duplicated()].tolist()
    if duplicated:
        raise RuntimeError(f"Columnas duplicadas en el Excel: {duplicated}")
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise RuntimeError(f"La hoja '{SHEET_NAME}' no tiene las columnas: {missing}")
    return df.dropna(how="all")


def resolve_periodo(argv: list[str], df: pd.DataFrame) -> str:
    explicito = next((a.strip() for a in argv[1:] if re.fullmatch(r"\d{6}", a.strip())), None)
    if explicito:
        periodo = explicito
    else:
        fechas = {clean_date(v) for v in df["FECHA_ASIGNACION"]} - {None}
        if not fechas:
            raise RuntimeError("El archivo no trae FECHA_ASIGNACION: indica el periodo YYYYMM como argumento")
        periodo = max(fechas).strftime("%Y%m")
    if not re.fullmatch(r"\d{4}(0[1-9]|1[0-2])", periodo):
        raise RuntimeError(f"PERIODO invalido: {periodo}. Se esperaba YYYYMM")
    return periodo


def ensure_table(cur, excel_columns: list[str]) -> list[str]:
    cur.execute(
        f"""
        IF OBJECT_ID('{TABLE}', 'U') IS NULL
        BEGIN
            CREATE TABLE {TABLE} (
                id_asignacion_veritus BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                fecha_carga DATE NOT NULL CONSTRAINT DF_tmp_asignacion_veritus_fecha_carga DEFAULT (CONVERT(date, GETDATE())),
                ts_carga DATETIME2(0) NOT NULL CONSTRAINT DF_tmp_asignacion_veritus_ts_carga DEFAULT (SYSDATETIME()),
                source_file NVARCHAR(260) NULL,
                [PERIODO] NVARCHAR(6) NULL
            );
            CREATE INDEX IX_tmp_asignacion_veritus_periodo ON {TABLE}([PERIODO]);
        END
        """
    )
    schema, table_name = TABLE.split(".")
    cur.execute(
        """
        SELECT c.name FROM sys.columns c
        INNER JOIN sys.tables t ON c.object_id = t.object_id
        INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
        WHERE s.name = ? AND t.name = ?
        """,
        (schema, table_name),
    )
    existing = {str(row[0]).upper() for row in cur.fetchall()}
    added = []
    for column in excel_columns:
        if column.upper() not in existing:
            cur.execute(f"ALTER TABLE {TABLE} ADD {sql_ident(column)} {sql_type_for(column)};")
            added.append(column)
    return added


def main() -> None:
    excel_path = resolve_excel(sys.argv)
    source_file = excel_path.name
    print(f"Archivo asignacion VERITUS: {excel_path}")

    df = read_excel(excel_path)
    periodo = resolve_periodo(sys.argv, df)
    print(f"Hoja: {SHEET_NAME} | Periodo: {periodo} | Filas: {len(df)} | Columnas: {len(df.columns)}")

    sin_rut = int(df["RUT"].map(clean_decimal).isna().sum())
    if sin_rut:
        print(f"Aviso: {sin_rut} filas sin RUT valido (quedan fuera del KPI)")

    excel_columns = list(df.columns)
    cleaners = [cleaner_for(col) for col in excel_columns]
    insert_cols = ["source_file", "PERIODO"] + excel_columns
    sql = (f"INSERT INTO {TABLE} ({','.join(map(sql_ident, insert_cols))}) "
           f"VALUES ({','.join(['?'] * len(insert_cols))})")
    rows = [
        tuple([source_file, periodo] + [clean(value) for clean, value in zip(cleaners, row)])
        for row in df.itertuples(index=False, name=None)
    ]

    with connect() as cn:
        cn.autocommit = False
        cur = cn.cursor()
        added = ensure_table(cur, excel_columns)
        cn.commit()
        if added:
            print(f"{TABLE}: columnas agregadas: {len(added)}")

        # Se reemplaza el periodo completo: queda solo la ultima asignacion del mes.
        cur.execute(f"DELETE FROM {TABLE} WHERE [PERIODO] = ?", (periodo,))
        deleted = cur.rowcount
        inserted = 0
        for i in range(0, len(rows), BATCH_SIZE):
            batch = rows[i : i + BATCH_SIZE]
            cur.executemany(sql, batch)
            inserted += len(batch)
            print(f"OK batch {i + 1}-{i + len(batch)}")
        cn.commit()

    print(f"OK: periodo {periodo} reemplazado ({deleted} filas anteriores), insertadas {inserted} filas en {TABLE}")


if __name__ == "__main__":
    main()
