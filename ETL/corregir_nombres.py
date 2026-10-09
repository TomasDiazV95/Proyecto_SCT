"""Corrige en las tablas los nombres de ejecutivos mal escritos, segun la nomina.

La referencia es dbo.rrhh_colaboradores.nombre_panel: la primera forma es la correcta y las
que siguen (separadas por ';') son las formas erroneas con que el nombre ha llegado en algun
archivo (ej. 'Valentina Rochow; Valentina Rocheau').

- Solo cambia las formas erroneas y los espacios repetidos. No cambia mayusculas: una tabla
  que guarda 'VALENTINA ROCHEAU' queda con 'VALENTINA ROCHOW'.
- Cada fila corregida queda registrada en dbo.rrhh_nombres_corregidos.
- Se ejecuta al final de las cargas de bench, porque los archivos nuevos pueden traer otra
  vez la forma erronea. Tambien se puede correr a mano:

      python corregir_nombres.py            corrige
      python corregir_nombres.py --simular  solo muestra lo que cambiaria
"""

import os
import sys
from pathlib import Path

import pyodbc
from dotenv import load_dotenv


# Columnas con nombres de ejecutivos que usan los paneles de productividad.
COLUMNAS = [
    ("dbo.stc_bloques_ejecutivos", "ejecutivo"),
    ("dbo.sth_ejecutivos_ciclo", "ejecutivo"),
    ("dbo.itau_vigente_ejecutivos", "ejecutivo"),
    ("dbo.itau_vigente_ejecutivos_castigo", "nombre_carterizado"),
    ("dbo.tmp_ejecutivos", "nombre_ejecutivo"),
    ("dbo.tmp_carterizado_GM", "ejecutivo"),
    ("dbo.tmp_carterizado_ITAU_CASTIGO", "ejecutivo"),
    ("dbo.tmp_carterizado_ITAU_VENCIDA", "ejecutivo"),
    ("dbo.tmp_carterizado_SCT", "ejecutivo"),
    ("dbo.tmp_carterizado_STH", "ejecutivo"),
    ("dbo.tmp_BIT_carterizado", "usuario"),
    ("dbo.tmp_bench_STC", "fld_COBRADOR"),
    ("dbo.tmp_bench_temp_STC", "fld_COBRADOR"),
    ("dbo.tmp_bench_temp_STC_asignado", "fld_COBRADOR"),
    ("dbo.tmp_bench_SC_Castigo", "fld_COBRADOR"),
    ("dbo.tbl_gestiones_diarias_sct", "cobrador_actual"),
]

LOG_TABLE = "dbo.rrhh_nombres_corregidos"


def _connect() -> pyodbc.Connection:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    available = list(pyodbc.drivers())
    preferred = [os.getenv("DB_DRIVER"), "ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server", "SQL Server"]
    driver = next((d for d in preferred if d and d in available), None)
    if not driver:
        raise RuntimeError(f"No hay driver ODBC para SQL Server. Drivers encontrados: {available}")
    return pyodbc.connect(
        f"Driver={{{driver}}};"
        f"Server={os.getenv('DB_SERVER')};"
        f"Database={os.getenv('DB_NAME')};"
        f"Uid={os.getenv('DB_USER')};"
        f"Pwd={os.getenv('DB_PASSWORD')};"
        "TrustServerCertificate=yes;"
        "Encrypt=yes;"
    )


def _formas(cur) -> list[tuple[str, str]]:
    """Pares (forma, nombre correcto). Incluye la forma correcta, para limpiar sus espacios repetidos."""
    cur.execute(
        """
        SELECT nombre_panel
        FROM dbo.rrhh_colaboradores
        WHERE activo = 1
          AND nombre_panel IS NOT NULL
        """
    )
    pares: dict[str, str] = {}
    for (nombre_panel,) in cur.fetchall():
        formas = [" ".join(f.split()) for f in str(nombre_panel).split(";")]
        formas = [f for f in formas if f]
        for forma in formas:
            pares[forma.upper()] = formas[0]
    return [(forma, correcto) for forma, correcto in pares.items()]


def _columna_id(cur, tabla: str) -> str | None:
    """Columna de la clave primaria, si es una sola; con ella se registra cada fila corregida."""
    cur.execute(
        """
        SELECT c.name
        FROM sys.indexes i
        JOIN sys.index_columns ic ON ic.object_id = i.object_id AND ic.index_id = i.index_id
        JOIN sys.columns c ON c.object_id = ic.object_id AND c.column_id = ic.column_id
        WHERE i.object_id = OBJECT_ID(?)
          AND i.is_primary_key = 1
        """,
        (tabla,),
    )
    columnas = [row[0] for row in cur.fetchall()]
    return columnas[0] if len(columnas) == 1 else None


def corregir(cn: pyodbc.Connection, simular: bool = False) -> int:
    """Corrige todas las tablas de COLUMNAS. Devuelve el total de filas corregidas (o por corregir)."""
    cur = cn.cursor()
    if not simular:
        cur.execute(
            f"""
        IF OBJECT_ID('{LOG_TABLE}', 'U') IS NULL
            CREATE TABLE {LOG_TABLE} (
                id             INT IDENTITY(1, 1) PRIMARY KEY,
                tabla          VARCHAR(128)  NOT NULL,
                columna        VARCHAR(128)  NOT NULL,
                id_fila        BIGINT        NULL,
                valor_anterior NVARCHAR(400) NOT NULL,
                valor_nuevo    NVARCHAR(400) NOT NULL,
                fecha          DATETIME2     NOT NULL DEFAULT (SYSDATETIME())
            );
        """
        )
    cur.execute(
        """
        CREATE TABLE #formas (
            forma    NVARCHAR(400) COLLATE DATABASE_DEFAULT NOT NULL PRIMARY KEY,
            correcto NVARCHAR(400) COLLATE DATABASE_DEFAULT NOT NULL
        );
        """
    )
    cur.executemany("INSERT INTO #formas (forma, correcto) VALUES (?, ?)", _formas(cur))
    cn.commit()

    total = 0
    for tabla, columna in COLUMNAS:
        cur.execute("SELECT COL_LENGTH(?, ?)", (tabla, columna))
        if cur.fetchone()[0] is None:
            continue
        col = f"t.[{columna}]"
        limpio = f"REPLACE(REPLACE(LTRIM(RTRIM({col})), '   ', ' '), '  ', ' ')"
        # Se respeta el estilo de la tabla: si el valor viene en mayusculas, el corregido tambien.
        nuevo = f"CASE WHEN {col} = UPPER({col}) COLLATE Modern_Spanish_CS_AS THEN UPPER(f.correcto) ELSE f.correcto END"
        desde = f"FROM {tabla} t JOIN #formas f ON {limpio} = f.forma WHERE {col} <> f.correcto"

        if simular:
            cur.execute(f"SELECT {col}, {nuevo}, COUNT(*) {desde} GROUP BY {col}, {nuevo}")
            for anterior, corregido, filas in cur.fetchall():
                print(f"  {tabla}.{columna}: '{anterior}' -> '{corregido}' ({filas} filas)")
                total += filas
            continue

        id_fila = _columna_id(cur, tabla)
        id_sql = f"t.[{id_fila}]" if id_fila else "NULL"
        try:
            cur.execute(
                f"INSERT INTO {LOG_TABLE} (tabla, columna, id_fila, valor_anterior, valor_nuevo) "
                f"SELECT ?, ?, {id_sql}, {col}, {nuevo} {desde}",
                (tabla, columna),
            )
            cur.execute(f"UPDATE t SET {col} = {nuevo} {desde}")
            filas = cur.rowcount
            cn.commit()
        except pyodbc.Error as exc:
            # Tipicamente una clave unica: la fila ya existe con el nombre correcto.
            cn.rollback()
            print(f"  [AVISO] {tabla}.{columna} no se pudo corregir: {exc}")
            continue
        if filas:
            print(f"  {tabla}.{columna}: {filas} filas corregidas")
            total += filas

    cur.execute("DROP TABLE #formas")
    cn.commit()
    return total


def corregir_tras_carga() -> None:
    """Para llamar al final de un ETL: un fallo aca no debe botar la carga."""
    try:
        with _connect() as cn:
            total = corregir(cn)
        print(f"Nombres de ejecutivos corregidos segun la nomina: {total} filas")
    except Exception as exc:
        print(f"[AVISO] No se pudieron corregir los nombres de ejecutivos: {exc}")


if __name__ == "__main__":
    simular = "--simular" in sys.argv
    with _connect() as cn:
        total = corregir(cn, simular=simular)
    print(f"Total: {total} filas {'por corregir' if simular else 'corregidas'}")
