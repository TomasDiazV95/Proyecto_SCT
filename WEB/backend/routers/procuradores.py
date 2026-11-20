from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from auth.dependencies import require_module, require_roles
from excel_export import xlsx_response
from services.procuradores_excel import build_excel
from services.procuradores_service import get_detalle, get_filter_values, get_general, guardar_logros
from routers._errores import error_500


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
        raise error_500(exc) from exc


@router.get("/general")
def general(periodo: str | None = Query(default=None)) -> dict:
    try:
        return get_general({"periodo": periodo})
    except Exception as exc:
        raise error_500(exc) from exc


@router.get("/detalle")
def detalle(periodo: str | None = Query(default=None)) -> dict:
    try:
        return {"rows": get_detalle({"periodo": periodo})}
    except Exception as exc:
        raise error_500(exc) from exc


# Descarga completa del periodo (todas las carteras) con el formato de la planilla del concurso: solo super admin.
@router.get("/export")
def export(periodo: str | None = Query(default=None), _user: dict = Depends(require_roles("super_admin"))) -> StreamingResponse:
    try:
        output, filename = build_excel(periodo)
    except Exception as exc:
        raise error_500(exc) from exc
    return xlsx_response(output, filename)


# Ver la pagina no basta: los logros manuales los ingresa solo el super admin.
@router.put("/logros")
def logros(payload: GuardarLogrosRequest, user: dict = Depends(require_roles("super_admin"))) -> dict:
    try:
        guardar_logros(payload.periodo, [v.model_dump() for v in payload.valores], int(user["id"]))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise error_500(exc) from exc
    return {"ok": True}
