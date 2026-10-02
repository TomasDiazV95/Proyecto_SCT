"""Carga la asignacion de apertura mensual de Santander Consumer en las tablas de bench.

    YYYYMM - ASIGNACION_APERTURA - PHOENIX.XLSX             -> dbo.tmp_bench_STC
    YYYYMM - ASIGNACION_APERTURA - PHOENIX (TELEFONIA).XLSX -> dbo.tmp_bench_temp_STC

Los archivos los deja descarga_SCT.py en la carpeta de los bench. Solo se cargan las columnas
que existen en la tabla (por nombre identico o por su equivalente); el resto se ignora y no se
agregan columnas nuevas. PERIODO sale del nombre del archivo y FECHA es el primer dia de ese mes.
"""

import os
import re
from pathlib import Path

import bench_recarga
import data_cleaners
import pandas as pd
from etl_bench_temp_stc import clean_numeric_to_str, connect, read_excel, require_env, sql_ident

BENCH_FOLDER = Path(require_env("BENCH_STC_FOLDER"))
SHEET_NAME = os.getenv("ASIGNACION_APERTURA_SHEET_NAME", "").strip() or None
PERIODO_PATTERN = re.compile(r"^\s*(\d{6})\s*-\s*ASIGNACION_APERTURA", re.IGNORECASE)
BATCH_SIZE = 5000

# Columnas del archivo de apertura que en las tablas de bench tienen otro nombre.
EQUIVALENTES_COMUNES = {
    "DDAS_NRT_PPAL": "RUT",
    "DDAS_ID_NUMERO_OPERAC": "OPERACION",
    "DDAS_NOMBRE_DDOR": "NOMBRE",
    "DEUDA_TOTAL": "DEUDA_ACT",
    "DDAS_FEC_1ER_VCTO": "FEC_1ER_VCTO",
    "DDAS_FEC_ULT_PAGO": "FEC_ULT_PAGO",
}

CARGAS = [
    {
        "nombre": "ASIGNACION APERTURA",
        "glob": "*ASIGNACION_APERTURA - PHOENIX.XLSX",
        "tabla": "dbo.tmp_bench_STC",
        "equivalentes": {
            **EQUIVALENTES_COMUNES,
            "AT_DIA_INI": "DM_INI",
            "AT_DIA_ACT": "DM_ACT",
            "DDAS_FEC_PROX_VCTO": "FECHA_PROX_VCTO",
            "DDAS_NROCUO_MOROSAS": "DDAS_NROCUO_MORA",
        },
    },
    {
        "nombre": "ASIGNACION APERTURA - TELEFONIA",
        "glob": "*ASIGNACION_APERTURA - PHOENIX (TELEFONIA).XLSX",
        "tabla": "dbo.tmp_bench_temp_STC",
        "equivalentes": {
            **EQUIVALENTES_COMUNES,
            "AT_DIA_INI": "MORA_INI",
            "AT_DIA_ACT": "MORA_ACT",
            "DDAS_FEC_PROX_VCTO": "FEC_PROXVCTO",
            "DDAS_NROCUO_PACTADAS": "CUO_PAC",
            "DDAS_NROCUO_PAGADAS": "CUO_PAG",
            "DDAS_NROCUO_MOROSAS": "CUO_MORA",
        },
    },
]


def periodo_archivo(path: Path) -> str | None:
    match = PERIODO_PATTERN.match(path.name)
    return match.group(1) if match else None


def pick_files(pattern: str) -> list[Path]:
    files = [
        p for p in BENCH_FOLDER.glob(pattern)
        if not p.name.startswith("~$") and periodo_archivo(p) is not None
    ]
    files.sort(key=lambda p: p.name)
    return files


def columnas_tabla(cur, table: str) -> dict[str, tuple[str, bool]]:
    """Columnas fld_ de la tabla: nombre sin prefijo en mayusculas -> (nombre real, es numerica)."""
    cur.execute(
        """
        SELECT c.name, TYPE_NAME(c.user_type_id)
        FROM sys.columns c
        WHERE c.object_id = OBJECT_ID(?)
        """,
        (table,),
    )
    columnas = {}
    for name, type_name in cur.fetchall():
        if name.lower().startswith("fld_"):
            columnas[name[4:].upper()] = (name, type_name in {"decimal", "numeric", "int", "bigint"})
    return columnas


def clean_text(value) -> str | None:
    if value is None or value is pd.NA:
        return None
    text = str(value).replace("\x00", "").strip()
    if not text or text.lower() == "nan":
        return None
    return text


def deuda_total_como_inicial(df: pd.DataFrame) -> pd.DataFrame:
    """En la apertura la deuda inicial es DEUDA_TOTAL (COL_INI viene en cero para castigo): se guarda en
    DEUDA_INI y en DEUDA_ACT, y COL_INI no se carga."""
    por_nombre = {str(col).strip().upper(): col for col in df.columns}
    if "DEUDA_TOTAL" not in por_nombre:
        raise RuntimeError("El archivo de apertura no trae la columna DEUDA_TOTAL.")
    df = df.drop(columns=[por_nombre[c] for c in ("DEUDA_INI", "COL_INI") if c in por_nombre])
    df["DEUDA_INI"] = df[por_nombre["DEUDA_TOTAL"]]
    return df


def plan_columnas(df: pd.DataFrame, existentes: dict[str, tuple[str, bool]], equivalentes: dict[str, str]):
    """Devuelve [(columna del Excel, columna de la tabla, es numerica)] y las columnas ignoradas."""
    plan = []
    ignoradas = []
    usadas = set()
    for col in df.columns:
        origen = str(col).strip().upper()
        destino = equivalentes.get(origen, origen).upper()
        if destino not in existentes or destino in usadas:
            ignoradas.append(str(col))
            continue
        usadas.add(destino)
        nombre_real, es_numerica = existentes[destino]
        plan.append((col, nombre_real, es_numerica))
    return plan, ignoradas


def insert_rows(cur, table: str, df: pd.DataFrame, source_file: str, plan, fijas: dict[str, str]) -> int:
    insert_cols = ["source_file"] + list(fijas) + [destino for _, destino, _ in plan]
    placeholders = ",".join(["?"] * len(insert_cols))
    sql = f"INSERT INTO {table} ({','.join(map(sql_ident, insert_cols))}) VALUES ({placeholders})"

    limpiadores = [clean_numeric_to_str if es_numerica else clean_text for _, _, es_numerica in plan]
    datos = df[[origen for origen, _, _ in plan]]
    rows = [
        tuple([source_file] + list(fijas.values()) + [limpiar(v) for limpiar, v in zip(limpiadores, row)])
        for row in datos.itertuples(index=False, name=None)
    ]

    cur.fast_executemany = True
    inserted = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        cur.executemany(sql, batch)
        inserted += len(batch)
        print(f"OK batch {i + 1}-{i + len(batch)}")
    return inserted


def cargar_archivo(excel_file: Path, carga: dict) -> None:
    table = carga["tabla"]
    source_file = excel_file.name
    periodo = periodo_archivo(excel_file)
    fecha_visor = bench_recarga.fecha_visor_archivo(excel_file)

    print(f"Archivo: {source_file} -> {table}")

    with connect() as cn:
        cn.autocommit = False
        cur = cn.cursor()

        existentes = columnas_tabla(cur, table)
        if not existentes:
            raise RuntimeError(f"La tabla {table} no existe o no tiene columnas fld_.")

        # Si el archivo ya esta cargado pero fue resubido al visor, se borran sus filas y se recarga.
        if not bench_recarga.debe_cargar(cur, table, source_file, fecha_visor):
            return

        df = read_excel(str(excel_file), SHEET_NAME)
        print(f"Filas: {len(df)} | Columnas: {len(df.columns)}")
        df = data_cleaners.apply_fuzzy_matching_to_cobrador(df, threshold=90)
        df = deuda_total_como_inicial(df)

        plan, ignoradas = plan_columnas(df, existentes, carga["equivalentes"])
        print("Columnas cargadas:", ", ".join(f"{o}->{d}" if f"fld_{o}".upper() != d.upper() else str(o) for o, d, _ in plan))
        print(f"Columnas ignoradas (no estan en {table}): {len(ignoradas)}")

        # El archivo no trae periodo ni fecha: periodo del nombre y primer dia de ese mes.
        fijas = {}
        destinos = {destino.upper() for _, destino, _ in plan}
        for columna, valor in (("PERIODO", periodo), ("FECHA", f"{periodo}01")):
            if columna in existentes and existentes[columna][0].upper() not in destinos:
                fijas[existentes[columna][0]] = valor

        inserted = insert_rows(cur, table, df, source_file, plan, fijas)
        bench_recarga.registrar_fecha_visor(cur, table, source_file, fecha_visor)
        cn.commit()

    print(f"OK: insertadas {inserted} filas en {table}")


def main() -> None:
    if not BENCH_FOLDER.exists():
        raise FileNotFoundError(f"La carpeta no existe: {BENCH_FOLDER}")

    for carga in CARGAS:
        files = pick_files(carga["glob"])
        if not files:
            raise FileNotFoundError(
                f"No se encontro el archivo de {carga['nombre']} en {BENCH_FOLDER} con el patron {carga['glob']}"
            )
        for excel_file in files:
            cargar_archivo(excel_file, carga)


if __name__ == "__main__":
    main()
