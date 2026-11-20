from fastapi import APIRouter, Depends, HTTPException, Query

from auth.dependencies import require_module
from services.simulador_veritus_service import RutInvalido, get_deudor
from routers._errores import error_500


router = APIRouter(dependencies=[Depends(require_module("simulador-veritus"))])


@router.get("/deudor")
def deudor(rut: str = Query(..., min_length=1, max_length=20)) -> dict:
    try:
        data = get_deudor(rut)
    except RutInvalido as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise error_500(exc) from exc
    if data is None:
        raise HTTPException(status_code=404, detail="El RUT no está en la asignación Veritus del mes.")
    return {"data": data}
