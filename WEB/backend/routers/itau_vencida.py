from fastapi import APIRouter, Depends, HTTPException, Query

from auth.dependencies import require_module
from services.itau_vencida_service import get_filter_values, get_general


router = APIRouter(dependencies=[Depends(require_module("itau-vencida"))])


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "modulo": "itau-vencida"}


@router.get("/filtros")
def filtros() -> dict:
    try:
        return get_filter_values()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/general")
def general(
    fecha_carga: str | None = Query(default=None),
    ejecutivo: str | None = Query(default=None),
) -> dict:
    try:
        return get_general({"fecha_carga": fecha_carga, "ejecutivo": ejecutivo})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
