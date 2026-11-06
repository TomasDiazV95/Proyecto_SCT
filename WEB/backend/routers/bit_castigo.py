from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from auth.dependencies import require_module, require_roles
from excel_export import XLSX_MEDIA_TYPE
from services.bit_castigo_excel import build_excel
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


# Descarga del detalle de todo lo medible del periodo (todos los ejecutivos): solo super admin.
@router.get("/export")
def export(periodo: str | None = Query(default=None), _user: dict = Depends(require_roles("super_admin"))) -> StreamingResponse:
    try:
        output, filename = build_excel(periodo)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return StreamingResponse(
        output,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
