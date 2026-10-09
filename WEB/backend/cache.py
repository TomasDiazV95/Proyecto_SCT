"""Cache en memoria de los resultados de consulta, compartida por los servicios.

Las tablas de origen solo cambian cuando corre una carga; mientras tanto se reutiliza el resultado.
"""
from __future__ import annotations

import contextlib
import contextvars
import copy
import functools
import json
import threading
import time


CACHE_TTL = 300  # segundos

_cache: dict[tuple, tuple[float, object]] = {}
_cache_locks: dict[tuple, threading.Lock] = {}
_cache_guard = threading.Lock()
_generacion = 0
# Durante el precalentamiento: claves ya recargadas en esta pasada (None fuera de el).
_refrescando: contextvars.ContextVar[set | None] = contextvars.ContextVar("cache_refrescando", default=None)
_ultimo_uso = 0.0


def cached(key: tuple, loader, ttl: float = CACHE_TTL):
    """Resultado de loader() en cache por ttl segundos. El candado es por clave: si dos pedidos
    necesitan lo mismo a la vez, la consulta corre una sola vez.

    Devuelve el objeto guardado: quien lo recibe no debe modificarlo (ver cached_view)."""
    global _ultimo_uso
    recargadas = _refrescando.get()
    if recargadas is not None and key not in recargadas:
        # Recarga sin tomar el candado: mientras tanto los pedidos siguen recibiendo lo guardado.
        recargadas.add(key)
        return _guardar(key, _generacion, loader())
    if recargadas is None:
        _ultimo_uso = time.monotonic()
    with _cache_guard:
        lock = _cache_locks.setdefault(key, threading.Lock())
    with lock:
        cached_value = _cache.get(key)
        if cached_value and time.monotonic() - cached_value[0] < ttl:
            return cached_value[1]
        return _guardar(key, _generacion, loader())


def _guardar(key: tuple, generacion: int, value):
    with _cache_guard:
        now = time.monotonic()
        for old_key in [k for k, (created, _) in _cache.items() if now - created >= CACHE_TTL]:
            _cache.pop(old_key, None)
        # Si se limpio la cache mientras corria la consulta, el resultado puede venir de datos viejos.
        if generacion == _generacion:
            _cache[key] = (now, value)
    return value


@contextlib.contextmanager
def refrescando():
    """Dentro de este bloque todo se vuelve a consultar y reemplaza lo guardado (precalentamiento)."""
    token = _refrescando.set(set())
    try:
        yield
    finally:
        _refrescando.reset(token)


def segundos_sin_uso() -> float:
    """Tiempo desde el ultimo pedido a la cache (sin contar el precalentamiento)."""
    return time.monotonic() - _ultimo_uso


def clear() -> None:
    """Olvida todo lo guardado. Se llama cuando la aplicacion modifica datos que cambian los resultados."""
    global _generacion
    with _cache_guard:
        _generacion += 1
        _cache.clear()


def forget(key: tuple) -> None:
    """Olvida una clave puntual."""
    with _cache_guard:
        _cache.pop(key, None)


def _sin_vacios(value):
    """Un filtro vacio equivale a no enviarlo: {'ejecutivo': None} y {} comparten clave."""
    if isinstance(value, dict):
        return {k: v for k, v in value.items() if v not in (None, "")}
    return value


def cached_view(fn):
    """Guarda en cache el resultado de una funcion de lectura segun sus argumentos (filtros).

    Entrega una copia en cada llamada, asi quien la recibe puede modificarla sin tocar lo guardado."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        posicionales = [_sin_vacios(arg) for arg in args]
        while posicionales and posicionales[-1] in (None, ""):
            posicionales.pop()
        nombrados = {k: _sin_vacios(v) for k, v in kwargs.items() if v not in (None, "")}
        argumentos = json.dumps([posicionales, nombrados], sort_keys=True, default=str)
        key = (fn.__module__, fn.__qualname__, argumentos)
        return copy.deepcopy(cached(key, lambda: fn(*args, **kwargs)))

    return wrapper
