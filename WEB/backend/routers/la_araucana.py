from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from io import BytesIO

from auth.dependencies import require_module, require_roles
from services.la_araucana_auditoria import build_auditoria_workbook
from services.la_araucana_service import get_detalle, get_filtros, get_negocios, get_resumen, get_validacion


router = APIRouter(dependencies=[Depends(require_module("la-araucana"))])


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "modulo": "la-araucana"}


@router.get("/filtros")
def filtros(periodo: str | None = Query(default=None)) -> dict:
    try:
        return get_filtros(periodo)
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
        raise HTTPException(status_code=400, detail="Para este módulo cartera_crm debe ser 531")
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
        raise HTTPException(status_code=400, detail="Para este módulo cartera_crm debe ser 531")
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


@router.get("/negocios")
def negocios(
    periodo: str | None = Query(default=None),
    ejecutivo: str | None = Query(default=None),
) -> dict:
    try:
        return {"periodo": periodo, "cartera_crm": 531, **get_negocios({"periodo": periodo, "ejecutivo": ejecutivo})}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/detalle")
def detalle(
    periodo: str | None = Query(default=None),
    buscar: str | None = Query(default=None),
    tipo_cartera: str | None = Query(default=None),
    ejecutivo: str | None = Query(default=None),
    usuario_gestion: str | None = Query(default=None),
    con_pago: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
) -> dict:
    try:
        return get_detalle(
            {
                "periodo": periodo,
                "buscar": buscar,
                "tipo_cartera": tipo_cartera,
                "ejecutivo": ejecutivo,
                "usuario_gestion": usuario_gestion,
                "con_pago": con_pago,
                "page": page,
                "page_size": page_size,
            }
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/export")
def export(
    periodo: str = Query(...),
    _user: dict = Depends(require_roles("super_admin", "admin", "coordinador")),
) -> StreamingResponse:
    try:
        period_month, wb = build_auditoria_workbook(periodo)
        output = BytesIO()
        wb.save(output)
        output.seek(0)
        filename = f"la_araucana_auditoria_{period_month}.xlsx"
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
