from fastapi import Cookie, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from auth.jwt_handler import decode_token
from repositories.session_control_repo import get_tokens_valid_after
from repositories.users_repo import get_modules_for_user, get_user_by_id


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
        raise HTTPException(status_code=401, detail="Token invalido") from exc

    if not _token_is_globally_valid(payload):
        raise HTTPException(status_code=401, detail="Sesion expirada")

    user = get_user_by_id(int(payload["sub"]))
    if not user or not user.get("is_active"):
        raise HTTPException(status_code=401, detail="Usuario no habilitado")

    role = str(user["role_code"])
    modules = get_modules_for_user(int(user["id"]))
    user["role"] = role
    user["modules"] = [m["code"] for m in modules]
    return user


def require_roles(*allowed_roles: str):
    def checker(user: dict = Depends(current_user)) -> dict:
        if user["role"] not in allowed_roles:
            raise HTTPException(status_code=403, detail="No autorizado")
        return user

    return checker


def require_module(module_code: str):
    def checker(user: dict = Depends(current_user)) -> dict:
        role = user["role"]
        modules = user.get("modules", [])
        if module_code == "admin":
            if role in {"super_admin", "admin"} or "admin" in modules:
                return user
            raise HTTPException(status_code=403, detail=f"Sin permiso para modulo {module_code}")
        if role in {"super_admin", "admin"} or "global" in modules:
            return user
        if module_code not in modules:
            raise HTTPException(status_code=403, detail=f"Sin permiso para modulo {module_code}")
        return user

    return checker


def refresh_user(refresh_token: str | None = Cookie(default=None, alias="refresh_token")) -> dict:
    if not refresh_token:
        raise HTTPException(status_code=401, detail="No autenticado")
    try:
        payload = decode_token(refresh_token, expected_type="refresh")
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Refresh token invalido") from exc

    if not _token_is_globally_valid(payload):
        raise HTTPException(status_code=401, detail="Sesion expirada")

    user = get_user_by_id(int(payload["sub"]))
    if not user or not user.get("is_active"):
        raise HTTPException(status_code=401, detail="Usuario no habilitado")
    user["role"] = str(user["role_code"])
    return user
