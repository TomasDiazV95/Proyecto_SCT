from fastapi import Cookie, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from auth.jwt_handler import decode_token
from auth.permissions import user_access
from repositories.session_control_repo import get_tokens_valid_after
from repositories.users_repo import get_user_by_id


bearer = HTTPBearer(auto_error=False)


def _token_is_globally_valid(payload: dict) -> bool:
    issued_at = payload.get("iat")
    if issued_at is None:
        return False
    try:
        issued_at_value = int(issued_at)
    except (TypeError, ValueError):
        return False
    valid_after = get_tokens_valid_after()
    valid_after_timestamp = int(valid_after.timestamp())
    if valid_after.microsecond:
        valid_after_timestamp += 1
    return issued_at_value >= valid_after_timestamp


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict:
    if not credentials:
        raise HTTPException(status_code=401, detail="No autenticado")
    try:
        payload = decode_token(credentials.credentials, expected_type="access")
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Token inválido") from exc

    if not _token_is_globally_valid(payload):
        raise HTTPException(status_code=401, detail="Sesión expirada")

    user = get_user_by_id(int(payload["sub"]))
    if not user or not user.get("is_active"):
        raise HTTPException(status_code=401, detail="Usuario no habilitado")

    role = str(user["role_code"])
    user["role"] = role
    # modules = lo asignado; access = lo que puede abrir (paneles completos, acceso global, rol).
    user["modules"], user["access"] = user_access(int(user["id"]), role)
    return user


def require_roles(*allowed_roles: str):
    def checker(user: dict = Depends(current_user)) -> dict:
        if user["role"] not in allowed_roles:
            raise HTTPException(status_code=403, detail="No autorizado")
        return user

    return checker


def require_module(module_code: str):
    def checker(user: dict = Depends(current_user)) -> dict:
        if module_code not in user.get("access", []):
            raise HTTPException(status_code=403, detail=f"Sin permiso para módulo {module_code}")
        return user

    return checker


def refresh_user(refresh_token: str | None = Cookie(default=None, alias="refresh_token")) -> dict:
    if not refresh_token:
        raise HTTPException(status_code=401, detail="No autenticado")
    try:
        payload = decode_token(refresh_token, expected_type="refresh")
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Refresh token inválido") from exc

    if not _token_is_globally_valid(payload):
        raise HTTPException(status_code=401, detail="Sesión expirada")

    user = get_user_by_id(int(payload["sub"]))
    if not user or not user.get("is_active"):
        raise HTTPException(status_code=401, detail="Usuario no habilitado")
    user["role"] = str(user["role_code"])
    return user
