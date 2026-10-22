"""Carga el bench de mora tardia telefonia en dbo.tmp_bench_STC_tel.

    YYYYMMDD_BENCH_MORA_TARDIA_PHOENIX (TELEFONIA).xlsx  (carpeta EXTRAS del visor)

Misma logica que etl_bench_stc.py (columnas fld_ dinamicas, recarga y pre-cierre con bench_recarga),
pero sin las columnas de metas: solo se cargan las columnas del Excel.
"""

import os
from pathlib import Path

import pandas as pd
import pyodbc

import bench_recarga
import corregir_nombres
import data_cleaners
from etl_bench_stc import (
    NUMERIC_COLS,
    clean_numeric_to_str,
    col_is_numeric,
    connect,
    get_bench_files,
    normalize_excel_col,
    read_excel,
    require_env,
    sql_ident,
    sql_type_for,
)

BENCH_FOLDER = Path(require_env("BENCH_STC_FOLDER"))
BENCH_PATTERN = require_env("BENCH_STC_TEL_PATTERN")
# Vacio = primera hoja del Excel.
SHEET_NAME = os.getenv("BENCH_STC_TEL_SHEET_NAME", "").strip() or None

TABLE = "dbo.tmp_bench_STC_tel"
BATCH_SIZE = 200


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
                id_bench_stc_tel BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                fecha_carga  DATE        NOT NULL CONSTRAINT DF_tmp_bench_STC_tel_fecha_carga DEFAULT (CONVERT(date, GETDATE())),
                ts_carga     DATETIME2(0) NOT NULL CONSTRAINT DF_tmp_bench_STC_tel_ts_carga    DEFAULT (SYSDATETIME()),
                source_file  NVARCHAR(260) NULL
            );
            CREATE INDEX IX_tmp_bench_STC_tel_fecha_carga ON {TABLE}(fecha_carga);
        END
        """)
        cn.commit()

        # 2) columnas existentes
        schema, table_name = TABLE.split(".")
        cur.execute("""
            SELECT c.name
            FROM sys.columns c
            INNER JOIN sys.tables t ON c.object_id = t.object_id
            INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
            WHERE s.name = ? AND t.name = ?
        """, (schema, table_name))
        existing = {row[0] for row in cur.fetchall()}

        # 3) agregar columnas faltantes
        alters = [
            f"ALTER TABLE {TABLE} ADD {sql_ident(fld)} {sql_type_for(original)};"
            for original, fld in zip(excel_cols, fld_cols)
            if fld not in existing
        ]
        if alters:
            print(f"Agregando {len(alters)} columnas nuevas a {TABLE}...")
            for stmt in alters:
                cur.execute(stmt)
            cn.commit()

        # 4) asegurar que las numericas queden DECIMAL(38,0)
        for n in NUMERIC_COLS:
            colname = f"fld_{n}"
            if colname in existing or colname in fld_cols:
                cur.execute(f"ALTER TABLE {TABLE} ALTER COLUMN {sql_ident(colname)} DECIMAL(38,0) NULL;")
        cn.commit()


def insert_append(df: pd.DataFrame, source_file: str):
    excel_cols = [normalize_excel_col(c) for c in df.columns]
    insert_cols = ["source_file"] + [f"fld_{c}" for c in excel_cols]
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
                out.append(clean_numeric_to_str(v))  # '1234' o None
            elif v is None or v is pd.NA:
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
                print(f"Error en batch {i+1}-{i+len(batch)}: {e}")
                # aislar filas malas
                for j, r in enumerate(batch):
                    try:
                        cur.execute(sql, r)
                        cn.commit()
                        inserted += 1
                    except pyodbc.Error as e2:
                        cn.rollback()
                        global_idx = i + j
                        print(f"Saltando fila problemática global #{global_idx} (Excel aprox fila {global_idx+2})")
                        print("Detalle:", e2)

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


def cargar_archivo(excel_path: str):
    df = read_excel(excel_path, SHEET_NAME)

    print(f"Archivo: {Path(excel_path).name}")
    print(f"Filas: {len(df)} | Columnas: {len(df.columns)}")

    df = data_cleaners.apply_fuzzy_matching_to_cobrador(df, threshold=90)

    found_numeric = [c for c in df.columns if col_is_numeric(c)]
    print("Columnas numéricas detectadas:", found_numeric if found_numeric else "ninguna")

    ensure_table_and_columns(df)
    current_source_file = Path(excel_path).name
    fecha_visor = bench_recarga.fecha_visor_archivo(excel_path)
    if should_skip_load(current_source_file, fecha_visor):
        return
    insert_append(df, current_source_file)
    with connect() as cn:
        bench_recarga.registrar_fecha_visor(cn.cursor(), TABLE, current_source_file, fecha_visor)
        cn.commit()


def main():
    for excel_file in get_bench_files(BENCH_FOLDER, BENCH_PATTERN):
        print(f"Archivo BENCH encontrado: {excel_file}")
        cargar_archivo(str(excel_file))
    # Los archivos pueden traer nombres de ejecutivos mal escritos: se corrigen segun la nomina.
    corregir_nombres.corregir_tras_carga()


if __name__ == "__main__":
    main()
