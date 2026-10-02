"""Recarga de archivos bench que se vuelven a subir al visor con el mismo nombre.

descarga_SCT.py deja en cada archivo extraido, como fecha de modificacion, la fecha
en que fue cargado al visor. Aqui se compara esa fecha con la de la carga que ya
existe en la tabla: si el visor tiene una carga mas nueva, se reemplazan las filas.
"""

from datetime import datetime
from pathlib import Path

import pyodbc

# Fecha de carga en el visor del archivo que origino las filas.
VISOR_COL = "visor_modificado"


def fecha_visor_archivo(path: str | Path) -> datetime:
    mtime = Path(path).stat().st_mtime
    return datetime.fromtimestamp(mtime).replace(second=0, microsecond=0)


def _tabla_existe(cur: pyodbc.Cursor, table: str) -> bool:
    cur.execute("SELECT OBJECT_ID(?, 'U')", (table,))
    return cur.fetchone()[0] is not None


def _asegurar_columna(cur: pyodbc.Cursor, table: str) -> None:
    cur.execute("SELECT COL_LENGTH(?, ?)", (table, VISOR_COL))
    if cur.fetchone()[0] is None:
        cur.execute(f"ALTER TABLE {table} ADD [{VISOR_COL}] DATETIME2(0) NULL;")


def debe_cargar(cur: pyodbc.Cursor, table: str, source_file: str, fecha_visor: datetime) -> bool:
    """Indica si hay que cargar el archivo.

    Si el archivo ya estaba cargado pero el visor tiene una carga posterior,
    borra las filas anteriores de ese source_file para que se reemplacen.
    No hace commit: lo decide quien llama.
    """
    if not _tabla_existe(cur, table):
        print("No hay carga previa en la tabla; se cargara el archivo actual.")
        return True

    _asegurar_columna(cur, table)
    cur.execute(
        f"SELECT COUNT(*), MAX([{VISOR_COL}]), MAX(ts_carga) FROM {table} WHERE source_file = ?",
        (source_file,),
    )
    filas, visor_bd, ts_carga_bd = cur.fetchone()

    if not filas:
        print(f"{source_file} no esta en {table}; se cargara.")
        return True

    # Cargas anteriores a este control no tienen fecha de visor: se usa la fecha de carga a la BD.
    referencia = visor_bd or ts_carga_bd
    print(f"Carga en visor: {fecha_visor:%d-%m-%Y %H:%M} | Carga registrada en BD: {referencia:%d-%m-%Y %H:%M}")

    if fecha_visor <= referencia:
        print(f"Ya cargado, se omite: {source_file}")
        return False

    print(f"{source_file} fue subido nuevamente al visor; se reemplazan {filas} filas en {table}.")
    cur.execute(f"DELETE FROM {table} WHERE source_file = ?", (source_file,))
    return True


def registrar_fecha_visor(cur: pyodbc.Cursor, table: str, source_file: str, fecha_visor: datetime) -> None:
    """Guarda la fecha de carga en el visor en las filas recien insertadas. No hace commit."""
    _asegurar_columna(cur, table)
    cur.execute(
        f"UPDATE {table} SET [{VISOR_COL}] = ? WHERE source_file = ?",
        (fecha_visor, source_file),
    )
