from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from auth.dependencies import current_user, require_module
from auth.permissions import effective_modules, module_tree
from auth.security import hash_password
from repositories.users_repo import (
    change_user_modules,
    create_user,
    get_user_by_id,
    insert_audit,
    list_modules,
    list_user_modules_map,
    list_users,
    set_user_active,
    set_user_modules,
    unlock_user,
    update_password,
    update_user_profile,
)
from repositories.session_control_repo import invalidate_all_sessions
from schemas import (
    BulkUserModulesRequest,
    CreateUserRequest,
    UpdateUserModulesRequest,
    UpdateUserRequest,
    UpdateUserStatusRequest,
)
from services.mail_service import send_temp_password_email, send_welcome_email


router = APIRouter(dependencies=[Depends(require_module("admin"))])

TEMP_PASSWORD = "Ph.2026"
# Roles que solo el super admin puede crear, asignar o modificar.
ROLES_PROTEGIDOS = {"admin", "super_admin"}
ROLES_ASIGNABLES = {"admin", "coordinador", "supervisor", "ejecutivo"}


def _ensure_can_modify(target: dict | None, user: dict) -> None:
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if str(target["role_code"]) in ROLES_PROTEGIDOS and user["role"] != "super_admin":
        raise HTTPException(status_code=403, detail="Solo super_admin puede modificar administradores")


def _es_uno_mismo(user_id: int, user: dict) -> bool:
    return int(user_id) == int(user["id"])


def _utc(valor):
    if isinstance(valor, datetime) and valor.tzinfo is None:
        return valor.replace(tzinfo=timezone.utc)
    return valor


def _iso(valor) -> str | None:
    valor = _utc(valor)
    return valor.isoformat() if isinstance(valor, datetime) else None


@router.get("/modules")
def modules_catalog() -> dict:
    return {"data": list_modules()}


@router.get("/users")
def users_list() -> dict:
    """Usuarios con sus modulos asignados (modules) y los que realmente pueden abrir (access)."""
    asignados = list_user_modules_map()
    arbol = module_tree()
    ahora = datetime.now(timezone.utc)
    data = []
    for row in list_users():
        modules = asignados.get(int(row["id"]), [])
        locked_until = _utc(row.pop("locked_until", None))
        data.append({
            **row,
            "modules": modules,
            "access": sorted(effective_modules(str(row["role_code"]), modules, arbol)),
            "locked": isinstance(locked_until, datetime) and locked_until > ahora,
            "last_login_at": _iso(row.get("last_login_at")),
            "created_at": _iso(row.get("created_at")),
        })
    return {"data": data}


@router.put("/users/{user_id}")
def users_update(user_id: int, payload: UpdateUserRequest, user: dict = Depends(current_user)) -> dict:
    """Nombre y rol del usuario."""
    target = get_user_by_id(user_id)
    _ensure_can_modify(target, user)
    full_name = payload.full_name.strip()
    role = payload.role.strip().lower()
    if not full_name:
        raise HTTPException(status_code=400, detail="Ingresa el nombre del usuario")
    if role not in ROLES_ASIGNABLES:
        raise HTTPException(status_code=400, detail="Rol no permitido")
    if role == "admin" and user["role"] != "super_admin":
        raise HTTPException(status_code=403, detail="Solo super_admin puede asignar el rol admin")
    if role != str(target["role_code"]) and _es_uno_mismo(user_id, user):
        raise HTTPException(status_code=400, detail="No puedes cambiar tu propio rol")
    try:
        update_user_profile(user_id, full_name, role)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    insert_audit(int(user["id"]), "USER_PROFILE_UPDATE", "user", user_id, f"role={role}")
    return {"ok": True}


@router.post("/users/{user_id}/reset-password")
def users_reset_password(user_id: int, user: dict = Depends(current_user)) -> dict:
    """Deja la contrasena temporal (con cambio obligatorio al entrar) y la envia por correo."""
    target = get_user_by_id(user_id)
    _ensure_can_modify(target, user)
    if _es_uno_mismo(user_id, user):
        raise HTTPException(status_code=400, detail="Para tu propia contraseña usa Cambiar contraseña")
    update_password(user_id, hash_password(TEMP_PASSWORD), True)
    insert_audit(int(user["id"]), "USER_PASSWORD_RESET", "user", user_id, None)
    try:
        send_temp_password_email(str(target["email"]), str(target.get("full_name") or ""), TEMP_PASSWORD)
    except Exception as exc:
        insert_audit(int(user["id"]), "USER_RESET_MAIL_FAIL", "user", user_id, str(exc))
        return {"ok": True, "email_sent": False, "email_error": str(exc)}
    return {"ok": True, "email_sent": True}


@router.post("/users/{user_id}/unlock")
def users_unlock(user_id: int, user: dict = Depends(current_user)) -> dict:
    _ensure_can_modify(get_user_by_id(user_id), user)
    unlock_user(user_id)
    insert_audit(int(user["id"]), "USER_UNLOCK", "user", user_id, None)
    return {"ok": True}


@router.post("/users")
def users_create(payload: CreateUserRequest, user: dict = Depends(current_user)) -> dict:
    role = payload.role.strip().lower()
    if role == "admin" and user["role"] != "super_admin":
        raise HTTPException(status_code=403, detail="Solo super_admin puede crear admin")
    if role == "super_admin":
        raise HTTPException(status_code=403, detail="No se permite crear super_admin por API")

    new_user_id = create_user(
        email=payload.email.strip().lower(),
        full_name=payload.full_name.strip(),
        password_hash=hash_password(TEMP_PASSWORD),
        role_code=role,
        created_by_user_id=int(user["id"]),
    )
    try:
        set_user_modules(new_user_id, payload.module_codes, int(user["id"]))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    insert_audit(int(user["id"]), "USER_CREATE", "user", new_user_id, f"role={role}")

    email_sent = True
    email_error = ""
    try:
        send_welcome_email(payload.email.strip().lower(), payload.full_name.strip(), TEMP_PASSWORD)
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


@router.post("/users/modules/bulk")
def users_bulk_modules(payload: BulkUserModulesRequest, user: dict = Depends(current_user)) -> dict:
    """Agrega y quita modulos a varios usuarios, sin tocar el resto de sus permisos."""
    user_ids = list(dict.fromkeys(payload.user_ids))
    if not user_ids:
        raise HTTPException(status_code=400, detail="Selecciona al menos un usuario")
    if not payload.add and not payload.remove:
        raise HTTPException(status_code=400, detail="Indica al menos un módulo para agregar o quitar")
    for user_id in user_ids:
        _ensure_can_modify(get_user_by_id(user_id), user)

    try:
        result = change_user_modules(user_ids, payload.add, payload.remove, int(user["id"]))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    for user_id, codes in result.items():
        insert_audit(int(user["id"]), "USER_MODULES_UPDATE", "user", user_id, ",".join(codes))
    return {"ok": True, "updated": len(result)}


@router.put("/users/{user_id}/modules")
def users_update_modules(user_id: int, payload: UpdateUserModulesRequest, user: dict = Depends(current_user)) -> dict:
    _ensure_can_modify(get_user_by_id(user_id), user)
    try:
        set_user_modules(user_id, payload.module_codes, int(user["id"]))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    insert_audit(int(user["id"]), "USER_MODULES_UPDATE", "user", user_id, ",".join(payload.module_codes))
    return {"ok": True}


@router.put("/users/{user_id}/status")
def users_update_status(user_id: int, payload: UpdateUserStatusRequest, user: dict = Depends(current_user)) -> dict:
    _ensure_can_modify(get_user_by_id(user_id), user)
    if not payload.is_active and _es_uno_mismo(user_id, user):
        raise HTTPException(status_code=400, detail="No puedes desactivar tu propio usuario")
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


@router.post("/sessions/logout-all")
def logout_all_sessions(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "super_admin":
        raise HTTPException(status_code=403, detail="Solo super_admin")
    invalidate_all_sessions(int(user["id"]))
    insert_audit(int(user["id"]), "LOGOUT_ALL_USERS", "session", None, None)
    return {"ok": True}
