from fastapi import APIRouter, Depends, HTTPException, Query

from auth.dependencies import require_module
from services.gestiones_diarias_sct_service import get_detail_view, get_filter_values, get_summary_view


router = APIRouter(dependencies=[Depends(require_module("gestiones-diarias-sct"))])


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "modulo": "gestiones-diarias-sct"}


@router.get("/filtros")
def filtros(
    fecha_desde: str | None = Query(default=None),
    fecha_hasta: str | None = Query(default=None),
    ejecutivo: str | None = Query(default=None),
    contacto: str | None = Query(default=None),
    accion: str | None = Query(default=None),
    canal: str | None = Query(default=None),
    estado: str | None = Query(default=None),
    tramo_mora: str | None = Query(default=None),
    zona: str | None = Query(default=None),
) -> dict:
    try:
        return get_filter_values(
            {
                "fecha_desde": fecha_desde,
                "fecha_hasta": fecha_hasta,
                "ejecutivo": ejecutivo,
                "contacto": contacto,
                "accion": accion,
                "canal": canal,
                "estado": estado,
                "tramo_mora": tramo_mora,
                "zona": zona,
            }
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/detalle")
def detalle(
    fecha_desde: str | None = Query(default=None),
    fecha_hasta: str | None = Query(default=None),
    ejecutivo: str | None = Query(default=None),
    ejecutivos: str | None = Query(default=None),
    contacto: str | None = Query(default=None),
    accion: str | None = Query(default=None),
    canal: str | None = Query(default=None),
    estado: str | None = Query(default=None),
    tramo_mora: str | None = Query(default=None),
    zona: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
) -> dict:
    try:
        return get_detail_view(
            {
                "fecha_desde": fecha_desde,
                "fecha_hasta": fecha_hasta,
                "ejecutivo": ejecutivo,
                "ejecutivos": ejecutivos,
                "contacto": contacto,
                "accion": accion,
                "canal": canal,
                "estado": estado,
                "tramo_mora": tramo_mora,
                "zona": zona,
                "page": page,
                "page_size": page_size,
            }
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/resumen")
def resumen(
    fecha_desde: str | None = Query(default=None),
    fecha_hasta: str | None = Query(default=None),
    ejecutivo: str | None = Query(default=None),
    ejecutivos: str | None = Query(default=None),
    contacto: str | None = Query(default=None),
    canal: str | None = Query(default=None),
    tramo_mora: str | None = Query(default=None),
    zona: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
) -> dict:
    try:
        return get_summary_view(
            {
                "fecha_desde": fecha_desde,
                "fecha_hasta": fecha_hasta,
                "ejecutivo": ejecutivo,
                "ejecutivos": ejecutivos,
                "contacto": contacto,
                "canal": canal,
                "tramo_mora": tramo_mora,
                "zona": zona,
                "page": page,
                "page_size": page_size,
            }
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
