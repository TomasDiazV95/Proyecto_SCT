import re
import unicodedata

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from auth.dependencies import require_module
from excel_export import workbook_response
from services.rrhh_service import (
    HEADERS,
    RESUMEN_HEADERS,
    get_consolidado,
    get_negocios,
    get_periodos,
    get_planilla,
)


router = APIRouter(dependencies=[Depends(require_module("rrhh"))])

# Mismos anchos y formatos que la planilla de RRHH.
RESULTADOS_WIDTHS = [14, 22, 47, 41, 32, 13, 14, 12, 19, 18, 28, 19]
RESULTADOS_FORMATS = {
    "MES": "mmm-yy",
    "CUMPLIMIENTO TOTAL INDIVIDUAL": "0%",
    "APORTE INDIVIDUAL": "0.00%",
    "CUMPLIMIENTOS GRUPALES": "0.00%",
    "INSERTAR Q VARIABLES": "#,##0",
}
RESUMEN_WIDTHS = [22, 52, 22, 18, 24, 40]
RESUMEN_FORMATS = {"CUMPLIMIENTO PROMEDIO": "0%"}


def _resultados_sheet(rows: list[dict]) -> dict:
    return {
        "title": "RESULTADOS",
        "headers": HEADERS,
        "rows": rows,
        "widths": RESULTADOS_WIDTHS,
        "number_formats": RESULTADOS_FORMATS,
    }


def _file_part(text: str) -> str:
    ascii_text = unicodedata.normalize("NFD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "_", ascii_text).strip("_")


@router.get("/periodos")
def periodos() -> dict:
    return {"periodos": get_periodos()}


@router.get("/negocios")
def negocios(periodo: str | None = Query(default=None)) -> dict:
    try:
        return {"negocios": get_negocios(periodo)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/planilla")
def planilla(
    periodo: str | None = Query(default=None),
    negocio: str = Query(...),
) -> dict:
    try:
        return get_planilla(periodo, negocio)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/export")
def export(
    periodo: str | None = Query(default=None),
    negocio: str | None = Query(default=None),
) -> StreamingResponse:
    """Con negocio: planilla de ese negocio. Sin negocio: consolidado de todas las campañas para Finanzas."""
    try:
        if negocio:
            data = get_planilla(periodo, negocio)
            filename = f"Cumplimiento_{_file_part(data['campana'])}.xlsx"
            return workbook_response([_resultados_sheet(data["rows"])], filename)

        data = get_consolidado(periodo)
        sheets = [
            _resultados_sheet(data["rows"]),
            {
                "title": "RESUMEN",
                "headers": RESUMEN_HEADERS,
                "rows": data["resumen"],
                "widths": RESUMEN_WIDTHS,
                "number_formats": RESUMEN_FORMATS,
            },
        ]
        return workbook_response(sheets, f"Cumplimientos_Campanas_{data['periodo']}.xlsx")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
