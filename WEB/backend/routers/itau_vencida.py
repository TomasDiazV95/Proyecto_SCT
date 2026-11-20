from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from auth.dependencies import require_module, require_roles
from excel_export import xlsx_response
from services.itau_vencida_excel import build_excel
from services.itau_vencida_service import get_filter_values, get_general, get_negocios
from routers._errores import error_500


router = APIRouter(dependencies=[Depends(require_module("itau-vencida"))])


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "modulo": "itau-vencida"}


@router.get("/filtros")
def filtros(fecha_carga: str | None = Query(default=None)) -> dict:
    try:
        return get_filter_values(fecha_carga)
    except Exception as exc:
        raise error_500(exc) from exc


@router.get("/general")
def general(
    fecha_carga: str | None = Query(default=None),
    ejecutivo: str | None = Query(default=None),
) -> dict:
    try:
        return get_general({"fecha_carga": fecha_carga, "ejecutivo": ejecutivo})
    except Exception as exc:
        raise error_500(exc) from exc


@router.get("/negocios")
def negocios(
    fecha_carga: str | None = Query(default=None),
    ejecutivo: str | None = Query(default=None),
) -> dict:
    try:
        return get_negocios({"fecha_carga": fecha_carga, "ejecutivo": ejecutivo})
    except Exception as exc:
        raise error_500(exc) from exc


# Descarga del detalle de todo lo medible de la fecha (todos los ejecutivos): solo super admin.
@router.get("/export")
def export(fecha_carga: str | None = Query(default=None), _user: dict = Depends(require_roles("super_admin"))) -> StreamingResponse:
    try:
        output, filename = build_excel(fecha_carga)
    except Exception as exc:
        raise error_500(exc) from exc
    return xlsx_response(output, filename)
