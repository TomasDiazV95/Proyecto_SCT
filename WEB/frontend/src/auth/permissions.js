// El backend calcula que modulos puede abrir cada usuario (auth/permissions.py) y los entrega en
// user.access: rol, acceso global y paneles completos ya vienen resueltos. Aqui solo se consulta.
// user.modules son los asignados a mano; se usan en el Panel Admin, no para decidir acceso.

function accessOf(user) {
  return user?.access || [];
}

export function canAccessModule(user, moduleCode) {
  if (!moduleCode) {
    return true;
  }
  return accessOf(user).includes(moduleCode);
}

export function getVisibleModules(user, panel) {
  return (panel.modules || []).filter((module) => canAccessModule(user, module.code));
}

export function canAccessPanel(user, panel) {
  return canAccessModule(user, panel.code) || getVisibleModules(user, panel).length > 0;
}
