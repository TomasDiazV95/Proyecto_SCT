from fastapi import APIRouter, Depends, HTTPException, Query

from auth.dependencies import require_module

from schemas import ApiEnvelope, FiltersResponse
from service import get_cycle_view, get_filter_values, get_general_view


router = APIRouter(dependencies=[Depends(require_module("kpi-diario"))])


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "modulo": "kpi-diario"}


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
    ejecutivo: str | None = Query(default=None),
) -> ApiEnvelope:
    try:
        return ApiEnvelope(data=get_general_view({"periodo": periodo, "zona": zona, "ejecutivo": ejecutivo}))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/productividad/ciclo", response_model=ApiEnvelope)
def productividad_ciclo(
    periodo: str | None = Query(default=None),
    zona: str | None = Query(default=None),
    ejecutivo: str | None = Query(default=None),
    ciclo: str | None = Query(default=None),
) -> ApiEnvelope:
    try:
        return ApiEnvelope(data=get_cycle_view({"periodo": periodo, "zona": zona, "ejecutivo": ejecutivo, "ciclo": ciclo}))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
