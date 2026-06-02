from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers.admin_users import router as admin_users_router
from routers.auth import router as auth_router
from routers.bit import router as bit_router
from routers.gm import router as gm_router
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
        "http://192.168.1.95:5173",
        "http://192.168.1.24:5174",
    ],
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
app.include_router(bit_router, prefix="/api/bit", tags=["bit"])
app.include_router(la_araucana_router, prefix="/api/la-araucana", tags=["la-araucana"])
app.include_router(porsche_router, prefix="/api", tags=["porsche"])
app.include_router(sth_router, prefix="/api/sth", tags=["sth"])
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(admin_users_router, prefix="/api/admin", tags=["admin-users"])
