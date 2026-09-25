from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from auth.dependencies import require_module
from excel_export import excel_response as _excel_response
from pydantic import BaseModel

from services.itau_vencida_medibles_service import (
    FiltroDuplicado,
    FiltroInvalido,
    add_medibles,
    delete_medible,
    get_medibles,
)
from services.administrativas_itau_service import (
    get_asignacion_export_rows,
    get_cuotas_pagadas_export_rows,
    get_cuotas_export_rows,
    get_periodos,
)


router = APIRouter(dependencies=[Depends(require_module("administrativas"))])


@router.get("/itau/periodos")
def itau_periodos() -> dict:
    try:
        return get_periodos()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/itau/cuotas/export")
def itau_cuotas_export(periodo: str = Query(...)) -> StreamingResponse:
    try:
        period_month, headers, rows = get_cuotas_export_rows(periodo)
        return _excel_response(headers, rows, "Cuotas", f"itau_cuotas_vencida_{period_month}.xlsx")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/itau/asignacion/export")
def itau_asignacion_export(periodo: str = Query(...)) -> StreamingResponse:
    try:
        period_month, headers, rows = get_asignacion_export_rows(periodo)
        return _excel_response(headers, rows, "Asignacion", f"itau_asignacion_vencida_{period_month}.xlsx")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/itau/cuotas-pagadas/export")
def itau_cuotas_pagadas_export(periodo: str = Query(...)) -> StreamingResponse:
    try:
        period_month, headers, rows = get_cuotas_pagadas_export_rows(periodo)
        return _excel_response(headers, rows, "Cuotas pagadas", f"itau_cuotas_pagadas_{period_month}.xlsx")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


class MedibleRequest(BaseModel):
    periodo: str
    columna: str
    valores: list[str]


def _medibles_call(fn, *args) -> dict:
    try:
        return fn(*args)
    except FiltroInvalido as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FiltroDuplicado as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/itau/medibles")
def itau_medibles(periodo: str = Query(...)) -> dict:
    return _medibles_call(get_medibles, periodo)


@router.post("/itau/medibles")
def itau_medibles_add(payload: MedibleRequest) -> dict:
    return _medibles_call(add_medibles, payload.periodo, payload.columna, payload.valores)


@router.delete("/itau/medibles")
def itau_medibles_delete(
    periodo: str = Query(...),
    columna: str = Query(...),
    valor: str = Query(...),
) -> dict:
    return _medibles_call(delete_medible, periodo, columna, valor)
