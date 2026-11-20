from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from auth.dependencies import current_user, require_module
from auth.negocios_kpi import acotar_lista, filtrar_opciones, negocios_permitidos
from services.kpi_operacional_service import SEGMENTACION, get_dashboard, get_filter_values


router = APIRouter(dependencies=[Depends(require_module("kpi-operacional"))])


def _filters(mandante, cartera, tramo, producto, zona, canal=None) -> dict:
    return {"mandante": mandante, "cartera": cartera, "tramo": tramo, "producto": producto, "zona": zona, "canal": canal}


def _mandantes_del_usuario(user: dict, mandante: list[str] | None) -> list[str] | None:
    """Supervisores: solo los mandantes de su productividad; sin eleccion = todos los suyos (auth/negocios_kpi.py)."""
    return acotar_lista(user, "operacional", mandante, list(SEGMENTACION))


@router.get("/filtros")
def filtros(
    mandante: list[str] | None = Query(default=None),
    cartera: list[str] | None = Query(default=None),
    tramo: list[str] | None = Query(default=None),
    producto: list[str] | None = Query(default=None),
    user: dict = Depends(current_user),
) -> dict:
    permitidos = negocios_permitidos(user, "operacional")
    if permitidos is not None and not permitidos:
        return {"mandantes": [], "labels": {}, "visibles": {}, "sin_negocio": True}
    mandante = _mandantes_del_usuario(user, mandante)
    try:
        data = get_filter_values(_filters(mandante, cartera, tramo, producto, None))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    data["mandantes"] = filtrar_opciones(data["mandantes"], permitidos, clave="valor")
    data["sin_negocio"] = False
    return data


@router.get("/dashboard")
def dashboard(
    mandante: list[str] | None = Query(default=None),
    cartera: list[str] | None = Query(default=None),
    tramo: list[str] | None = Query(default=None),
    producto: list[str] | None = Query(default=None),
    zona: list[str] | None = Query(default=None),
    canal: list[str] | None = Query(default=None),
    user: dict = Depends(current_user),
) -> dict:
    """Mes en curso (hasta hoy) vs los 3 meses anteriores al mismo dia habil restante y a su cierre."""
    mandante = _mandantes_del_usuario(user, mandante)
    try:
        # hoy explicito: es parte de la clave de cache del dashboard.
        return get_dashboard(_filters(mandante, cartera, tramo, producto, zona, canal), hoy=date.today())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
