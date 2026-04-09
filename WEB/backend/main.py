from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from schemas import ApiEnvelope, FiltersResponse
from service import get_cycle_view, get_filter_values, get_general_view


app = FastAPI(title="Productividad Ejecutivos API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/filtros", response_model=FiltersResponse)
def filtros() -> FiltersResponse:
    try:
        return FiltersResponse(**get_filter_values())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/productividad/general", response_model=ApiEnvelope)
def productividad_general(
    periodo: str | None = Query(default=None),
    zona: str | None = Query(default=None),
    tramo: str | None = Query(default=None),
    apertura: str | None = Query(default=None),
    ejecutivo: str | None = Query(default=None),
) -> ApiEnvelope:
    try:
        rows = get_general_view(
            {
                "periodo": periodo,
                "zona": zona,
                "tramo": tramo,
                "apertura": apertura,
                "ejecutivo": ejecutivo,
            }
        )
        return ApiEnvelope(data=rows)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/productividad/ciclo", response_model=ApiEnvelope)
def productividad_ciclo(
    ciclo: str | None = Query(default=None),
    periodo: str | None = Query(default=None),
    zona: str | None = Query(default=None),
    tramo: str | None = Query(default=None),
    apertura: str | None = Query(default=None),
    ejecutivo: str | None = Query(default=None),
) -> ApiEnvelope:
    try:
        rows = get_cycle_view(
            {
                "ciclo": ciclo,
                "periodo": periodo,
                "zona": zona,
                "tramo": tramo,
                "apertura": apertura,
                "ejecutivo": ejecutivo,
            }
        )
        return ApiEnvelope(data=rows)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
