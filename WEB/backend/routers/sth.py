from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from auth.dependencies import require_module, require_roles
from excel_export import XLSX_MEDIA_TYPE
from schemas import ApiEnvelope
from services.negocios_service import get_conteo as get_negocios_conteo
from services.negocios_service import get_detalle as get_negocios_detalle
from services.sth_excel import build_excel
from services.sth_service import get_detail_view, get_filter_values, get_general_view, get_metas, get_operations_detail_view


router = APIRouter(dependencies=[Depends(require_module("sth"))])


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "modulo": "sth"}


@router.get("/filtros")
def filtros(periodo: str | None = Query(default=None)) -> dict:
    try:
        return get_filter_values(periodo)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/metas", response_model=ApiEnvelope)
def metas(periodo: str | None = Query(default=None)) -> ApiEnvelope:
    try:
        return ApiEnvelope(data=get_metas({"periodo": periodo}))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/productividad/general", response_model=ApiEnvelope)
def productividad_general(
    periodo: str | None = Query(default=None),
    ejecutivo: str | None = Query(default=None),
) -> ApiEnvelope:
    try:
        return ApiEnvelope(data=get_general_view({"periodo": periodo, "ejecutivo": ejecutivo}))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/productividad/desglosada", response_model=ApiEnvelope)
def productividad_desglosada(
    periodo: str | None = Query(default=None),
    ejecutivo: str | None = Query(default=None),
) -> ApiEnvelope:
    try:
        return ApiEnvelope(data=get_detail_view({"periodo": periodo, "ejecutivo": ejecutivo}))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/detalle")
def detalle(
    periodo: str | None = Query(default=None),
    operacion: str | None = Query(default=None),
    ejecutivo: str | None = Query(default=None),
    producto: str | None = Query(default=None),
    ciclo: str | None = Query(default=None),
    contenido: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
) -> dict:
    try:
        return get_operations_detail_view(
            {
                "periodo": periodo,
                "operacion": operacion,
                "ejecutivo": ejecutivo,
                "producto": producto,
                "ciclo": ciclo,
                "contenido": contenido,
                "page": page,
                "page_size": page_size,
            }
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/export")
def export(periodo: str = Query(...), _user: dict = Depends(require_roles("super_admin"))) -> StreamingResponse:
    try:
        output, filename = build_excel(periodo)
        return StreamingResponse(
            output,
            media_type=XLSX_MEDIA_TYPE,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/negocios")
def negocios(
    periodo: str | None = Query(default=None),
    ejecutivo: str | None = Query(default=None),
) -> dict:
    try:
        return get_negocios_conteo("sth", periodo, ejecutivo)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/negocios/detalle")
def negocios_detalle(
    periodo: str | None = Query(default=None),
    ejecutivo: str | None = Query(default=None),
) -> dict:
    try:
        return get_negocios_detalle("sth", periodo, ejecutivo)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
