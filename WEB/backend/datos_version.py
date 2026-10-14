"""Detecta cambios en las tablas que lee la web y renueva la cache al instante.

Cada tabla de TABLAS tiene un trigger que anota en dbo.datos_version que cambio (INSERT, UPDATE o
DELETE, sea del ETL o hecho a mano). Un hilo revisa esa tabla cada pocos segundos, junto con el
conteo de filas (para TRUNCATE y tablas que el ETL borra y vuelve a crear, que no disparan
triggers). Cuando hay un cambio y la base lleva unos segundos quieta (la carga termino), se limpia
la cache, se precalienta y se sube VERSION: las paginas abiertas la consultan en /api/datos/version
y vuelven a pedir sus datos.

Se apaga con DATOS_VERSION=0 en el entorno.
"""
from __future__ import annotations

import logging
import os
import threading
import time

import cache
import precalentar
from database import get_connection


logger = logging.getLogger("uvicorn.error")

# Tablas que leen los servicios (directo o a traves de vistas). Las de usuarios y sesiones no van:
# cambian en cada login y no afectan los datos de las paginas.
TABLAS = [
    "asignacion_itau_vencida", "contencion_itau_vencida", "cuotas_itau_vencida", "gm_metas_mensuales",
    "itau_castigo_metas_ejecutivo", "itau_castigo_metas_mensuales", "itau_vencida_filtros_medibles",
    "itau_vencida_metas", "itau_vigente_ejecutivos", "itau_vigente_ejecutivos_castigo", "itau_vigente_metas",
    "kpi_accion_canal", "kpi_asignacion", "kpi_compromisos", "kpi_crm_cartera", "kpi_gestiones_rut",
    "kpi_pagos", "kpi_pagos_diario", "kpi_tipo_contacto", "negocios_cargas", "negocios_cierre",
    "recup_itau_castigo", "rrhh_colaboradores", "stc_bloques_ejecutivos", "stc_metas_mensuales",
    "sth_ejecutivos_ciclo", "sth_metas_mensuales", "tbl_gestiones_diarias_sct", "tmp_BENCH_CONTROL_DIARIO",
    "tmp_BIT_asignacion", "tmp_BIT_asignacion_mensual", "tmp_BIT_carterizado", "tmp_BIT_castigo",
    "tmp_BIT_contencion", "tmp_BIT_metas", "tmp_FECHA_COMPROMISO_CRM", "tmp_GEST_CRM", "tmp_LA_asignacion",
    "tmp_LA_pagos", "tmp_LA_respuesta", "tmp_asig_GM", "tmp_bench_SC_Castigo", "tmp_bench_STC",
    "tmp_bench_STH", "tmp_bench_temp_STC", "tmp_carterizado_GM", "tmp_carterizado_ITAU_CASTIGO",
    "tmp_carterizado_ITAU_VENCIDA", "tmp_carterizado_SCT", "tmp_carterizado_STH", "tmp_ejecutivos",
    "tmp_itau_castigo_asignacion", "tmp_pagos_gm",
]

INTERVALO = 3  # segundos entre revisiones
QUIETO_MS = 3000  # la base debe llevar este tiempo sin cambios antes de recargar
REVISAR_TRIGGERS = 60  # segundos: recrea triggers perdidos (tablas que el ETL vuelve a crear)

# Version de los datos que ven las paginas. Sube despues de limpiar y precalentar la cache.
VERSION = 0

_TABLA_SQL = """
IF OBJECT_ID('dbo.datos_version', 'U') IS NULL
    CREATE TABLE dbo.datos_version (
        tabla SYSNAME NOT NULL PRIMARY KEY,
        version BIGINT NOT NULL DEFAULT 0,
        actualizado DATETIME2(3) NOT NULL DEFAULT '2000-01-01'
    );
"""

# El trigger corre una vez por fila en las cargas con fast_executemany: anota a lo mas una vez por
# segundo y cada tabla tiene su propia fila, asi dos cargas en paralelo no se bloquean entre si.
_TRIGGER_SQL = """
CREATE OR ALTER TRIGGER dbo.[trg_datos_version_{tabla}] ON dbo.[{tabla}]
AFTER INSERT, UPDATE, DELETE AS
BEGIN
    SET NOCOUNT ON;
    UPDATE dbo.datos_version
    SET version = version + 1, actualizado = SYSDATETIME()
    WHERE tabla = N'{tabla}'
      AND actualizado < DATEADD(MILLISECOND, -1000, SYSDATETIME());
END
"""

_ESTADO_SQL = """
SET LOCK_TIMEOUT 2000;
SELECT
    (SELECT SUM(version) FROM dbo.datos_version) AS version,
    (SELECT DATEDIFF_BIG(MILLISECOND, MAX(actualizado), SYSDATETIME()) FROM dbo.datos_version) AS quieto_ms,
    (SELECT CHECKSUM_AGG(CHECKSUM(p.object_id, p.row_count))
     FROM sys.dm_db_partition_stats p
     JOIN sys.tables t ON t.object_id = p.object_id
     WHERE p.index_id IN (0, 1) AND t.schema_id = SCHEMA_ID('dbo') AND t.name IN ({tablas})) AS filas;
"""


def _tablas_in() -> str:
    return ", ".join(f"N'{t}'" for t in TABLAS)


def asegurar_triggers() -> int:
    """Crea la tabla de versiones y el trigger de cada tabla que no lo tenga. Devuelve cuantos creo."""
    creados = 0
    with get_connection() as cn:
        cur = cn.cursor()
        cur.execute(_TABLA_SQL)
        cur.execute(
            f"""
            SELECT t.name
            FROM sys.tables t
            WHERE t.schema_id = SCHEMA_ID('dbo') AND t.name IN ({_tablas_in()})
              AND NOT EXISTS (
                  SELECT 1 FROM sys.triggers tr
                  WHERE tr.parent_id = t.object_id AND tr.name = N'trg_datos_version_' + t.name
              )
            """
        )
        faltantes = [r[0] for r in cur.fetchall()]
        for tabla in faltantes:
            cur.execute(
                "IF NOT EXISTS (SELECT 1 FROM dbo.datos_version WHERE tabla = ?) "
                "INSERT INTO dbo.datos_version (tabla) VALUES (?)",
                (tabla, tabla),
            )
            cur.execute(_TRIGGER_SQL.format(tabla=tabla))
            creados += 1
        cn.commit()
    return creados


def _estado() -> tuple | None:
    """(version, filas) y cuanto lleva quieta la base; None si una carga tiene tomada la tabla."""
    try:
        with get_connection() as cn:
            cur = cn.cursor()
            cur.execute(_ESTADO_SQL.format(tablas=_tablas_in()))
            while cur.description is None and cur.nextset():
                pass
            version, quieto_ms, filas = cur.fetchone()
    except Exception as exc:  # lock timeout mientras una carga no hace commit, o la BD no responde
        logger.debug("datos_version: sin estado (%s)", exc)
        return None
    return (version, filas), (quieto_ms if quieto_ms is not None else QUIETO_MS)


def _renovar() -> None:
    global VERSION
    en_uso = cache.segundos_sin_uso() < precalentar.PAUSA_SIN_USO
    cache.clear()
    VERSION += 1
    logger.info("Datos cambiaron en la base: cache limpiada (version %s)", VERSION)
    # Las paginas abiertas ya estan pidiendo de nuevo; el precalentamiento comparte sus candados,
    # asi cada consulta corre una sola vez. De noche o sin visitas solo se limpia.
    if en_uso:
        precalentar.precalentar(renovar=False)


def _ciclo() -> None:
    aplicado = None
    candidato = None
    ultima_revision_triggers = 0.0
    while True:
        try:
            if time.monotonic() - ultima_revision_triggers >= REVISAR_TRIGGERS:
                creados = asegurar_triggers()
                ultima_revision_triggers = time.monotonic()
                if creados:
                    logger.info("datos_version: %s triggers creados", creados)
            estado = _estado()
            if estado is not None:
                huella, quieto_ms = estado
                if aplicado is None:
                    aplicado = huella
                elif huella != aplicado:
                    # Se recarga cuando la huella se repite entre dos revisiones y la base esta quieta:
                    # asi no se toma una carga a medias.
                    if huella == candidato and quieto_ms >= QUIETO_MS:
                        _renovar()
                        aplicado = huella
                    candidato = huella
        except Exception as exc:
            logger.warning("datos_version: %s", exc)
        time.sleep(INTERVALO)


def iniciar() -> None:
    if os.getenv("DATOS_VERSION", "1").strip().lower() in ("0", "false", "no"):
        return
    threading.Thread(target=_ciclo, name="datos_version", daemon=True).start()
