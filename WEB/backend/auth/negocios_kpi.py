"""Negocios que un supervisor puede ver en los KPI (BENCH, KPI Avance Phoenix, KPI Operacional, KPI diario).

Regla: los supervisores ven en los KPI solo los negocios de las productividades a las que tienen acceso
(auth/permissions.py). Asi, al cambiarle la productividad a un supervisor, su KPI cambia solo. Un supervisor
sin productividad no ve ningun negocio. Los demas roles no se restringen.

Cada fuente nombra los negocios a su manera:
  - "bench": columna negocio de dbo.tmp_BENCH_CONTROL_DIARIO (BENCH, KPI Avance Phoenix y KPI diario).
  - "operacional": mandante del KPI Operacional (services/kpi_operacional_service.py).
"""

from __future__ import annotations

import unicodedata

from fastapi import HTTPException

ROLES_RESTRINGIDOS = {"supervisor"}

# Productividad -> negocios en cada fuente. Procuradores no tiene negocio propio en los KPI.
NEGOCIOS_POR_PRODUCTIVIDAD: dict[str, dict[str, list[str]]] = {
    "itau-vencida": {"bench": ["ITAU VENCIDA"], "operacional": ["ITAU VENCIDA"]},
    "itau-vigente": {"bench": ["ITAU VIGENTE"], "operacional": ["ITAU VIGENTE"]},
    "itau-castigo": {"bench": ["ITAU CASTIGO"], "operacional": ["ITAU CASTIGO"]},
    "gm": {"bench": ["GENERAL MOTORS"], "operacional": ["GM"]},
    "sth": {"bench": ["BANCO SANTANDER"], "operacional": ["SANTANDER"]},
    "bit": {"bench": ["BANCO INTERNACIONAL"], "operacional": ["BANCO INTERNACIONAL"]},
    "bit-castigo": {"bench": ["BANCO INTERNACIONAL"], "operacional": ["BANCO INTERNACIONAL"]},
    "la-araucana": {"bench": ["LA ARAUCANA"], "operacional": ["LA ARAUCANA"]},
    # SC Terreno: las tres zonas y el consolidado.
    "sc-tardia": {"bench": ["SC RM", "SC ZONA NORTE", "SC ZONA SUR", "GLOBAL SC"], "operacional": ["SC TERRENO"]},
    "sc-temprana": {"bench": ["SC TELEFONIA"], "operacional": ["SC TELEFONIA"]},
    "sc-piloto": {"bench": ["SC TELEFONIA PILOTO"], "operacional": ["SC PILOTO"]},
}

SIN_NEGOCIO = "No tienes un negocio asignado para ver los KPI. Pide al administrador que te asigne la productividad de tu negocio."


def normalizar(valor) -> str:
    """Mayusculas, sin tildes ni espacios de mas: 'Itaú Vencida ' -> 'ITAU VENCIDA'."""
    texto = unicodedata.normalize("NFD", str(valor or "")).encode("ascii", "ignore").decode("ascii")
    return " ".join(texto.upper().split())


def negocios_permitidos(user: dict | None, fuente: str) -> set[str] | None:
    """Negocios normalizados que puede ver el usuario. None = sin restriccion; vacio = ninguno."""
    if not user or str(user.get("role") or "") not in ROLES_RESTRINGIDOS:
        return None
    acceso = set(user.get("access") or [])
    permitidos: set[str] = set()
    for modulo, fuentes in NEGOCIOS_POR_PRODUCTIVIDAD.items():
        if modulo in acceso:
            permitidos.update(normalizar(v) for v in fuentes.get(fuente, []))
    return permitidos


def filtrar_opciones(opciones: list, permitidos: set[str] | None, clave: str | None = None) -> list:
    """Deja solo las opciones permitidas (strings, o dicts con el valor en `clave`)."""
    if permitidos is None:
        return opciones
    return [op for op in opciones if normalizar(op.get(clave) if clave else op) in permitidos]


def exigir_negocio(user: dict | None, fuente: str, negocio: str | None) -> None:
    """Un supervisor solo consulta un negocio suyo; sin negocio elegido seria ver todos."""
    permitidos = negocios_permitidos(user, fuente)
    if permitidos is None:
        return
    if not permitidos:
        raise HTTPException(status_code=403, detail=SIN_NEGOCIO)
    if not negocio or normalizar(negocio) not in permitidos:
        raise HTTPException(status_code=403, detail="Solo puedes ver los KPI de tu negocio.")


def acotar_lista(user: dict | None, fuente: str, valores: list[str] | None, opciones: list[str]) -> list[str] | None:
    """Filtros de seleccion multiple (mandante del KPI Operacional). Sin seleccion = todos los suyos.

    opciones: los valores tal como los guarda la fuente, para devolver los del supervisor con su escritura.
    """
    permitidos = negocios_permitidos(user, fuente)
    if permitidos is None:
        return valores
    if not permitidos:
        raise HTTPException(status_code=403, detail=SIN_NEGOCIO)
    if valores:
        if any(normalizar(v) not in permitidos for v in valores):
            raise HTTPException(status_code=403, detail="Solo puedes ver los KPI de tu negocio.")
        return valores
    return [v for v in opciones if normalizar(v) in permitidos]
