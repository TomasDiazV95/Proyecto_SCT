from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from auth.dependencies import require_module
from services.kpi_operacional_service import get_dashboard, get_filter_values


router = APIRouter(dependencies=[Depends(require_module("kpi-operacional"))])


def _filters(mandante, cartera, tramo, producto, zona, canal=None) -> dict:
    return {"mandante": mandante, "cartera": cartera, "tramo": tramo, "producto": producto, "zona": zona, "canal": canal}


@router.get("/filtros")
def filtros(
    mandante: list[str] | None = Query(default=None),
    cartera: list[str] | None = Query(default=None),
    tramo: list[str] | None = Query(default=None),
    producto: list[str] | None = Query(default=None),
) -> dict:
    try:
        return get_filter_values(_filters(mandante, cartera, tramo, producto, None))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/dashboard")
def dashboard(
    mandante: list[str] | None = Query(default=None),
    cartera: list[str] | None = Query(default=None),
    tramo: list[str] | None = Query(default=None),
    producto: list[str] | None = Query(default=None),
    zona: list[str] | None = Query(default=None),
    canal: list[str] | None = Query(default=None),
) -> dict:
    """Mes en curso (hasta hoy) vs los 3 meses anteriores al mismo dia habil restante y a su cierre."""
    try:
        # hoy explicito: es parte de la clave de cache del dashboard.
        return get_dashboard(_filters(mandante, cartera, tramo, producto, zona, canal), hoy=date.today())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
