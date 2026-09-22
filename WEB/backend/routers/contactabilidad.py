import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from auth.dependencies import require_module
from excel_export import excel_response
from services.contactabilidad_itau_vencida_service import (
    PeriodoSinContencion,
    get_detalle,
    get_detalle_export_rows,
    get_dashboard,
    get_evolucion,
    get_estado_contacto,
    get_filter_values,
    get_resumen,
    get_tubo,
)


router = APIRouter(dependencies=[Depends(require_module("contactabilidad"))])
logger = logging.getLogger(__name__)


def _sin_contencion(exc: PeriodoSinContencion) -> HTTPException:
    """404 con el mensaje del negocio: nunca se cae a la carga de otro período."""
    return HTTPException(status_code=404, detail=str(exc))


def _filters(
    periodo: str | None,
    segmento: list[str] | None,
    canal: list[str] | None,
    fase_cliente: list[str] | None,
    glosa_tipo_cartera: list[str] | None,
    producto: list[str] | None,
    tipo_campana: list[str] | None,
    detalle_marca: list[str] | None,
    estado_contencion: list[str] | None,
    estado_contacto: list[str] | None,
) -> dict:
    return {"periodo": periodo, "segmento": segmento, "canal": canal, "fase_cliente": fase_cliente, "glosa_tipo_cartera": glosa_tipo_cartera, "producto": producto, "tipo_campana": tipo_campana, "detalle_marca": detalle_marca, "estado_contencion": estado_contencion, "estado_contacto": estado_contacto}


@router.get("/itau-vencida/filtros")
def filtros(periodo: str | None = Query(default=None)) -> dict:
    try:
        return get_filter_values({"periodo": periodo})
    except PeriodoSinContencion as exc:
        raise _sin_contencion(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="No fue posible cargar los filtros") from exc


@router.get("/itau-vencida/resumen")
def resumen(
    periodo: str | None = None, segmento: list[str] | None = Query(default=None), canal: list[str] | None = Query(default=None), fase_cliente: list[str] | None = Query(default=None), glosa_tipo_cartera: list[str] | None = Query(default=None), producto: list[str] | None = Query(default=None), tipo_campana: list[str] | None = Query(default=None), detalle_marca: list[str] | None = Query(default=None), estado_contencion: list[str] | None = Query(default=None), estado_contacto: list[str] | None = Query(default=None),
) -> dict:
    try:
        return get_resumen(_filters(periodo, segmento, canal, fase_cliente, glosa_tipo_cartera, producto, tipo_campana, detalle_marca, estado_contencion, estado_contacto))
    except PeriodoSinContencion as exc:
        raise _sin_contencion(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="No fue posible cargar el resumen") from exc


@router.get("/itau-vencida/dashboard")
def dashboard(
    periodo: str | None = None,
    segmento: list[str] | None = Query(default=None),
    canal: list[str] | None = Query(default=None),
    fase_cliente: list[str] | None = Query(default=None),
    glosa_tipo_cartera: list[str] | None = Query(default=None),
    producto: list[str] | None = Query(default=None),
    tipo_campana: list[str] | None = Query(default=None),
    detalle_marca: list[str] | None = Query(default=None),
    estado_contencion: list[str] | None = Query(default=None),
    estado_contacto: list[str] | None = Query(default=None),
    search: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
    sort_by: str = "rut",
    sort_direction: str = "asc",
) -> dict:
    try:
        filters = _filters(
            periodo,
            segmento,
            canal,
            fase_cliente,
            glosa_tipo_cartera,
            producto,
            tipo_campana,
            detalle_marca,
            estado_contencion,
            estado_contacto,
        )
        filters.update({
            "search": search,
            "page": page,
            "page_size": page_size,
            "sort_by": sort_by,
            "sort_direction": sort_direction,
        })
        return get_dashboard(filters)
    except PeriodoSinContencion as exc:
        raise _sin_contencion(exc) from exc
    except Exception as exc:
        logger.exception("Error en dashboard de Contactabilidad Itaú Vencida")
        raise HTTPException(status_code=500, detail="No fue posible cargar el dashboard de contactabilidad") from exc


def _data_endpoint(fn):
    def endpoint(
        periodo: str | None = None, segmento: list[str] | None = Query(default=None), canal: list[str] | None = Query(default=None), fase_cliente: list[str] | None = Query(default=None), glosa_tipo_cartera: list[str] | None = Query(default=None), producto: list[str] | None = Query(default=None), tipo_campana: list[str] | None = Query(default=None), detalle_marca: list[str] | None = Query(default=None), estado_contencion: list[str] | None = Query(default=None), estado_contacto: list[str] | None = Query(default=None),
    ) -> dict:
        try:
            return fn(_filters(periodo, segmento, canal, fase_cliente, glosa_tipo_cartera, producto, tipo_campana, detalle_marca, estado_contencion, estado_contacto))
        except PeriodoSinContencion as exc:
            raise _sin_contencion(exc) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail="No fue posible cargar la información") from exc
    return endpoint


router.add_api_route("/itau-vencida/estado-contacto", _data_endpoint(get_estado_contacto), methods=["GET"])
router.add_api_route("/itau-vencida/tubo", _data_endpoint(get_tubo), methods=["GET"])
router.add_api_route("/itau-vencida/evolucion", _data_endpoint(get_evolucion), methods=["GET"])


@router.get("/itau-vencida/detalle")
def detalle(
    periodo: str | None = None, segmento: list[str] | None = Query(default=None), canal: list[str] | None = Query(default=None), fase_cliente: list[str] | None = Query(default=None), glosa_tipo_cartera: list[str] | None = Query(default=None), producto: list[str] | None = Query(default=None), tipo_campana: list[str] | None = Query(default=None), detalle_marca: list[str] | None = Query(default=None), estado_contencion: list[str] | None = Query(default=None), estado_contacto: list[str] | None = Query(default=None), search: str | None = None, page: int = Query(default=1, ge=1), page_size: int = Query(default=100, ge=1, le=500), sort_by: str = "rut", sort_direction: str = "asc",
) -> dict:
    try:
        filters = _filters(periodo, segmento, canal, fase_cliente, glosa_tipo_cartera, producto, tipo_campana, detalle_marca, estado_contencion, estado_contacto)
        filters.update({"search": search, "page": page, "page_size": page_size, "sort_by": sort_by, "sort_direction": sort_direction})
        return get_detalle(filters)
    except PeriodoSinContencion as exc:
        raise _sin_contencion(exc) from exc
    except Exception as exc:
        logger.exception("Error en detalle de Contactabilidad Itaú Vencida")
        raise HTTPException(status_code=500, detail="No fue posible cargar el detalle") from exc


@router.get("/itau-vencida/detalle/export")
def detalle_export(
    periodo: str | None = None, segmento: list[str] | None = Query(default=None), canal: list[str] | None = Query(default=None), fase_cliente: list[str] | None = Query(default=None), glosa_tipo_cartera: list[str] | None = Query(default=None), producto: list[str] | None = Query(default=None), tipo_campana: list[str] | None = Query(default=None), detalle_marca: list[str] | None = Query(default=None), estado_contencion: list[str] | None = Query(default=None), estado_contacto: list[str] | None = Query(default=None), search: str | None = None,
) -> StreamingResponse:
    try:
        filters = _filters(periodo, segmento, canal, fase_cliente, glosa_tipo_cartera, producto, tipo_campana, detalle_marca, estado_contencion, estado_contacto)
        filters.update({"search": search})
        period, process_date, headers, rows = get_detalle_export_rows(filters)
        return excel_response(
            headers,
            rows,
            "Detalle",
            f"contactabilidad_itau_vencida_{period}_contencion_{process_date}.xlsx",
        )
    except PeriodoSinContencion as exc:
        raise _sin_contencion(exc) from exc
    except Exception as exc:
        logger.exception("Error al exportar el detalle de Contactabilidad Itaú Vencida")
        raise HTTPException(status_code=500, detail="No fue posible exportar el detalle") from exc
