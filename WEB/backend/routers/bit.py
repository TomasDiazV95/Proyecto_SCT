from fastapi import APIRouter, Depends, HTTPException, Query

from auth.dependencies import require_module
from services.bit_service import get_detalle, get_filter_values, get_general, get_tramos


router = APIRouter(dependencies=[Depends(require_module("bit"))])


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "modulo": "bit"}


@router.get("/filtros")
def filtros() -> dict:
    try:
        return get_filter_values()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/general")
def general(
    periodo: str = Query(...),
    ejecutivo: str | None = Query(default=None),
    tramo: str | None = Query(default=None),
) -> dict:
    try:
        return get_general({"periodo": periodo, "ejecutivo": ejecutivo, "tramo": tramo})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/tramos")
def tramos(
    periodo: str = Query(...),
    ejecutivo: str | None = Query(default=None),
    tramo: str | None = Query(default=None),
) -> dict:
    try:
        return get_tramos({"periodo": periodo, "ejecutivo": ejecutivo, "tramo": tramo})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/detalle")
def detalle(
    periodo: str = Query(...),
    ejecutivo: str | None = Query(default=None),
    tramo: str | None = Query(default=None),
) -> dict:
    try:
        return get_detalle({"periodo": periodo, "ejecutivo": ejecutivo, "tramo": tramo})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
