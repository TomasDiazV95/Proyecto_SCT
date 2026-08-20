from typing import Any

from pydantic import BaseModel


class FiltersResponse(BaseModel):
    periodos: list[str]
    tramos: list[str]
    aperturas: list[str]
    ejecutivos: list[str]
    zonas: list[str]
    negocios: list[str] = []
    segmentos: list[str] = []


class GeneralRow(BaseModel):
    ejecutivo: str
    zona: str | None
    deuda_total: float
    casos_asignados: int
    cumplimiento_final: float
    ciclos: dict[str, float]


class CycleRow(BaseModel):
    periodo: str | None
    zona: str | None
    tramo: str
    apertura: str
    ejecutivo: str
    deuda_asignada: float
    saldo_contenido: float
    porcentaje_contenido: float
    saldo_normalizado: float
    porcentaje_normalizado: float
    meta_contencion_pct: float
    meta_normalizacion_pct: float
    cumplimiento_final: float
    casos_asignados: int


class ApiEnvelope(BaseModel):
    data: list[Any]


class LoginRequest(BaseModel):
    email: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class VerifyResetCodeRequest(BaseModel):
    email: str
    code: str


class ResetPasswordRequest(BaseModel):
    email: str
    code: str
    new_password: str


class CreateUserRequest(BaseModel):
    email: str
    full_name: str
    role: str
    module_codes: list[str] = []


class UpdateUserModulesRequest(BaseModel):
    module_codes: list[str] = []


class UpdateUserStatusRequest(BaseModel):
    is_active: bool
