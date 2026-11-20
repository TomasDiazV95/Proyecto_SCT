from fastapi import APIRouter, Depends, HTTPException, Query

from auth.dependencies import current_user, require_module
from auth.negocios_kpi import exigir_negocio, filtrar_opciones, negocios_permitidos

from schemas import ApiEnvelope, FiltersResponse
from service import get_cycle_view, get_filter_values, get_general_view


router = APIRouter(dependencies=[Depends(require_module("kpi-diario"))])


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "modulo": "kpi-diario"}


@router.get("/filtros", response_model=FiltersResponse)
def filtros(negocio: str | None = Query(default=None), user: dict = Depends(current_user)) -> FiltersResponse:
    if negocio:
        exigir_negocio(user, "bench", negocio)
    try:
        data = get_filter_values({"negocio": negocio})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    # Supervisores: solo los negocios de su productividad (auth/negocios_kpi.py).
    data["negocios"] = filtrar_opciones(data.get("negocios") or [], negocios_permitidos(user, "bench"))
    return FiltersResponse(**data)


@router.get("/productividad/general", response_model=ApiEnvelope)
def productividad_general(
    periodo: str | None = Query(default=None),
    zona: str | None = Query(default=None),
    ejecutivo: str | None = Query(default=None),
    negocio: str | None = Query(default=None),
    segmento: str | None = Query(default=None),
    user: dict = Depends(current_user),
) -> ApiEnvelope:
    exigir_negocio(user, "bench", negocio)
    try:
        return ApiEnvelope(data=get_general_view({"periodo": periodo, "zona": zona, "ejecutivo": ejecutivo, "negocio": negocio, "segmento": segmento}))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/productividad/ciclo", response_model=ApiEnvelope)
def productividad_ciclo(
    periodo: str | None = Query(default=None),
    zona: str | None = Query(default=None),
    ejecutivo: str | None = Query(default=None),
    ciclo: str | None = Query(default=None),
    negocio: str | None = Query(default=None),
    segmento: str | None = Query(default=None),
    user: dict = Depends(current_user),
) -> ApiEnvelope:
    exigir_negocio(user, "bench", negocio)
    try:
        return ApiEnvelope(data=get_cycle_view({"periodo": periodo, "zona": zona, "ejecutivo": ejecutivo, "ciclo": ciclo, "negocio": negocio, "segmento": segmento}))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
