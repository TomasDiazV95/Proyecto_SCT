import os
import re
from decimal import Decimal
from io import BytesIO
from pathlib import Path

import bench_recarga
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
# Desde octubre 2026 el bench diario llega partido en un archivo por tramo de mora
# (YYYYMMDD_PHOENIX (TELEFONIA)_C1_BENCH_MORA_TEMPRANA.XLSX, _C2_, _C3_), con las mismas columnas.
CICLOS = ("C1", "C2", "C3")
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
        "Encrypt=no;"
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


def should_skip_load(current_source_file: str, fecha_visor) -> bool:
    # Si el archivo ya esta cargado pero fue resubido al visor, se borran sus filas y se recarga.
    # El archivo de fin de mes conserva la primera carga marcada como pre-cierre (version_carga).
    with connect() as cn:
        cargar = bench_recarga.debe_cargar(
            cn.cursor(), TABLE, current_source_file, fecha_visor, conservar_precierre=True
        )
        cn.commit()
    return not cargar


def archivos_por_ciclo() -> dict[str, dict[str, Path]]:
    """Archivos del bench partido por tramo: {foto YYYYMMDD: {ciclo: archivo}}.

    Si un tramo de la misma foto esta mas de una vez, queda el de carga mas reciente en el visor."""
    esperado = bench_recarga.tokens_bench(BENCH_PATTERN.replace("*", " ").replace("?", " "))
    fotos: dict[str, dict[str, Path]] = {}
    for p in BENCH_FOLDER.iterdir():
        match = re.match(r"(\d{8})(?!\d)", p.name)
        if not match or not p.is_file() or p.suffix.lower() not in (".xlsx", ".xls") or p.name.startswith("~$"):
            continue
        ciclo = bench_recarga.tokens_bench(p.name) - esperado
        if len(ciclo) != 1 or not ciclo <= set(CICLOS) or not esperado <= bench_recarga.tokens_bench(p.name):
            continue
        partes = fotos.setdefault(match.group(1), {})
        (nombre_ciclo,) = ciclo
        if nombre_ciclo not in partes or p.stat().st_mtime > partes[nombre_ciclo].stat().st_mtime:
            partes[nombre_ciclo] = p
    return fotos


def pick_files_to_process() -> list[tuple[str, list[Path]]]:
    """Cargas a procesar como (source_file, archivos), de la mas antigua a la mas nueva segun su carga
    en el visor (el pre-cierre antes que el cierre).

    El bench en un solo archivo se carga con su nombre. El bench partido por tramo se carga como una
    sola foto, con el nombre que tenia el archivo unico (sin el tramo): asi todo lo que lee la tabla
    sigue viendo un source_file por foto."""
    if not BENCH_FOLDER.exists():
        return []
    cargas = [(p.name, [p]) for p in bench_recarga.archivos_bench(BENCH_FOLDER, BENCH_PATTERN)]
    sufijo = BENCH_PATTERN.replace("*", "").replace("?", "").strip()
    for foto, partes in archivos_por_ciclo().items():
        faltan = [ciclo for ciclo in CICLOS if ciclo not in partes]
        if faltan:
            print(f"ADVERTENCIA: la foto {foto} no trae los tramos {', '.join(faltan)}; se carga con los que hay.")
        cargas.append((f"{foto}_{sufijo}", [partes[ciclo] for ciclo in CICLOS if ciclo in partes]))
    return sorted(cargas, key=lambda carga: (fecha_visor_carga(carga[1]), carga[0]))


def fecha_visor_carga(archivos: list[Path]):
    # Si resuben un solo tramo, la foto completa se vuelve a cargar.
    return max(bench_recarga.fecha_visor_archivo(p) for p in archivos)


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

    for source_file, excel_files in files:
        fecha_visor = fecha_visor_carga(excel_files)
        if should_skip_load(source_file, fecha_visor):
            continue

        df = pd.concat([read_excel(str(p), SHEET_NAME) for p in excel_files], ignore_index=True)
        df = df.where(pd.notnull(df), None)

        print(f"Archivo: {source_file}")
        if len(excel_files) > 1:
            print("Tramos unidos: " + ", ".join(p.name for p in excel_files))
        print(f"Filas: {len(df)} | Columnas: {len(df.columns)}")

        df = data_cleaners.apply_fuzzy_matching_to_cobrador(df, threshold=90)

        found_numeric = [c for c in df.columns if col_is_numeric(c)]
        print("Columnas numericas detectadas:", found_numeric if found_numeric else "ninguna")

        ensure_table_and_columns(df)
        insert_append(df, source_file)
        with connect() as cn:
            bench_recarga.registrar_fecha_visor(cn.cursor(), TABLE, source_file, fecha_visor)
            cn.commit()


if __name__ == "__main__":
    main()
