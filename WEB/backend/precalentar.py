"""Deja en cache lo que cada productividad pide al abrirse, para que la primera visita no espere.

Corre en un hilo al iniciar la API y se repite antes de que venza la cache. Se apaga con
PRECALENTAR=0 en el entorno.
"""
from __future__ import annotations

import contextlib
import functools
import importlib
import logging
import os
import threading
import time
from datetime import date

import cache


logger = logging.getLogger("uvicorn.error")

# (servicio, funcion de filtros, nombre del filtro de fecha, vistas de la pagina)
MODULOS = [
    ("sc_tardia", "get_filter_values", "periodo", ["get_general_view", "get_cycle_view", "get_metas"]),
    ("sc_temprana", "get_filter_values", "periodo", ["get_cycle_view"]),
    ("gm", "get_filter_values", "periodo", ["get_cycle_view", "get_bucket_view", "get_general_view"]),
    ("itau_castigo", "get_filter_values", "fecha_carga", ["get_general", "get_producto"]),
    ("itau_vencida", "get_filter_values", "fecha_carga", ["get_general"]),
    ("itau_vigente", "get_filter_values", "fecha_carga", ["get_general"]),
    ("sth", "get_filter_values", "periodo", ["get_general_view", "get_detail_view", "get_metas"]),
    ("bit", "get_filter_values", "periodo", ["get_general", "get_tramos", "get_negocios"]),
    ("la_araucana", "get_filtros", "periodo", ["get_resumen", "get_negocios"]),
    ("bit_castigo", "get_filter_values", "periodo", ["get_general"]),
]

# Se recarga un minuto antes de que venza lo guardado.
INTERVALO = cache.CACHE_TTL - 60  # segundos
# Sin visitas en este tiempo no se recarga (noches, fines de semana).
PAUSA_SIN_USO = 30 * 60  # segundos


def precalentar_modulo(nombre: str, fn_filtros: str, clave_fecha: str, vistas: list[str]) -> None:
    """Filtros y vistas de la fecha mas reciente del modulo, tal como los pide la pagina al abrirse."""
    servicio = importlib.import_module(f"services.{nombre}_service")
    filtros_fn = getattr(servicio, fn_filtros)
    filtros = filtros_fn(None)
    fechas = filtros.get("periodos") or filtros.get("fechas_carga") or []
    if not fechas:
        return
    filtros_fn(fechas[0])
    for vista in vistas:
        getattr(servicio, vista)({clave_fecha: fechas[0]})


def precalentar_kpi_operacional() -> None:
    """KPI Operacional no se filtra por fecha: filtros y vista inicial (todos los mandantes), con la misma
    clave que pide la pagina. Los mandantes quedan en cache con la primera visita."""
    servicio = importlib.import_module("services.kpi_operacional_service")
    servicio.get_filter_values({})
    servicio.get_dashboard({}, hoy=date.today())


def precalentar(renovar: bool = True) -> None:
    """renovar=True vuelve a consultar aunque haya algo guardado (ciclo periodico). Con False usa los
    candados de la cache: sirve justo despues de limpiarla, cuando las paginas abiertas tambien piden."""
    pasos = [(modulo[0], functools.partial(precalentar_modulo, *modulo)) for modulo in MODULOS]
    pasos.append(("kpi_operacional", precalentar_kpi_operacional))
    with cache.refrescando() if renovar else contextlib.nullcontext():
        for nombre, paso in pasos:
            inicio = time.perf_counter()
            try:
                paso()
            except Exception as exc:  # un modulo que falla no detiene a los demas
                logger.warning("Precalentamiento de %s fallo: %s", nombre, exc)
            else:
                logger.info("Precalentado %s en %.1fs", nombre, time.perf_counter() - inicio)


def _ciclo() -> None:
    precalentar()
    while True:
        time.sleep(INTERVALO)
        if cache.segundos_sin_uso() < PAUSA_SIN_USO:
            precalentar()


def iniciar() -> None:
    if os.getenv("PRECALENTAR", "1").strip().lower() in ("0", "false", "no"):
        return
    threading.Thread(target=_ciclo, name="precalentar", daemon=True).start()
