from fastapi import APIRouter, Depends, HTTPException, Query

from auth.dependencies import require_module
from services.bit_castigo_service import get_filter_values, get_general


router = APIRouter(dependencies=[Depends(require_module("bit-castigo"))])


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "modulo": "bit-castigo"}


@router.get("/filtros")
def filtros() -> dict:
    try:
        return get_filter_values()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/general")
def general(
    periodo: str | None = Query(default=None),
    ejecutivo: str | None = Query(default=None),
) -> dict:
    try:
        return get_general({"periodo": periodo, "ejecutivo": ejecutivo})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
