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


class UpdateUserRequest(BaseModel):
    full_name: str
    role: str


class UpdateUserModulesRequest(BaseModel):
    module_codes: list[str] = []


class BulkUserModulesRequest(BaseModel):
    user_ids: list[int]
    add: list[str] = []
    remove: list[str] = []


class UpdateUserStatusRequest(BaseModel):
    is_active: bool
