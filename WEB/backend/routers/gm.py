from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from excel_export import XLSX_MEDIA_TYPE
from auth.dependencies import require_module, require_roles
from schemas import ApiEnvelope
from services.negocios_service import get_conteo as get_negocios_conteo
from services.negocios_service import get_detalle as get_negocios_detalle
from services.gm_excel import build_excel
from services.gm_service import (
    get_bucket_view,
    get_cycle_view,
    get_detail_view,
    get_filter_values,
    get_general_view,
)


router = APIRouter(dependencies=[Depends(require_module("gm"))])


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "modulo": "gm"}


@router.get("/filtros")
def filtros(periodo: str | None = Query(default=None)) -> dict:
    try:
        return get_filter_values(periodo)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/productividad/ciclo", response_model=ApiEnvelope)
def productividad_ciclo(
    periodo: str | None = Query(default=None),
    ejecutivo: str | None = Query(default=None),
) -> ApiEnvelope:
    try:
        return ApiEnvelope(
            data=get_cycle_view(
                {
                    "periodo": periodo,
                    "ejecutivo": ejecutivo,
                }
            )
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/productividad/general", response_model=ApiEnvelope)
def productividad_general(
    periodo: str | None = Query(default=None),
    ejecutivo: str | None = Query(default=None),
) -> ApiEnvelope:
    try:
        return ApiEnvelope(
            data=get_general_view(
                {
                    "periodo": periodo,
                    "ejecutivo": ejecutivo,
                }
            )
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/productividad/bucket", response_model=ApiEnvelope)
def productividad_bucket(
    periodo: str | None = Query(default=None),
) -> ApiEnvelope:
    try:
        return ApiEnvelope(data=get_bucket_view({"periodo": periodo}))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/detalle", response_model=ApiEnvelope)
def detalle(
    periodo: str | None = Query(default=None),
    op: str | None = Query(default=None),
    bucket: str | None = Query(default=None),
    ejecutivo: str | None = Query(default=None),
    contenido: str | None = Query(default=None),
    normalizado: str | None = Query(default=None),
) -> ApiEnvelope:
    try:
        return ApiEnvelope(
            data=get_detail_view(
                {
                    "periodo": periodo,
                    "op": op,
                    "bucket": bucket,
                    "ejecutivo": ejecutivo,
                    "contenido": contenido,
                    "normalizado": normalizado,
                }
            )
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# Descarga del detalle de todo lo medible del mes (todos los ejecutivos): solo super admin.
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


@router.get("/negocios")
def negocios(
    periodo: str | None = Query(default=None),
    ejecutivo: str | None = Query(default=None),
) -> dict:
    try:
        return get_negocios_conteo("gm", periodo, ejecutivo)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/negocios/detalle")
def negocios_detalle(
    periodo: str | None = Query(default=None),
    ejecutivo: str | None = Query(default=None),
) -> dict:
    try:
        return get_negocios_detalle("gm", periodo, ejecutivo)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
