from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers.admin_users import router as admin_users_router
from routers.auth import router as auth_router
from routers.bit_castigo import router as bit_castigo_router
from routers.bit import router as bit_router
from routers.factura import router as factura_router
from routers.gm import router as gm_router
from routers.kpi_diario import router as kpi_diario_router
from routers.itau_castigo import router as itau_castigo_router
from routers.la_araucana import router as la_araucana_router
from routers.porsche import router as porsche_router
from routers.sc_tardia import router as sc_tardia_router
from routers.sc_temprana import router as sc_temprana_router
from routers.sth import router as sth_router


app = FastAPI(title="Productividad Ejecutivos API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_origin_regex=r"^https?://("
    r"localhost|127\.0\.0\.1|"
    r"192\.168\.\d{1,3}\.\d{1,3}|"
    r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
    r"172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3}"
    r")(:\d+)?$",
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
app.include_router(kpi_diario_router, prefix="/api/kpi-diario", tags=["kpi-diario"])
app.include_router(itau_castigo_router, prefix="/api/itau-castigo", tags=["itau-castigo"])
app.include_router(bit_castigo_router, prefix="/api/bit-castigo", tags=["bit-castigo"])
app.include_router(bit_router, prefix="/api/bit", tags=["bit"])
app.include_router(factura_router, prefix="/api/factura", tags=["factura"])
app.include_router(la_araucana_router, prefix="/api/la-araucana", tags=["la-araucana"])
app.include_router(porsche_router, prefix="/api", tags=["porsche"])
app.include_router(sth_router, prefix="/api/sth", tags=["sth"])
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(admin_users_router, prefix="/api/admin", tags=["admin-users"])
