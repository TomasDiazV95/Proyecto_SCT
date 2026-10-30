"""Recalcula el KPI Operacional apenas cambian sus tablas fuente, solo en los mandantes que cambiaron.

Las tablas del KPI (kpi_asignacion, kpi_pagos_diario, ...) las arma dbo.sp_kpi_operacional_cargar. Un hilo revisa
cada tabla que lee ese SP con la misma huella de datos_version (triggers + conteo de filas); cuando alguna cambia y
lleva unos segundos quieta (la carga termino), recalcula el mes en curso solo para los grupos de esas tablas
(@grupos: si carga el CRM, solo gestiones y compromisos; si carga BIT, solo BIT). Al terminar, datos_version ve el
cambio en las kpi_* y renueva la cache, asi las paginas abiertas se actualizan solas.

El SP calcula en temporales y escribe solo las filas que cambiaron, asi la web no queda esperando.
La tarea programada KPI_Operacional_Carga (cada hora, los 4 meses y todos los grupos) queda de respaldo.

Se apaga con KPI_AUTO=0 en el entorno.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import date, timedelta

from database import get_connection


logger = logging.getLogger("uvicorn.error")

# Grupos de dbo.sp_kpi_operacional_cargar_periodo (SQL/007_kpi_operacional.sql) y las tablas que lee cada uno.
GRUPOS = {
    "ITAU": ["asignacion_itau_vencida", "contencion_itau_vencida", "recup_itau_castigo", "tmp_itau_castigo_asignacion"],
    "BIT": ["tmp_BIT_asignacion", "tmp_BIT_contencion", "tmp_BIT_castigo"],
    "GM": ["tmp_asig_GM", "tmp_pagos_gm"],
    "SANTANDER": ["tmp_bench_STH"],
    "SC_TELEFONIA": ["tmp_bench_temp_STC"],
    "SC_PILOTO": ["tmp_bench_STC_tel"],
    "SC_TERRENO": ["tmp_bench_STC"],
    "LA_ARAUCANA": ["tmp_LA_asignacion", "tmp_LA_pagos"],
    "FORUM": ["tmp_asignacion_forum"],
    "CRM": ["tmp_GEST_CRM", "tmp_FECHA_COMPROMISO_CRM", "kpi_crm_cartera", "kpi_tipo_contacto", "kpi_accion_canal"],
}
FUENTES = [tabla for tablas in GRUPOS.values() for tabla in tablas]
GRUPO_DE = {tabla: grupo for grupo, tablas in GRUPOS.items() for tabla in tablas}

INTERVALO = 5  # segundos entre revisiones
QUIETO_MS = 15000  # las fuentes deben llevar este tiempo sin cambios (los ETL hacen commit por lotes seguidos)
# Primeros dias del mes: tambien se recalcula el anterior (el dashboard puede mostrarlo y le llegan archivos tardios).
DIAS_MES_ANTERIOR = 5

# Por tabla: version (triggers de datos_version), filas (TRUNCATE o tablas que el ETL vuelve a crear) y cuanto
# lleva quieta.
_ESTADO_SQL = """
SET LOCK_TIMEOUT 2000;
SELECT t.name AS tabla, v.version, DATEDIFF_BIG(MILLISECOND, v.actualizado, SYSDATETIME()) AS quieto_ms,
       (SELECT SUM(p.row_count) FROM sys.dm_db_partition_stats p
        WHERE p.object_id = t.object_id AND p.index_id IN (0, 1)) AS filas
FROM sys.tables t
LEFT JOIN dbo.datos_version v ON v.tabla = t.name
WHERE t.schema_id = SCHEMA_ID('dbo') AND t.name IN ({tablas});
"""


def _periodos(hoy: date) -> list[str]:
    inicio = hoy.replace(day=1)
    periodos = [f"{inicio:%Y-%m}"]
    if hoy.day <= DIAS_MES_ANTERIOR:
        periodos.insert(0, f"{inicio - timedelta(days=1):%Y-%m}")
    return periodos


def _estado() -> dict[str, tuple] | None:
    """{tabla: ((version, filas), quieto_ms)} de las fuentes; None si una carga tiene tomada una tabla."""
    try:
        with get_connection() as cn:
            cur = cn.cursor()
            cur.execute(_ESTADO_SQL.format(tablas=", ".join(f"N'{t}'" for t in FUENTES)))
            while cur.description is None and cur.nextset():
                pass
            rows = cur.fetchall()
    except Exception as exc:  # lock timeout mientras una carga no hace commit, o la BD no responde
        logger.debug("kpi_auto: sin estado (%s)", exc)
        return None
    return {r.tabla: ((r.version, r.filas), r.quieto_ms if r.quieto_ms is not None else QUIETO_MS) for r in rows}


def cargar(periodos: list[str], grupos: list[str] | None = None) -> None:
    """Corre el SP del KPI para cada periodo; grupos=None recalcula todos."""
    with get_connection() as cn:
        cn.autocommit = True
        cur = cn.cursor()
        for periodo in periodos:
            cur.execute(
                "EXEC dbo.sp_kpi_operacional_cargar @periodo = ?, @grupos = ?",
                (periodo, "|".join(grupos) if grupos else None),
            )
            # Los result sets del SP (filas por paso) se recorren para que termine y aparezca cualquier error.
            while cur.nextset():
                pass


def _ciclo() -> None:
    aplicado: dict | None = None
    candidato: dict | None = None
    while True:
        try:
            estado = _estado()
            if estado is not None:
                huellas = {t: h for t, (h, _) in estado.items()}
                if aplicado is None:
                    aplicado = huellas
                else:
                    cambiadas = [t for t, h in huellas.items() if aplicado.get(t) != h]
                    # Igual que datos_version: la huella se repite entre dos revisiones y las tablas que cambiaron
                    # estan quietas.
                    if (
                        cambiadas
                        and huellas == candidato
                        and all(estado[t][1] >= QUIETO_MS for t in cambiadas)
                    ):
                        # Se marca antes de cargar: lo que llegue mientras corre dispara otra carga.
                        aplicado = huellas
                        grupos = sorted({GRUPO_DE[t] for t in cambiadas})
                        periodos = _periodos(date.today())
                        logger.info(
                            "kpi_auto: cambiaron %s, cargando %s (%s)",
                            ", ".join(cambiadas), ", ".join(periodos), ", ".join(grupos),
                        )
                        inicio = time.perf_counter()
                        cargar(periodos, grupos)
                        logger.info("kpi_auto: KPI Operacional cargado en %.1fs", time.perf_counter() - inicio)
                    candidato = huellas
        except Exception as exc:  # una carga que falla se reintenta con el siguiente cambio
            logger.warning("kpi_auto: %s", exc)
        time.sleep(INTERVALO)


def iniciar() -> None:
    if os.getenv("KPI_AUTO", "1").strip().lower() in ("0", "false", "no"):
        return
    threading.Thread(target=_ciclo, name="kpi_auto", daemon=True).start()
