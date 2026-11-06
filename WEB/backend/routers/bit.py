from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from auth.dependencies import require_module, require_roles
from excel_export import XLSX_MEDIA_TYPE
from services.bit_excel import build_excel
from services.bit_service import get_detalle, get_filter_values, get_general, get_negocios, get_negocios_detalle, get_tramos


router = APIRouter(dependencies=[Depends(require_module("bit"))])


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "modulo": "bit"}


@router.get("/filtros")
def filtros(periodo: str | None = Query(default=None)) -> dict:
    try:
        return get_filter_values(periodo)
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


@router.get("/negocios")
def negocios(
    periodo: str = Query(...),
    ejecutivo: str | None = Query(default=None),
) -> dict:
    try:
        return get_negocios({"periodo": periodo, "ejecutivo": ejecutivo})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/negocios/detalle")
def negocios_detalle(
    periodo: str = Query(...),
    ejecutivo: str | None = Query(default=None),
) -> dict:
    try:
        return get_negocios_detalle({"periodo": periodo, "ejecutivo": ejecutivo})
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


# Descarga del detalle de todo lo medible del periodo (todos los ejecutivos): solo super admin.
@router.get("/export")
def export(periodo: str = Query(...), _user: dict = Depends(require_roles("super_admin"))) -> StreamingResponse:
    try:
        output, filename = build_excel(periodo)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return StreamingResponse(
        output,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
