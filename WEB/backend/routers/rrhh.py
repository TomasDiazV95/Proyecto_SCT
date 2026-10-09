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
    modules = set(user.get("modules", []))
    if user["role"] in {"super_admin", "admin"} or modules & {"global", "rrhh"}:
        return set(NEGOCIOS)
    permitidos = modules & set(NEGOCIOS)
    if not permitidos:
        raise HTTPException(status_code=403, detail="Sin permiso para modulo rrhh")
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


def _resultados_sheet(rows: list[dict]) -> dict:
    return {
        "title": "RESULTADOS",
        "headers": HEADERS,
        "rows": rows,
        "widths": RESULTADOS_WIDTHS,
        "number_formats": RESULTADOS_FORMATS,
    }


def _negocios_sheet(rows: list[dict]) -> dict:
    return {
        "title": "NEGOCIOS",
        "headers": NEGOCIOS_HEADERS,
        "rows": rows,
        "widths": NEGOCIOS_WIDTHS,
        "number_formats": NEGOCIOS_FORMATS,
    }


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
