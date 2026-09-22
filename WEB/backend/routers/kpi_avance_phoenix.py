from fastapi import APIRouter, Depends, HTTPException, Query

from auth.dependencies import require_module
from services.kpi_avance_phoenix_service import get_comparison_view, get_filter_values


router = APIRouter(dependencies=[Depends(require_module("kpi-diario"))])


@router.get("/filtros")
def filtros(
    negocio: str | None = Query(default=None),
    segmento: str | None = Query(default=None),
) -> dict:
    try:
        return get_filter_values({"negocio": negocio, "segmento": segmento})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/comparacion")
def comparacion(
    periodos: list[str] | None = Query(default=None),
    negocio: str | None = Query(default=None),
    segmento: str | None = Query(default=None),
) -> dict:
    try:
        return get_comparison_view({"periodos": periodos, "negocio": negocio, "segmento": segmento})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
