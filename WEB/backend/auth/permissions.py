import threading
import time

from repositories.users_repo import get_modules_for_user, list_modules


ADMIN_ROLES = {"super_admin", "admin"}
GLOBAL_MODULE = "global"
ADMIN_MODULE = "admin"
RRHH_MODULE = "rrhh"
PRODUCTIVIDAD_PANEL = "productividad"

# El arbol de modulos solo cambia con una migracion; se relee cada minuto.
TREE_TTL = 60  # segundos
_tree_cache: tuple[float, list[dict]] | None = None
_tree_lock = threading.Lock()


def module_tree() -> list[dict]:
    """Modulos activos con su panel (parent_code)."""
    global _tree_cache
    with _tree_lock:
        if _tree_cache and time.monotonic() - _tree_cache[0] < TREE_TTL:
            return _tree_cache[1]
        tree = list_modules()
        _tree_cache = (time.monotonic(), tree)
        return tree


def effective_modules(role: str, assigned: list[str], tree: list[dict]) -> set[str]:
    """Modulos que el usuario puede abrir. Unica regla de acceso: la usan la API y el frontend.

    - Administradores: todo.
    - Acceso global: todo menos el Panel Admin, que se asigna aparte.
    - Un panel asignado abre todos sus modulos (parent_code).
    - Cumplimientos (rrhh) se abre tambien con cualquier negocio de productividad;
      el router de rrhh limita a esos negocios.
    """
    todos = {m["code"] for m in tree}
    if role in ADMIN_ROLES:
        return todos

    access = set(assigned) & todos
    if GLOBAL_MODULE in access:
        return (todos - {ADMIN_MODULE}) | access

    for module in tree:
        if module.get("parent_code") in access:
            access.add(module["code"])

    negocios = {m["code"] for m in tree if m.get("parent_code") == PRODUCTIVIDAD_PANEL}
    if access & negocios and RRHH_MODULE in todos:
        access.add(RRHH_MODULE)
    return access


def user_access(user_id: int, role: str) -> tuple[list[str], list[str]]:
    """(modulos asignados, modulos que puede abrir) del usuario."""
    assigned = [m["code"] for m in get_modules_for_user(user_id)]
    return assigned, sorted(effective_modules(role, assigned, module_tree()))
