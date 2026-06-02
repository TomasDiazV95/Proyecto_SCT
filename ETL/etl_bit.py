import argparse
import json
import os
from pathlib import Path

import pandas as pd
import pyodbc
from dotenv import load_dotenv


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
    return df.where(pd.notnull(df), None)


def clean_cell(value: object) -> object:
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def _read_sources(file_path: str | None, folder_path: str | None) -> tuple[pd.DataFrame, pd.DataFrame, str, str]:
    if file_path:
        xlsx = Path(file_path)
        if not xlsx.exists():
            raise FileNotFoundError(f"No existe archivo: {xlsx}")
        cont = load_sheet(xlsx, "CONTENCION")
        cart = load_sheet(xlsx, "CARTERIZADO")
        return cont, cart, xlsx.name, xlsx.name

    if folder_path:
        folder = Path(folder_path)
        if not folder.exists():
            raise FileNotFoundError(f"No existe carpeta: {folder}")
        cont_path = folder / "CONTENCION.xlsx"
        cart_path = folder / "CARTERIZADO.xlsx"
        if not cont_path.exists() or not cart_path.exists():
            raise FileNotFoundError("En la carpeta deben existir CONTENCION.xlsx y CARTERIZADO.xlsx")

        cont_source_name = cont_path.name
        metadata_path = folder / "CONTENCION.meta.json"
        if metadata_path.exists():
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                candidate = str(metadata.get("original_filename") or "").strip()
                if candidate:
                    cont_source_name = candidate
            except Exception:
                pass

        cont = load_sheet(cont_path, 0)
        cart = load_sheet(cart_path, 0)
        return cont, cart, cont_source_name, cart_path.name

    raise RuntimeError("Debes indicar --file o --folder")


def run(periodo: str, file_path: str | None, folder_path: str | None) -> None:
    cont, cart, cont_source_file, cart_source_file = _read_sources(file_path, folder_path)
    skipped_cart_rows = 0

    with connect() as cn:
        cn.autocommit = False
        cur = cn.cursor()

        cur.execute("DELETE FROM dbo.tmp_BIT_contencion WHERE periodo = ?", (periodo,))
        cur.execute("DELETE FROM dbo.tmp_BIT_carterizado WHERE periodo = ?", (periodo,))
        insert_cont = """
        INSERT INTO dbo.tmp_BIT_contencion (
            periodo, source_file, rut, dv, con_no, prod, tipo_prod, cartera, grupo_producto, nombre, total,
            dias_mora, tramo_proyectado, tramo_proyectado_nuevo, dias_mora_hoy, tramo_cierre_op,
            dias_mora_intrames, castigo, paso_pc06, contiene, mto_contiene, tipo_cont
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        cont_rows = []
        for _, r in cont.iterrows():
            cont_rows.append(
                (
                    periodo,
                    cont_source_file,
                    r.get("RUT"),
                    r.get("DV"),
                    r.get("CON_NO"),
                    r.get("PROD"),
                    r.get("TIPO_PROD"),
                    r.get("CARTERA"),
                    r.get("GRUPO_PRODUCTO"),
                    r.get("NOMBRE"),
                    r.get("TOTAL"),
                    r.get("DIAS_MORA"),
                    r.get("TRAMO_PROYECTADO"),
                    r.get("TRAMO_PROYECTADO_NUEVO"),
                    r.get("DIAS_MORA_HOY"),
                    r.get("TRAMO_CIERRE_OP"),
                    r.get("DIAS_MORA_INTRAMES"),
                    r.get("CASTIGO"),
                    r.get("PASO_PC06"),
                    r.get("CONTIENE"),
                    r.get("MTO_CONTIENE"),
                    r.get("TIPO_CONT"),
                )
            )
        if cont_rows:
            cur.executemany(insert_cont, cont_rows)

        insert_cart = """
        INSERT INTO dbo.tmp_BIT_carterizado (periodo, source_file, rut, dv, nro_operacion, usuario)
        VALUES (?, ?, ?, ?, ?, ?)
        """
        cart_rows = []
        for _, r in cart.iterrows():
            nro_operacion = clean_cell(r.get("NRO_OPERACION"))
            if nro_operacion is None:
                skipped_cart_rows += 1
                continue

            cart_rows.append(
                (
                    periodo,
                    cart_source_file,
                    clean_cell(r.get("RUT")),
                    clean_cell(r.get("DV")),
                    nro_operacion,
                    clean_cell(r.get("USUARIO")),
                )
            )
        if cart_rows:
            cur.executemany(insert_cart, cart_rows)

        cn.commit()

    print(
        f"Carga BIT completada. periodo={periodo}, contencion={len(cont_rows)}, "
        f"carterizado={len(cart_rows)}, carterizado_omitido_sin_nro_operacion={skipped_cart_rows}"
    )


if __name__ == "__main__":
    load_env_files()
    parser = argparse.ArgumentParser(description="Carga ETL BIT")
    parser.add_argument("--file", required=False, help="Ruta del Excel SEGUIMIENTO BIT")
    parser.add_argument("--folder", required=False, help="Carpeta con CONTENCION.xlsx y CARTERIZADO.xlsx")
    parser.add_argument("--periodo", required=True, help="Periodo YYYY-MM")
    args = parser.parse_args()
    run(args.periodo, args.file, args.folder)
