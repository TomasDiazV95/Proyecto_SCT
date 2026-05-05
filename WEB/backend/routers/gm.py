from fastapi import APIRouter, HTTPException, Query

from schemas import ApiEnvelope
from services.gm_service import (
    get_bucket_view,
    get_cycle_view,
    get_filter_values,
    get_general_view,
)


router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "modulo": "gm"}


@router.get("/filtros")
def filtros() -> dict:
    try:
        return get_filter_values()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/productividad/ciclo", response_model=ApiEnvelope)
def productividad_ciclo(
    periodo: str | None = Query(default=None),
    ejecutivo: str | None = Query(default=None),
) -> ApiEnvelope:
    try:
        return ApiEnvelope(
            data=get_cycle_view(
                {
                    "periodo": periodo,
                    "ejecutivo": ejecutivo,
                }
            )
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/productividad/general", response_model=ApiEnvelope)
def productividad_general(
    periodo: str | None = Query(default=None),
    ejecutivo: str | None = Query(default=None),
) -> ApiEnvelope:
    try:
        return ApiEnvelope(
            data=get_general_view(
                {
                    "periodo": periodo,
                    "ejecutivo": ejecutivo,
                }
            )
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/productividad/bucket", response_model=ApiEnvelope)
def productividad_bucket(
    periodo: str | None = Query(default=None),
) -> ApiEnvelope:
    try:
        return ApiEnvelope(data=get_bucket_view({"periodo": periodo}))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
