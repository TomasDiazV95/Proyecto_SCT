from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from auth.dependencies import require_module
from excel_export import XLSX_MEDIA_TYPE, excel_response as _excel_response
from pydantic import BaseModel

from services import negocios_service

from services.itau_vencida_medibles_service import (
    FiltroDuplicado,
    FiltroInvalido,
    add_medibles,
    delete_medible,
    get_medibles,
    replace_medibles,
    sugerir_medibles,
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


class FiltroMedible(BaseModel):
    columna: str
    valor: str


class ReemplazarMediblesRequest(BaseModel):
    periodo: str
    filtros: list[FiltroMedible]


class MontoAsignado(BaseModel):
    producto: str
    # Sin fase: el monto es el total del producto.
    fase: int | None = None
    monto: float


class SugerirMediblesRequest(BaseModel):
    periodo: str
    fecha_carga: str
    unidad: str = "pesos"
    montos: list[MontoAsignado]


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


@router.put("/itau/medibles")
def itau_medibles_replace(payload: ReemplazarMediblesRequest) -> dict:
    return _medibles_call(replace_medibles, payload.periodo, [f.model_dump() for f in payload.filtros])


@router.post("/itau/medibles/sugerir")
def itau_medibles_sugerir(payload: SugerirMediblesRequest) -> dict:
    return _medibles_call(
        sugerir_medibles, payload.periodo, payload.fecha_carga, [m.model_dump() for m in payload.montos], payload.unidad
    )


@router.delete("/itau/medibles")
def itau_medibles_delete(
    periodo: str = Query(...),
    columna: str = Query(...),
    valor: str = Query(...),
) -> dict:
    return _medibles_call(delete_medible, periodo, columna, valor)


def _negocios_call(fn, *args):
    try:
        return fn(*args)
    except negocios_service.ArchivoInvalido as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/negocios/cargas")
def negocios_cargas() -> list[dict]:
    return _negocios_call(negocios_service.listar_cargas)


@router.get("/negocios/plantilla")
def negocios_plantilla(negocio: str = Query(...)) -> StreamingResponse:
    nombre, contenido = _negocios_call(negocios_service.plantilla, negocio)
    return StreamingResponse(
        contenido,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


@router.post("/negocios/cargas")
def negocios_cargar(
    negocio: str = Form(...),
    archivo: UploadFile = File(...),
    user: dict = Depends(require_module("administrativas")),
) -> dict:
    # Un byte de mas basta para saber que supera el limite, sin leer el archivo completo.
    contenido = archivo.file.read(negocios_service.MAX_BYTES + 1)
    return _negocios_call(negocios_service.cargar, negocio, archivo.filename or "", contenido, user.get("email") or "")


@router.delete("/negocios/cargas/{id_carga}")
def negocios_eliminar(id_carga: int) -> dict:
    _negocios_call(negocios_service.eliminar_carga, id_carga)
    return {"ok": True}
