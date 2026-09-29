from fastapi import APIRouter, Depends, HTTPException, Query

from auth.dependencies import require_module
from services.kpi_operacional_service import get_dashboard, get_filter_values


router = APIRouter(dependencies=[Depends(require_module("kpi-operacional"))])


def _filters(periodo, mandante, cartera, tramo, producto) -> dict:
    return {"periodo": periodo, "mandante": mandante, "cartera": cartera, "tramo": tramo, "producto": producto}


@router.get("/filtros")
def filtros(
    periodo: str | None = Query(default=None),
    mandante: str | None = Query(default=None),
    cartera: str | None = Query(default=None),
    tramo: str | None = Query(default=None),
) -> dict:
    try:
        return get_filter_values(_filters(periodo, mandante, cartera, tramo, None))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/dashboard")
def dashboard(
    periodo: str | None = Query(default=None),
    mandante: str | None = Query(default=None),
    cartera: str | None = Query(default=None),
    tramo: str | None = Query(default=None),
    producto: str | None = Query(default=None),
) -> dict:
    try:
        return get_dashboard(_filters(periodo, mandante, cartera, tramo, producto))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
