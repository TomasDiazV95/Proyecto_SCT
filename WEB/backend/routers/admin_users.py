from fastapi import APIRouter, Depends, HTTPException

from auth.dependencies import current_user
from auth.security import hash_password
from repositories.users_repo import (
    create_user,
    get_modules_for_user,
    get_user_by_id,
    insert_audit,
    list_modules,
    list_users,
    set_user_active,
    set_user_modules,
)
from schemas import CreateUserRequest, UpdateUserModulesRequest, UpdateUserStatusRequest
from services.mail_service import send_welcome_email


router = APIRouter()


def _ensure_admin(user: dict) -> None:
    if user["role"] not in {"super_admin", "admin"} and "admin" not in user.get("modules", []):
        raise HTTPException(status_code=403, detail="Sin permiso para Panel Admin")


@router.get("/modules")
def modules_catalog(user: dict = Depends(current_user)) -> dict:
    _ensure_admin(user)
    return {"data": list_modules()}


@router.get("/users")
def users_list(user: dict = Depends(current_user)) -> dict:
    _ensure_admin(user)
    rows = list_users()
    data = []
    for row in rows:
        modules = get_modules_for_user(int(row["id"]))
        row["modules"] = [m["code"] for m in modules]
        data.append(row)
    return {"data": data}


@router.post("/users")
def users_create(payload: CreateUserRequest, user: dict = Depends(current_user)) -> dict:
    _ensure_admin(user)
    role = payload.role.strip().lower()
    if role == "admin" and user["role"] != "super_admin":
        raise HTTPException(status_code=403, detail="Solo super_admin puede crear admin")
    if role == "super_admin":
        raise HTTPException(status_code=403, detail="No se permite crear super_admin por API")

    new_user_id = create_user(
        email=payload.email.strip().lower(),
        full_name=payload.full_name.strip(),
        password_hash=hash_password("Ph.2026"),
        role_code=role,
        created_by_user_id=int(user["id"]),
    )
    set_user_modules(new_user_id, payload.module_codes, int(user["id"]))
    insert_audit(int(user["id"]), "USER_CREATE", "user", new_user_id, f"role={role}")

    email_sent = True
    email_error = ""
    try:
        send_welcome_email(payload.email.strip().lower(), payload.full_name.strip(), "Ph.2026")
    except Exception as exc:
        email_sent = False
        email_error = str(exc)
        insert_audit(
            int(user["id"]),
            "USER_WELCOME_MAIL_FAIL",
            "user",
            new_user_id,
            email_error,
        )

    response = {"ok": True, "user_id": new_user_id, "email_sent": email_sent}
    if not email_sent:
        response["email_error"] = email_error
    return response


@router.put("/users/{user_id}/modules")
def users_update_modules(user_id: int, payload: UpdateUserModulesRequest, user: dict = Depends(current_user)) -> dict:
    _ensure_admin(user)
    target = get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if str(target["role_code"]) == "admin" and user["role"] != "super_admin":
        raise HTTPException(status_code=403, detail="Solo super_admin puede modificar admin")
    set_user_modules(user_id, payload.module_codes, int(user["id"]))
    insert_audit(int(user["id"]), "USER_MODULES_UPDATE", "user", user_id, ",".join(payload.module_codes))
    return {"ok": True}


@router.put("/users/{user_id}/status")
def users_update_status(user_id: int, payload: UpdateUserStatusRequest, user: dict = Depends(current_user)) -> dict:
    _ensure_admin(user)
    target = get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if str(target["role_code"]) == "admin" and user["role"] != "super_admin":
        raise HTTPException(status_code=403, detail="Solo super_admin puede modificar admin")
    set_user_active(user_id, payload.is_active)
    insert_audit(int(user["id"]), "USER_STATUS_UPDATE", "user", user_id, f"is_active={payload.is_active}")
    return {"ok": True}


@router.delete("/users/{user_id}")
def users_delete(user_id: int, user: dict = Depends(current_user)) -> dict:
    if user["role"] != "super_admin":
        raise HTTPException(status_code=403, detail="Solo super_admin")
    target = get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if str(target["role_code"]) != "admin":
        raise HTTPException(status_code=400, detail="Solo se permite eliminar usuarios admin por esta ruta")
    set_user_active(user_id, False)
    insert_audit(int(user["id"]), "ADMIN_DISABLE", "user", user_id, None)
    return {"ok": True}
