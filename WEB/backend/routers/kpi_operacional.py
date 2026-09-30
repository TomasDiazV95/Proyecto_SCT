from fastapi import APIRouter, Depends, HTTPException, Query

from auth.dependencies import require_module
from services.kpi_operacional_service import get_dashboard, get_filter_values


router = APIRouter(dependencies=[Depends(require_module("kpi-operacional"))])


def _filters(mandante, cartera, tramo, producto, zona) -> dict:
    return {"mandante": mandante, "cartera": cartera, "tramo": tramo, "producto": producto, "zona": zona}


@router.get("/filtros")
def filtros(
    mandante: str | None = Query(default=None),
    cartera: str | None = Query(default=None),
    tramo: str | None = Query(default=None),
    producto: str | None = Query(default=None),
) -> dict:
    try:
        return get_filter_values(_filters(mandante, cartera, tramo, producto, None))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/dashboard")
def dashboard(
    mandante: str | None = Query(default=None),
    cartera: str | None = Query(default=None),
    tramo: str | None = Query(default=None),
    producto: str | None = Query(default=None),
    zona: str | None = Query(default=None),
) -> dict:
    """Mes en curso (hasta hoy) vs el cierre de los 3 meses anteriores (sin filtro de periodo)."""
    try:
        return get_dashboard(_filters(mandante, cartera, tramo, producto, zona))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
