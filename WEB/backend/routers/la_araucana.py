from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from io import BytesIO
from openpyxl import Workbook

from services.la_araucana_service import get_export_rows, get_filtros, get_resumen, get_validacion


router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "modulo": "la-araucana"}


@router.get("/filtros")
def filtros() -> dict:
    try:
        return get_filtros()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/resumen")
def resumen(
    periodo: str | None = Query(default=None),
    cartera_crm: int | None = Query(default=531),
    tipo_cartera: str | None = Query(default=None),
    ejecutivo: str | None = Query(default=None),
) -> dict:
    if cartera_crm != 531:
        raise HTTPException(status_code=400, detail="Para este modulo cartera_crm debe ser 531")
    try:
        return {
            "periodo": periodo,
            "cartera_crm": 531,
            **get_resumen(
                {
                    "periodo": periodo,
                    "tipo_cartera": tipo_cartera,
                    "ejecutivo": ejecutivo,
                }
            ),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/productividad/detalle")
def productividad_detalle(
    periodo: str | None = Query(default=None),
    cartera_crm: int | None = Query(default=531),
    tipo_cartera: str | None = Query(default=None),
    ejecutivo: str | None = Query(default=None),
) -> dict:
    if cartera_crm != 531:
        raise HTTPException(status_code=400, detail="Para este modulo cartera_crm debe ser 531")
    try:
        return {
            "periodo": periodo,
            "cartera_crm": 531,
            **get_resumen(
                {
                    "periodo": periodo,
                    "tipo_cartera": tipo_cartera,
                    "ejecutivo": ejecutivo,
                }
            ),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/export")
def export(
    periodo: str = Query(...),
    tipo_cartera: str | None = Query(default=None),
) -> StreamingResponse:
    try:
        period_month, rows = get_export_rows({"periodo": periodo, "tipo_cartera": tipo_cartera})
        wb = Workbook()
        ws = wb.active
        ws.title = "La Araucana"
        headers = [
            "folio_credito",
            "rut",
            "tramo_mora",
            "capital",
            "total_deuda",
            "recupero",
            "tipo_cartera",
            "usuariogestion",
            "contactogestion",
            "respuestagestion",
            "gestionfecha",
            "gestionhora",
            "telefono",
        ]
        ws.append(headers)
        for row in rows:
            ws.append([row.get(h) for h in headers])

        output = BytesIO()
        wb.save(output)
        output.seek(0)
        filename = f"la_araucana_detalle_{period_month}.xlsx"
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/resumen/validacion")
def validacion(periodo: str = Query(...)) -> dict:
    try:
        return get_validacion(periodo)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
