from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from auth.dependencies import require_module, require_roles
from services.procuradores_service import get_detalle, get_filter_values, get_general, guardar_logros


router = APIRouter(dependencies=[Depends(require_module("procuradores"))])


class LogroManual(BaseModel):
    cartera: str
    ejecutivo: str
    variable: str
    valor: float | None = None


class GuardarLogrosRequest(BaseModel):
    periodo: str
    valores: list[LogroManual]


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "modulo": "procuradores"}


@router.get("/filtros")
def filtros(periodo: str | None = Query(default=None)) -> dict:
    try:
        return get_filter_values(periodo)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/general")
def general(periodo: str | None = Query(default=None)) -> dict:
    try:
        return get_general({"periodo": periodo})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/detalle")
def detalle(periodo: str | None = Query(default=None)) -> dict:
    try:
        return {"rows": get_detalle({"periodo": periodo})}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# Ver la pagina no basta: los logros manuales los ingresa solo el super admin.
@router.put("/logros")
def logros(payload: GuardarLogrosRequest, user: dict = Depends(require_roles("super_admin"))) -> dict:
    try:
        guardar_logros(payload.periodo, [v.model_dump() for v in payload.valores], int(user["id"]))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"ok": True}
