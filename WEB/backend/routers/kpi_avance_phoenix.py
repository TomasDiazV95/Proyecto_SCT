from fastapi import APIRouter, Depends, HTTPException, Query

from auth.dependencies import current_user, require_module
from auth.negocios_kpi import exigir_negocio, filtrar_opciones, negocios_permitidos
from services.kpi_avance_phoenix_service import get_comparison_view, get_filter_values


router = APIRouter(dependencies=[Depends(require_module("kpi-diario"))])


@router.get("/filtros")
def filtros(
    negocio: str | None = Query(default=None),
    segmento: str | None = Query(default=None),
    user: dict = Depends(current_user),
) -> dict:
    if negocio:
        exigir_negocio(user, "bench", negocio)
    try:
        data = get_filter_values({"negocio": negocio, "segmento": segmento})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    # Supervisores: solo los negocios de su productividad (auth/negocios_kpi.py).
    permitidos = negocios_permitidos(user, "bench")
    data["negocios"] = filtrar_opciones(data["negocios"], permitidos)
    data["sin_negocio"] = permitidos is not None and not permitidos
    return data


@router.get("/comparacion")
def comparacion(
    periodos: list[str] | None = Query(default=None),
    negocio: str | None = Query(default=None),
    segmento: str | None = Query(default=None),
    user: dict = Depends(current_user),
) -> dict:
    exigir_negocio(user, "bench", negocio)
    try:
        return get_comparison_view({"periodos": periodos, "negocio": negocio, "segmento": segmento})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
