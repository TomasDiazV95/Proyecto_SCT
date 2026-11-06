"""Recarga de archivos bench que se vuelven a subir al visor.

descarga_SCT.py deja en cada archivo extraido, como fecha de modificacion, la fecha
en que fue cargado al visor. Aqui se compara esa fecha con la de la carga que ya
existe en la tabla: si el visor tiene una carga mas nueva, se reemplazan las filas.

El bench de fin de mes se sube dos veces: primero el pre-cierre y despues el cierre,
con el mismo nombre o escrito de otra forma (20260930 - BENCH CASTIGO - PHOENIX.XLSX /
20260930_BENCH CASTIGO_PHOENIX.XLSX). Por eso las cargas se comparan por foto y no solo
por nombre de archivo. La primera carga no se borra: sus filas quedan en la misma tabla
con version_carga = 'PRECIERRE' y el cierre se carga al lado. Las filas vigentes (cierre
y cargas normales) tienen version_carga en NULL, asi que todo lo que lea la tabla debe
filtrar version_carga IS NULL para no sumar ambas.

La foto es la columna FECHA del archivo (fld_FECHA), no la fecha del nombre: desde
octubre-2026 el nombre lleva el dia en que se sube y la FECHA el dia habil de los datos
(20261102_PHOENIX_BENCH_CASTIGO.XLSX trae FECHA 20261030, el cierre de octubre).
Solo si el archivo no trae FECHA se usa la fecha del nombre.
"""

import re
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import pandas as pd
import pyodbc

# Fecha de carga en el visor del archivo que origino las filas.
VISOR_COL = "visor_modificado"
# NULL = carga vigente; 'PRECIERRE' = primera carga del archivo de fin de mes.
VERSION_COL = "version_carga"
PRECIERRE = "PRECIERRE"
# Columna con la fecha de los datos (FECHA del Excel, texto YYYYMMDD).
FOTO_COL = "fld_FECHA"

# Cargas sin fecha de visor (anteriores a este control): se usa la fecha de carga a la BD.
_REFERENCIA = f"MAX(COALESCE([{VISOR_COL}], ts_carga))"

# Archivos que debe_cargar decidio cargar como pre-cierre; registrar_fecha_visor los marca.
_cargar_como_precierre: set[tuple[str, str]] = set()


def fecha_visor_archivo(path: str | Path) -> datetime:
    mtime = Path(path).stat().st_mtime
    return datetime.fromtimestamp(mtime).replace(second=0, microsecond=0)


def tokens_bench(nombre: str) -> frozenset[str]:
    """Palabras que identifican un bench, sin la fecha ni la extension ni los separadores.

    '20260930 - BENCH CASTIGO - PHOENIX.XLSX' y '20260930_BENCH CASTIGO_PHOENIX.XLSX'
    dan lo mismo. Misma regla que DESCARGAS/descarga_SCT.py.
    """
    base = re.sub(r"\.xlsx?\s*$", "", nombre.strip(), flags=re.IGNORECASE)
    palabras = re.findall(r"[A-Z0-9&]+", base.upper())
    return frozenset(p for p in palabras if not re.fullmatch(r"\d{6,8}", p))


def archivos_bench(folder: Path, pattern: str) -> list[Path]:
    """Archivos del bench en la carpeta, del mas antiguo al mas nuevo segun su carga en el visor.

    Ademas de los que cumplen el patron, toma los que son el mismo bench con el nombre
    escrito de otra forma. El orden importa: el pre-cierre se carga antes que el cierre.
    """
    esperado = tokens_bench(pattern.replace("*", " ").replace("?", " "))
    archivos = {p for p in folder.glob(pattern)}
    archivos |= {
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in (".xlsx", ".xls") and tokens_bench(p.name) == esperado
    }
    return sorted(
        (p for p in archivos if not p.name.startswith("~$")),
        key=lambda p: (p.stat().st_mtime, p.name),
    )


def fecha_foto_df(df: pd.DataFrame) -> str | None:
    """Fecha de los datos (columna FECHA, YYYYMMDD) de un bench leido; None si no la trae."""
    columna = next(
        (c for c in df.columns if str(c).strip().upper() in ("FECHA", FOTO_COL.upper())),
        None,
    )
    if columna is None:
        return None
    fechas = df[columna].dropna().map(lambda v: re.sub(r"\D", "", str(v))[:8])
    fechas = fechas[fechas.str.fullmatch(r"\d{8}")]
    if fechas.empty:
        return None
    # Una foto trae una sola FECHA; si viniera mas de una, manda la que mas se repite.
    return fechas.mode().iloc[0]


def _tabla_existe(cur: pyodbc.Cursor, table: str) -> bool:
    cur.execute("SELECT OBJECT_ID(?, 'U')", (table,))
    return cur.fetchone()[0] is not None


def _asegurar_columnas(cur: pyodbc.Cursor, table: str) -> None:
    for columna, tipo in ((VISOR_COL, "DATETIME2(0)"), (VERSION_COL, "NVARCHAR(20)")):
        cur.execute("SELECT COL_LENGTH(?, ?)", (table, columna))
        if cur.fetchone()[0] is None:
            cur.execute(f"ALTER TABLE {table} ADD [{columna}] {tipo} NULL;")


def _es_fin_de_mes(
    cur: pyodbc.Cursor,
    table: str,
    source_file: str,
    fecha_visor: datetime,
    fecha_foto: str | None = None,
) -> bool:
    """La foto es el ultimo bench de su mes y la nueva carga llego ya en un mes posterior."""
    match = re.match(r"(\d{4})(\d{2})(\d{2})", fecha_foto or source_file)
    if not match:
        return False
    anio, mes, dia = match.groups()
    if (fecha_visor.year, fecha_visor.month) <= (int(anio), int(mes)):
        return False

    if fecha_foto:
        cur.execute(
            f"SELECT COUNT(*) FROM {table} WHERE [{FOTO_COL}] LIKE ? AND [{FOTO_COL}] > ?",
            (f"{anio}{mes}%", fecha_foto),
        )
    else:
        cur.execute(
            f"SELECT COUNT(*) FROM {table} WHERE source_file LIKE ? AND LEFT(source_file, 8) > ?",
            (f"{anio}{mes}[0-9][0-9]%", f"{anio}{mes}{dia}"),
        )
    return cur.fetchone()[0] == 0


def _filtro_foto(source_file: str, por_foto: bool, fecha_foto: str | None = None) -> tuple[str, str]:
    """Filtro de las cargas de la misma foto: misma FECHA de los datos o, si el archivo
    no la trae, la misma fecha en el nombre."""
    if por_foto and fecha_foto:
        return f"[{FOTO_COL}] = ?", fecha_foto
    match = re.match(r"(\d{8})(?!\d)", source_file) if por_foto else None
    if match:
        return "source_file LIKE ?", match.group(1) + "[^0-9]%"
    return "source_file = ?", source_file


def debe_cargar(
    cur: pyodbc.Cursor,
    table: str,
    source_file: str,
    fecha_visor: datetime,
    conservar_precierre: bool = False,
    fecha_foto: str | Callable[[], str | None] | None = None,
) -> bool:
    """Indica si hay que cargar el archivo.

    Si el visor tiene una carga posterior a la vigente, borra las filas vigentes para que
    se reemplacen. Con conservar_precierre (tablas de bench) la comparacion es por foto y,
    si es el bench de fin de mes y aun no tiene pre-cierre, la carga anterior no se borra:
    queda marcada como pre-cierre. Si lo que llega es anterior a la carga vigente y la
    foto no tiene pre-cierre, se carga como pre-cierre.

    fecha_foto: FECHA de los datos del archivo (YYYYMMDD), o una funcion que la lee; solo
    se llama si el archivo no esta ya cargado, para no leer el Excel sin necesidad.
    No hace commit: lo decide quien llama.
    """
    _cargar_como_precierre.discard((table, source_file))
    if not _tabla_existe(cur, table):
        print("No hay carga previa en la tabla; se cargara el archivo actual.")
        return True

    _asegurar_columnas(cur, table)

    # Este mismo archivo ya cargado (vigente o pre-cierre) y sin resubida posterior.
    cur.execute(f"SELECT COUNT(*), {_REFERENCIA} FROM {table} WHERE source_file = ?", (source_file,))
    filas_archivo, referencia_archivo = cur.fetchone()
    if filas_archivo and fecha_visor <= referencia_archivo:
        print(
            f"Carga en visor: {fecha_visor:%d-%m-%Y %H:%M} | "
            f"Carga registrada en BD: {referencia_archivo:%d-%m-%Y %H:%M}"
        )
        print(f"Ya cargado, se omite: {source_file}")
        return False

    if callable(fecha_foto):
        fecha_foto = fecha_foto()
    if conservar_precierre and fecha_foto:
        cur.execute("SELECT COL_LENGTH(?, ?)", (table, FOTO_COL))
        if cur.fetchone()[0] is None:
            fecha_foto = None
    if conservar_precierre:
        print(f"Foto (FECHA de los datos): {fecha_foto or 'sin FECHA, se usa el nombre'}")

    filtro, valor = _filtro_foto(source_file, conservar_precierre, fecha_foto)
    vigente = f"{filtro} AND [{VERSION_COL}] IS NULL"
    cur.execute(f"SELECT COUNT(*), {_REFERENCIA} FROM {table} WHERE {vigente}", (valor,))
    filas, referencia = cur.fetchone()

    if not filas:
        print(f"{source_file} no esta en {table}; se cargara.")
        return True

    print(f"Carga en visor: {fecha_visor:%d-%m-%Y %H:%M} | Carga vigente en BD: {referencia:%d-%m-%Y %H:%M}")

    sin_precierre = False
    if conservar_precierre and _es_fin_de_mes(cur, table, source_file, fecha_visor, fecha_foto):
        cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {filtro} AND [{VERSION_COL}] = ?", (valor, PRECIERRE))
        sin_precierre = not cur.fetchone()[0]

    if fecha_visor > referencia:
        if sin_precierre:
            cur.execute(f"UPDATE {table} SET [{VERSION_COL}] = ? WHERE {vigente}", (PRECIERRE, valor))
            print(f"{source_file} es una carga posterior; las {filas} filas anteriores quedan como pre-cierre en {table}.")
            return True
        print(f"{source_file} es una carga posterior; se reemplazan {filas} filas en {table}.")
        cur.execute(f"DELETE FROM {table} WHERE {vigente}", (valor,))
        return True

    # El archivo es anterior a la carga vigente de la misma foto (con otro nombre).
    if sin_precierre and fecha_visor < referencia:
        print(f"{source_file} es anterior a la carga vigente; se cargara como pre-cierre.")
        _cargar_como_precierre.add((table, source_file))
        return True

    print(f"Ya hay una carga igual o posterior de esa foto, se omite: {source_file}")
    return False


def registrar_fecha_visor(cur: pyodbc.Cursor, table: str, source_file: str, fecha_visor: datetime) -> None:
    """Guarda la fecha de carga en el visor en las filas recien insertadas. No hace commit."""
    _asegurar_columnas(cur, table)
    recien_cargadas = f"source_file = ? AND [{VERSION_COL}] IS NULL"
    cur.execute(f"UPDATE {table} SET [{VISOR_COL}] = ? WHERE {recien_cargadas}", (fecha_visor, source_file))
    if (table, source_file) in _cargar_como_precierre:
        cur.execute(f"UPDATE {table} SET [{VERSION_COL}] = ? WHERE {recien_cargadas}", (PRECIERRE, source_file))
        _cargar_como_precierre.discard((table, source_file))
