from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from auth.dependencies import require_module, require_roles
from excel_export import XLSX_MEDIA_TYPE
from services.itau_vigente_excel import build_excel
from services.itau_vigente_service import get_filter_values, get_general, get_negocios


router = APIRouter(dependencies=[Depends(require_module("itau-vigente"))])


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "modulo": "itau-vigente"}


@router.get("/filtros")
def filtros(fecha_carga: str | None = Query(default=None)) -> dict:
    try:
        return get_filter_values(fecha_carga)
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


@router.get("/negocios")
def negocios(
    fecha_carga: str | None = Query(default=None),
    ejecutivo: str | None = Query(default=None),
) -> dict:
    try:
        return get_negocios({"fecha_carga": fecha_carga, "ejecutivo": ejecutivo})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# Descarga del detalle de todo lo medible de la fecha (todos los ejecutivos): solo super admin.
@router.get("/export")
def export(fecha_carga: str | None = Query(default=None), _user: dict = Depends(require_roles("super_admin"))) -> StreamingResponse:
    try:
        output, filename = build_excel(fecha_carga)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return StreamingResponse(
        output,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
