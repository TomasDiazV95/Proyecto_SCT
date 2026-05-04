from fastapi import APIRouter, HTTPException, Query

from services.la_araucana_service import get_filtros, get_resumen, get_validacion


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


@router.get("/resumen/validacion")
def validacion(periodo: str = Query(...)) -> dict:
    try:
        return get_validacion(periodo)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
