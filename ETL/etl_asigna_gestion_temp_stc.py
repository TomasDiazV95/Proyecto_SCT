import os
from pathlib import Path

import pyodbc
from dotenv import load_dotenv

load_dotenv()

SERVER = os.getenv("DB_SERVER")
DATABASE = os.getenv("DB_NAME")
USER = os.getenv("DB_USER")
PASSWORD = os.getenv("DB_PASSWORD")
DRIVER_ENV = os.getenv("DB_DRIVER")

PRIORITY_FILE = Path(
    os.getenv(
        "GESTION_PRIORITY_FILE",
        str(Path(__file__).resolve().parents[1] / "archivos" / "orden_gest.txt"),
    )
)

CFG_TABLE = "dbo.cfg_gestion_prioridad_temp"
BENCH_TABLE = "dbo.tmp_bench_temp_STC"
GEST_TABLE = "dbo.tmp_GEST_CRM"
OUT_TABLE = "dbo.tmp_bench_temp_STC_asignado"


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


def connect() -> pyodbc.Connection:
    driver = pick_driver()
    conn_str = (
        f"Driver={{{driver}}};"
        f"Server={SERVER};"
        f"Database={DATABASE};"
        f"Uid={USER};"
        f"Pwd={PASSWORD};"
        "TrustServerCertificate=yes;"
        "Encrypt=yes;"
    )
    return pyodbc.connect(conn_str)


def read_priority_file(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"No existe archivo de prioridad: {path}")

    lines = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line:
            lines.append(line.upper())

    if not lines:
        raise RuntimeError("El archivo de prioridad esta vacio")
    return lines


def load_priority_table(priorities: list[str]) -> None:
    with connect() as cn:
        cur = cn.cursor()
        cur.execute(
            f"""
            IF OBJECT_ID('{CFG_TABLE}', 'U') IS NULL
            BEGIN
                CREATE TABLE {CFG_TABLE} (
                    prioridad INT NOT NULL,
                    gestion NVARCHAR(200) NOT NULL,
                    CONSTRAINT PK_cfg_gestion_prioridad_temp PRIMARY KEY (gestion)
                );
            END
            """
        )
        cn.commit()

        cur.execute(f"DELETE FROM {CFG_TABLE}")
        cur.fast_executemany = True
        rows = [(i + 1, g) for i, g in enumerate(priorities)]
        cur.executemany(f"INSERT INTO {CFG_TABLE} (prioridad, gestion) VALUES (?, ?)", rows)
        cn.commit()


def refresh_assignment_table() -> None:
    with connect() as cn:
        cur = cn.cursor()
        cur.execute(
            f"""
            IF OBJECT_ID('{OUT_TABLE}', 'U') IS NULL
            BEGIN
                CREATE TABLE {OUT_TABLE} (
                    id_asignado BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                    fecha_carga DATE NOT NULL CONSTRAINT DF_tmp_bench_temp_STC_asig_fecha_carga DEFAULT (CONVERT(date, GETDATE())),
                    ts_carga DATETIME2(0) NOT NULL CONSTRAINT DF_tmp_bench_temp_STC_asig_ts_carga DEFAULT (SYSDATETIME()),
                    source_file NVARCHAR(260) NULL,
                    fld_PERIODO NVARCHAR(50) NULL,
                    fld_FECHA NVARCHAR(50) NULL,
                    fld_RUT NVARCHAR(50) NULL,
                    fld_OPERACION NVARCHAR(100) NULL,
                    fld_NOMBRE NVARCHAR(300) NULL,
                    fld_TRAMO_MORA NVARCHAR(100) NULL,
                    fld_REGION NVARCHAR(200) NULL,
                    fld_ZONA NVARCHAR(200) NULL,
                    fld_COBRADOR NVARCHAR(200) NULL,
                    fld_DEUDA_INI DECIMAL(38,0) NULL,
                    fld_CONTENIDO DECIMAL(38,0) NULL,
                    fld_NORMALIZADO DECIMAL(38,0) NULL,
                    meta_contencion_pct DECIMAL(5,2) NULL,
                    meta_normalizacion_pct DECIMAL(5,2) NULL,
                    usuario_gestion_asignado NVARCHAR(200) NULL,
                    mejor_respuesta_gestion NVARCHAR(300) NULL,
                    contacto_gestion NVARCHAR(200) NULL,
                    gestion_fecha DATETIME NULL,
                    gestion_hora NVARCHAR(50) NULL,
                    prioridad_gestion INT NULL,
                    contacto_titular_flag BIT NOT NULL CONSTRAINT DF_tmp_bench_temp_STC_asig_contacto_titular DEFAULT (0)
                );
                CREATE INDEX IX_tmp_bench_temp_STC_asig_fecha ON {OUT_TABLE}(fld_FECHA);
                CREATE INDEX IX_tmp_bench_temp_STC_asig_rut ON {OUT_TABLE}(fld_RUT);
                CREATE INDEX IX_tmp_bench_temp_STC_asig_usuario ON {OUT_TABLE}(usuario_gestion_asignado);
            END
            """
        )
        cn.commit()

        cur.execute(f"TRUNCATE TABLE {OUT_TABLE}")
        cn.commit()

        sql_insert = f"""
        ;WITH gest_validas AS (
            SELECT
                UPPER(LTRIM(RTRIM(REPLACE(REPLACE(REPLACE(CONVERT(varchar(50), g.rut), '.', ''), '-', ''), ' ', '')))) AS rut_key,
                UPPER(LTRIM(RTRIM(CONVERT(varchar(200), g.UsuarioGestion)))) AS UsuarioGestion,
                UPPER(LTRIM(RTRIM(CONVERT(varchar(300), g.RespuestaGestion)))) AS RespuestaGestion,
                UPPER(LTRIM(RTRIM(CONVERT(varchar(200), g.ContactoGestion)))) AS ContactoGestion,
                CASE
                    WHEN ISDATE(CONVERT(varchar(30), g.GestionFecha)) = 1 THEN CONVERT(datetime, g.GestionFecha)
                    ELSE CONVERT(datetime, '19000101')
                END AS GestionFecha_dt,
                CONVERT(varchar(50), g.GestionHora) AS GestionHora,
                p.prioridad,
                g.id
            FROM {GEST_TABLE} g
            INNER JOIN {CFG_TABLE} p
                ON UPPER(LTRIM(RTRIM(CONVERT(varchar(300), g.RespuestaGestion)))) = p.gestion
            WHERE g.cartera = 526
              AND UPPER(LTRIM(RTRIM(ISNULL(CONVERT(varchar(300), g.RespuestaGestion), '')))) <> 'NO REGULARIZARA'
        ),
        mejor_gestion AS (
            SELECT
                gv.*,
                ROW_NUMBER() OVER (
                    PARTITION BY gv.rut_key
                    ORDER BY
                        gv.prioridad ASC,
                        gv.GestionFecha_dt DESC,
                        gv.GestionHora DESC,
                        gv.id DESC
                ) AS rn
            FROM gest_validas gv
        ),
        bench_base AS (
            SELECT
                b.source_file,
                b.fld_PERIODO,
                b.fld_FECHA,
                b.fld_RUT,
                b.fld_OPERACION,
                b.fld_NOMBRE,
                b.fld_TRAMO_MORA,
                b.fld_REGION,
                b.fld_ZONA,
                b.fld_COBRADOR,
                b.fld_DEUDA_INI,
                b.fld_CONTENIDO,
                b.fld_NORMALIZADO,
                b.meta_contencion_pct,
                b.meta_normalizacion_pct,
                UPPER(LTRIM(RTRIM(REPLACE(REPLACE(REPLACE(CONVERT(varchar(50), b.fld_RUT), '.', ''), '-', ''), ' ', '')))) AS rut_key
            FROM {BENCH_TABLE} b
        )
        INSERT INTO {OUT_TABLE} (
            source_file,
            fld_PERIODO,
            fld_FECHA,
            fld_RUT,
            fld_OPERACION,
            fld_NOMBRE,
            fld_TRAMO_MORA,
            fld_REGION,
            fld_ZONA,
            fld_COBRADOR,
            fld_DEUDA_INI,
            fld_CONTENIDO,
            fld_NORMALIZADO,
            meta_contencion_pct,
            meta_normalizacion_pct,
            usuario_gestion_asignado,
            mejor_respuesta_gestion,
            contacto_gestion,
            gestion_fecha,
            gestion_hora,
            prioridad_gestion,
            contacto_titular_flag
        )
        SELECT
            bb.source_file,
            bb.fld_PERIODO,
            bb.fld_FECHA,
            bb.fld_RUT,
            bb.fld_OPERACION,
            bb.fld_NOMBRE,
            bb.fld_TRAMO_MORA,
            bb.fld_REGION,
            bb.fld_ZONA,
            bb.fld_COBRADOR,
            bb.fld_DEUDA_INI,
            bb.fld_CONTENIDO,
            bb.fld_NORMALIZADO,
            bb.meta_contencion_pct,
            bb.meta_normalizacion_pct,
            mg.UsuarioGestion,
            mg.RespuestaGestion,
            mg.ContactoGestion,
            mg.GestionFecha_dt,
            mg.GestionHora,
            mg.prioridad,
            CASE WHEN mg.ContactoGestion = 'TITULAR' THEN 1 ELSE 0 END
        FROM bench_base bb
        LEFT JOIN mejor_gestion mg
            ON bb.rut_key = mg.rut_key
           AND mg.rn = 1;
        """
        cur.execute(sql_insert)
        cn.commit()

        cur.execute(f"SELECT COUNT(1) FROM {OUT_TABLE}")
        total = cur.fetchone()[0]
        print(f"OK: tabla {OUT_TABLE} actualizada con {total} filas")


def main() -> None:
    priorities = read_priority_file(PRIORITY_FILE)
    print(f"Prioridades cargadas desde txt: {len(priorities)}")
    load_priority_table(priorities)
    print(f"OK: prioridades guardadas en {CFG_TABLE}")
    refresh_assignment_table()


if __name__ == "__main__":
    main()
