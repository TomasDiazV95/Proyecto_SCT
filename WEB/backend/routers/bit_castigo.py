from fastapi import APIRouter, Depends, HTTPException, Query

from auth.dependencies import require_module
from services.bit_castigo_service import get_filter_values, get_general, get_nuevos_convenios


router = APIRouter(dependencies=[Depends(require_module("bit-castigo"))])


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "modulo": "bit-castigo"}


@router.get("/filtros")
def filtros(periodo: str | None = Query(default=None)) -> dict:
    try:
        return get_filter_values(periodo)
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


@router.get("/nuevos-convenios")
def nuevos_convenios(
    periodo: str | None = Query(default=None),
    ejecutivo: str | None = Query(default=None),
) -> dict:
    try:
        return {"rows": get_nuevos_convenios({"periodo": periodo, "ejecutivo": ejecutivo})}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
