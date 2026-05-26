from fastapi import APIRouter, Depends, HTTPException, Query

from auth.dependencies import require_module

from schemas import ApiEnvelope, FiltersResponse
from service import get_cycle_view, get_filter_values, get_general_view


router = APIRouter(dependencies=[Depends(require_module("sc-tardia"))])


@router.get("/filtros", response_model=FiltersResponse)
def filtros() -> FiltersResponse:
    try:
        return FiltersResponse(**get_filter_values())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/productividad/general", response_model=ApiEnvelope)
def productividad_general(
    periodo: str | None = Query(default=None),
    zona: str | None = Query(default=None),
    tramo: str | None = Query(default=None),
    apertura: str | None = Query(default=None),
    ejecutivo: str | None = Query(default=None),
) -> ApiEnvelope:
    try:
        rows = get_general_view(
            {
                "periodo": periodo,
                "zona": zona,
                "tramo": tramo,
                "apertura": apertura,
                "ejecutivo": ejecutivo,
            }
        )
        return ApiEnvelope(data=rows)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/productividad/ciclo", response_model=ApiEnvelope)
def productividad_ciclo(
    ciclo: str | None = Query(default=None),
    periodo: str | None = Query(default=None),
    zona: str | None = Query(default=None),
    tramo: str | None = Query(default=None),
    apertura: str | None = Query(default=None),
    ejecutivo: str | None = Query(default=None),
) -> ApiEnvelope:
    try:
        rows = get_cycle_view(
            {
                "ciclo": ciclo,
                "periodo": periodo,
                "zona": zona,
                "tramo": tramo,
                "apertura": apertura,
                "ejecutivo": ejecutivo,
            }
        )
        return ApiEnvelope(data=rows)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
