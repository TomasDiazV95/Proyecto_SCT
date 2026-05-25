import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response

from auth.dependencies import current_user, refresh_user
from auth.jwt_handler import create_access_token, create_refresh_token
from auth.security import hash_password, hash_token, new_reset_token, verify_password
from repositories.password_reset_repo import create_reset_token, get_valid_token, mark_token_used
from repositories.users_repo import (
    get_modules_for_user,
    get_user_by_email,
    insert_audit,
    update_login_failure,
    update_login_success,
    update_password,
)
from schemas import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    ResetPasswordRequest,
)
from services.mail_service import send_reset_password_email


router = APIRouter()


def _cookie_secure() -> bool:
    return os.getenv("AUTH_COOKIE_SECURE", "false").lower() == "true"


@router.post("/login")
def login(payload: LoginRequest, response: Response) -> dict:
    user = get_user_by_email(payload.email)
    if not user:
        raise HTTPException(status_code=401, detail="Credenciales invalidas")

    locked_until = user.get("locked_until")
    if locked_until:
        if isinstance(locked_until, datetime) and locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=timezone.utc)
        if isinstance(locked_until, datetime) and locked_until > datetime.now(timezone.utc):
            raise HTTPException(status_code=423, detail="Usuario temporalmente bloqueado")

    if not bool(user.get("is_active")):
        raise HTTPException(status_code=403, detail="Usuario inactivo")

    if not verify_password(payload.password, str(user["password_hash"])):
        update_login_failure(int(user["id"]), int(os.getenv("AUTH_MAX_LOGIN_ATTEMPTS", "5")), int(os.getenv("AUTH_LOCK_MINUTES", "15")))
        insert_audit(int(user["id"]), "LOGIN_FAIL", "user", int(user["id"]), "password invalida")
        raise HTTPException(status_code=401, detail="Credenciales invalidas")

    update_login_success(int(user["id"]))
    role = str(user["role_code"])
    access_token = create_access_token(int(user["id"]), role)
    refresh_token = create_refresh_token(int(user["id"]), role)
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=_cookie_secure(),
        samesite="lax",
        max_age=60 * 60 * 24 * int(os.getenv("AUTH_REFRESH_DAYS", "7")),
        path="/api/auth",
    )
    insert_audit(int(user["id"]), "LOGIN_OK", "user", int(user["id"]), None)

    modules = get_modules_for_user(int(user["id"]))
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user["id"],
            "email": user["email"],
            "full_name": user["full_name"],
            "role": role,
            "must_change_password": bool(user.get("must_change_password")),
            "modules": [m["code"] for m in modules],
        },
    }


@router.post("/refresh")
def refresh(response: Response, user: dict = Depends(refresh_user)) -> dict:
    role = str(user["role"])
    access_token = create_access_token(int(user["id"]), role)
    refresh_token = create_refresh_token(int(user["id"]), role)
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=_cookie_secure(),
        samesite="lax",
        max_age=60 * 60 * 24 * int(os.getenv("AUTH_REFRESH_DAYS", "7")),
        path="/api/auth",
    )
    modules = get_modules_for_user(int(user["id"]))
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user["id"],
            "email": user["email"],
            "full_name": user["full_name"],
            "role": role,
            "must_change_password": bool(user.get("must_change_password")),
            "modules": [m["code"] for m in modules],
        },
    }


@router.post("/logout")
def logout(response: Response, user: dict = Depends(current_user)) -> dict:
    response.delete_cookie("refresh_token", path="/api/auth")
    insert_audit(int(user["id"]), "LOGOUT", "user", int(user["id"]), None)
    return {"ok": True}


@router.get("/me")
def me(user: dict = Depends(current_user)) -> dict:
    modules = get_modules_for_user(int(user["id"]))
    return {
        "id": user["id"],
        "email": user["email"],
        "full_name": user["full_name"],
        "role": user["role"],
        "must_change_password": bool(user.get("must_change_password")),
        "modules": [m["code"] for m in modules],
    }


@router.post("/change-password")
def change_password(payload: ChangePasswordRequest, user: dict = Depends(current_user)) -> dict:
    db_user = get_user_by_email(str(user["email"]))
    if not db_user or not verify_password(payload.current_password, str(db_user["password_hash"])):
        raise HTTPException(status_code=400, detail="Contrasena actual invalida")
    update_password(int(user["id"]), hash_password(payload.new_password), must_change_password=False)
    insert_audit(int(user["id"]), "PASSWORD_CHANGE", "user", int(user["id"]), None)
    return {"ok": True}


@router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordRequest) -> dict:
    user = get_user_by_email(payload.email)
    if user and bool(user.get("is_active")):
        token = new_reset_token()
        create_reset_token(int(user["id"]), hash_token(token), int(os.getenv("AUTH_RESET_EXPIRES_MINUTES", "30")))
        send_reset_password_email(str(user["email"]), token)
        insert_audit(int(user["id"]), "PASSWORD_RESET_REQUEST", "user", int(user["id"]), None)
    return {"ok": True}


@router.post("/reset-password")
def reset_password(payload: ResetPasswordRequest) -> dict:
    token_row = get_valid_token(hash_token(payload.token))
    if not token_row:
        raise HTTPException(status_code=400, detail="Token invalido o expirado")
    user_id = int(token_row["user_id"])
    update_password(user_id, hash_password(payload.new_password), must_change_password=False)
    mark_token_used(int(token_row["id"]))
    insert_audit(user_id, "PASSWORD_RESET_DONE", "user", user_id, None)
    return {"ok": True}
