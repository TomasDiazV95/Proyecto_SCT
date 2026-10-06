from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from auth.dependencies import require_module
from excel_export import XLSX_MEDIA_TYPE
from services.estrategia_asignacion_service import (
    ParametroInvalido,
    get_itau_castigo_excel,
    get_itau_castigo_periodos,
)


router = APIRouter(dependencies=[Depends(require_module("estrategia-asignacion"))])


@router.get("/itau-castigo/periodos")
def itau_castigo_periodos() -> dict:
    try:
        return get_itau_castigo_periodos()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/itau-castigo/export")
def itau_castigo_export(periodo: str = Query(...), ejecutivos: int = Query(...)) -> StreamingResponse:
    try:
        output, filename = get_itau_castigo_excel(periodo, ejecutivos)
    except ParametroInvalido as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return StreamingResponse(
        output,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
