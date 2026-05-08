from io import BytesIO

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from openpyxl import Workbook

from schemas import ApiEnvelope
from services.gm_service import (
    get_bucket_view,
    get_cycle_view,
    get_filter_values,
    get_general_view,
    get_monthly_export_rows,
)


router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "modulo": "gm"}


@router.get("/filtros")
def filtros() -> dict:
    try:
        return get_filter_values()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/productividad/ciclo", response_model=ApiEnvelope)
def productividad_ciclo(
    periodo: str | None = Query(default=None),
    ejecutivo: str | None = Query(default=None),
) -> ApiEnvelope:
    try:
        return ApiEnvelope(
            data=get_cycle_view(
                {
                    "periodo": periodo,
                    "ejecutivo": ejecutivo,
                }
            )
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/productividad/general", response_model=ApiEnvelope)
def productividad_general(
    periodo: str | None = Query(default=None),
    ejecutivo: str | None = Query(default=None),
) -> ApiEnvelope:
    try:
        return ApiEnvelope(
            data=get_general_view(
                {
                    "periodo": periodo,
                    "ejecutivo": ejecutivo,
                }
            )
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/productividad/bucket", response_model=ApiEnvelope)
def productividad_bucket(
    periodo: str | None = Query(default=None),
) -> ApiEnvelope:
    try:
        return ApiEnvelope(data=get_bucket_view({"periodo": periodo}))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/export")
def export_mensual(periodo: str | None = Query(default=None)) -> StreamingResponse:
    try:
        periodo_base, rows = get_monthly_export_rows(periodo)

        wb = Workbook()
        ws = wb.active
        ws.title = "GM Mes"

        headers = [
            "op",
            "rut",
            "nombre",
            "bucket",
            "dias_de_mora",
            "deuda",
            "ejecutivo",
            "contenido",
            "normalizado",
            "UsuarioGestion",
            "ContactoGestion",
            "RespuestaGestion",
            "GestionFecha",
            "GestionHora",
            "telefono_gestion",
        ]
        ws.append(headers)

        for row in rows:
            ws.append(
                [
                    row.get("op"),
                    row.get("rut"),
                    row.get("nombre"),
                    row.get("bucket"),
                    row.get("dias_de_mora"),
                    row.get("deuda"),
                    row.get("ejecutivo"),
                    row.get("contenido"),
                    row.get("normalizado"),
                    row.get("UsuarioGestion"),
                    row.get("ContactoGestion"),
                    row.get("RespuestaGestion"),
                    row.get("GestionFecha"),
                    row.get("GestionHora"),
                    row.get("telefono_gestion"),
                ]
            )

        output = BytesIO()
        wb.save(output)
        output.seek(0)

        filename = f"gm_detalle_{periodo_base[:7]}.xlsx"
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
