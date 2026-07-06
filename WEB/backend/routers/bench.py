from fastapi import APIRouter, Depends, HTTPException, Query

from auth.dependencies import current_user, require_module
from services.bench_service import get_filter_values, get_kpi_view


router = APIRouter(dependencies=[Depends(require_module("bench"))])


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "modulo": "bench"}


@router.get("/filtros")
def filtros(
    periodo: str | None = Query(default=None),
    negocio: str | None = Query(default=None),
    user: dict = Depends(current_user),
) -> dict:
    try:
        return get_filter_values({"periodo": periodo, "negocio": negocio}, user=user)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/kpi")
def kpi(
    periodo: str | None = Query(default=None),
    negocio: str | None = Query(default=None),
    segmento: str | None = Query(default=None),
    user: dict = Depends(current_user),
) -> dict:
    try:
        return get_kpi_view({"periodo": periodo, "negocio": negocio, "segmento": segmento}, user=user)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
