from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers.gm import router as gm_router
from routers.sc_tardia import router as sc_tardia_router
from routers.sc_temprana import router as sc_temprana_router


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


app.include_router(sc_tardia_router, prefix="/api/sc-tardia", tags=["sc-tardia"])
app.include_router(sc_temprana_router, prefix="/api/sc-temprana", tags=["sc-temprana"])
app.include_router(gm_router, prefix="/api/gm", tags=["gm"])
