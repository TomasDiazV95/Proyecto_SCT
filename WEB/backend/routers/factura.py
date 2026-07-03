from fastapi import APIRouter, Depends, HTTPException, Query

from auth.dependencies import require_module
from services.factura_service import get_factura_bit_dashboard


router = APIRouter(dependencies=[Depends(require_module("factura"))])


@router.get("/bit")
def factura_bit(
    periodo: str | None = Query(default=None),
    scope: str | None = Query(default=None),
) -> dict:
    try:
        return get_factura_bit_dashboard(periodo, scope)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
