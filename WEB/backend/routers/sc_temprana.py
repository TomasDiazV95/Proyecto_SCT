from fastapi import APIRouter, Depends, HTTPException, Query

from auth.dependencies import require_module

from schemas import ApiEnvelope, FiltersResponse
from services.sc_temprana_service import get_cycle_view, get_filter_values, get_general_view


router = APIRouter(dependencies=[Depends(require_module("sc-temprana"))])


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "modulo": "sc-temprana"}


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
    ejecutivo: str | None = Query(default=None),
) -> ApiEnvelope:
    try:
        return ApiEnvelope(
            data=get_general_view(
                {
                    "periodo": periodo,
                    "zona": zona,
                    "tramo": tramo,
                    "ejecutivo": ejecutivo,
                }
            )
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/productividad/ciclo", response_model=ApiEnvelope)
def productividad_ciclo(
    ciclo: str | None = Query(default=None),
    periodo: str | None = Query(default=None),
    zona: str | None = Query(default=None),
    tramo: str | None = Query(default=None),
    ejecutivo: str | None = Query(default=None),
) -> ApiEnvelope:
    try:
        return ApiEnvelope(
            data=get_cycle_view(
                {
                    "ciclo": ciclo,
                    "periodo": periodo,
                    "zona": zona,
                    "tramo": tramo,
                    "ejecutivo": ejecutivo,
                }
            )
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
