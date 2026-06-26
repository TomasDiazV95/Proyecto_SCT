from fastapi import APIRouter, Depends, HTTPException, Query

from auth.dependencies import require_module

from schemas import ApiEnvelope
from services.sc_temprana_service import get_cycle_view, get_detail_view, get_filter_values, get_general_view


router = APIRouter(dependencies=[Depends(require_module("sc-temprana"))])


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "modulo": "sc-temprana"}


@router.get("/filtros")
def filtros() -> dict:
    try:
        return get_filter_values()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/productividad/general", response_model=ApiEnvelope)
def productividad_general(
    periodo: str | None = Query(default=None),
    ejecutivo: str | None = Query(default=None),
) -> ApiEnvelope:
    try:
        return ApiEnvelope(data=get_general_view({"periodo": periodo, "ejecutivo": ejecutivo}))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/productividad/ciclo", response_model=ApiEnvelope)
def productividad_ciclo(
    periodo: str | None = Query(default=None),
    ejecutivo: str | None = Query(default=None),
) -> ApiEnvelope:
    try:
        return ApiEnvelope(data=get_cycle_view({"periodo": periodo, "ejecutivo": ejecutivo}))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/detalle")
def detalle(
    periodo: str | None = Query(default=None),
    operacion: str | None = Query(default=None),
    contenido: str | None = Query(default=None),
    normalizado: str | None = Query(default=None),
    usuario_gestion: str | None = Query(default=None),
    tramo: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
) -> dict:
    try:
        return get_detail_view(
            {
                "periodo": periodo,
                "operacion": operacion,
                "contenido": contenido,
                "normalizado": normalizado,
                "usuario_gestion": usuario_gestion,
                "tramo": tramo,
                "page": page,
                "page_size": page_size,
            }
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


