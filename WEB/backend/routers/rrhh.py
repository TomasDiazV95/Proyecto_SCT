import re
import unicodedata

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from auth.dependencies import current_user
from excel_export import workbook_response
from services.rrhh_service import (
    HEADERS,
    NEGOCIOS,
    NEGOCIOS_HEADERS,
    RESUMEN_HEADERS,
    get_consolidado,
    get_negocios,
    get_periodos,
    get_planilla,
)


def negocios_permitidos(user: dict = Depends(current_user)) -> set[str]:
    """RRHH, administradores y acceso global ven todos los negocios; el resto (supervisores),
    solo los negocios cuyo panel de productividad tienen asignado."""
    if user["role"] in {"super_admin", "admin"} or set(user.get("modules", [])) & {"global", "rrhh"}:
        return set(NEGOCIOS)
    permitidos = set(user.get("access", [])) & set(NEGOCIOS)
    if not permitidos:
        raise HTTPException(status_code=403, detail="Sin permiso para módulo rrhh")
    return permitidos


router = APIRouter(dependencies=[Depends(negocios_permitidos)])

# Mismos anchos y formatos que la planilla de RRHH.
RESULTADOS_WIDTHS = [14, 22, 47, 41, 32, 13, 14, 12, 19, 18, 28, 19]
RESULTADOS_FORMATS = {
    "MES": "mmm-yy",
    "CUMPLIMIENTO TOTAL INDIVIDUAL": "0%",
    "APORTE INDIVIDUAL": "0.00%",
    "CUMPLIMIENTOS GRUPALES": "0.00%",
    "INSERTAR Q VARIABLES": "#,##0",
}
NEGOCIOS_WIDTHS = [14, 22, 40, 30, 28, 14, 30, 16, 16, 16, 12]
NEGOCIOS_FORMATS = {"MES": "mmm-yy", "MONTO DEUDA": "#,##0", "ABONO INICIAL": "#,##0", "FECHA": "dd-mm-yyyy"}
RESUMEN_WIDTHS = [22, 52, 22, 18, 24, 40]
RESUMEN_FORMATS = {"CUMPLIMIENTO PROMEDIO": "0%"}
# Columnas que el panel muestra o calcula pero que no van en el Excel de descarga.
EXCEL_OMITIR = {
    "RESULTADOS": {"ANEXOS / RESPALDO", "ESTADO ANEXO / RESPALDO"},
    "NEGOCIOS": {"FECHA"},
    "RESUMEN": {"CORTE", "CUMPLIMIENTO PROMEDIO", "ESTADO"},
}


def _sheet(title: str, headers: list[str], rows: list[dict], widths: list[int], formats: dict) -> dict:
    omitir = EXCEL_OMITIR.get(title, set())
    columnas = [(header, width) for header, width in zip(headers, widths) if header not in omitir]
    return {
        "title": title,
        "headers": [header for header, _ in columnas],
        "rows": rows,
        "widths": [width for _, width in columnas],
        "number_formats": formats,
    }


def _resultados_sheet(rows: list[dict]) -> dict:
    return _sheet("RESULTADOS", HEADERS, rows, RESULTADOS_WIDTHS, RESULTADOS_FORMATS)


def _negocios_sheet(rows: list[dict]) -> dict:
    return _sheet("NEGOCIOS", NEGOCIOS_HEADERS, rows, NEGOCIOS_WIDTHS, NEGOCIOS_FORMATS)


def _file_part(text: str) -> str:
    ascii_text = unicodedata.normalize("NFD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "_", ascii_text).strip("_")


def _validar_negocio(negocio: str, permitidos: set[str]) -> None:
    if negocio in NEGOCIOS and negocio not in permitidos:
        raise HTTPException(status_code=403, detail=f"Sin permiso para el negocio {negocio}")


@router.get("/periodos")
def periodos() -> dict:
    return {"periodos": get_periodos()}


@router.get("/negocios")
def negocios(
    periodo: str | None = Query(default=None),
    permitidos: set[str] = Depends(negocios_permitidos),
) -> dict:
    try:
        return {"negocios": get_negocios(periodo, permitidos)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/planilla")
def planilla(
    periodo: str | None = Query(default=None),
    negocio: str = Query(...),
    permitidos: set[str] = Depends(negocios_permitidos),
) -> dict:
    _validar_negocio(negocio, permitidos)
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
    permitidos: set[str] = Depends(negocios_permitidos),
) -> StreamingResponse:
    """Con negocio: planilla de ese negocio. Sin negocio: consolidado de las campañas que el usuario puede ver."""
    if negocio:
        _validar_negocio(negocio, permitidos)
    try:
        if negocio:
            data = get_planilla(periodo, negocio)
            filename = f"Cumplimiento_{_file_part(data['campana'])}.xlsx"
            sheets = [_resultados_sheet(data["rows"])]
            # Solo los negocios que cursan operaciones (reprogramaciones, convenios, etc.) llevan el detalle.
            if data["negocios"]:
                sheets.append(_negocios_sheet(data["negocios"]))
            return workbook_response(sheets, filename)

        data = get_consolidado(periodo, permitidos)
        sheets = [
            _resultados_sheet(data["rows"]),
            _negocios_sheet(data["negocios"]),
            _sheet("RESUMEN", RESUMEN_HEADERS, data["resumen"], RESUMEN_WIDTHS, RESUMEN_FORMATS),
        ]
        return workbook_response(sheets, f"Cumplimientos_Campanas_{data['periodo']}.xlsx")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
