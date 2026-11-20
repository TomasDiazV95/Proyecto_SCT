from fastapi import APIRouter, Depends, Query

from auth.dependencies import current_user, require_module
from auth.negocios_kpi import exigir_negocio, filtrar_opciones, negocios_permitidos
from services.bench_service import get_filter_values, get_kpi_view
from routers._errores import error_500


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
    if negocio:
        exigir_negocio(user, "bench", negocio)
    try:
        data = get_filter_values({"periodo": periodo, "negocio": negocio}, user=user)
    except Exception as exc:
        raise error_500(exc) from exc
    # Supervisores: solo los negocios de su productividad (auth/negocios_kpi.py).
    permitidos = negocios_permitidos(user, "bench")
    data["negocios"] = filtrar_opciones(data["negocios"], permitidos)
    data["sin_negocio"] = permitidos is not None and not permitidos
    return data


@router.get("/kpi")
def kpi(
    periodo: str | None = Query(default=None),
    negocio: str | None = Query(default=None),
    segmento: str | None = Query(default=None),
    user: dict = Depends(current_user),
) -> dict:
    exigir_negocio(user, "bench", negocio)
    try:
        return get_kpi_view({"periodo": periodo, "negocio": negocio, "segmento": segmento}, user=user)
    except Exception as exc:
        raise error_500(exc) from exc
