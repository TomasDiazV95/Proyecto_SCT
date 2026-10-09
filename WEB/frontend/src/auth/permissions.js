import { GLOBAL_MODULE_CODE } from "../app/moduleCatalog";

export function isSuperAdmin(user) {
  return user?.role === "super_admin";
}

export function isAdmin(user) {
  return user?.role === "admin";
}

export function isAdminRole(user) {
  return isSuperAdmin(user) || isAdmin(user);
}

export function hasAssignedModule(user, moduleCode) {
  return Boolean(moduleCode && (user?.modules || []).includes(moduleCode));
}

export function hasGlobalAccess(user) {
  return isAdminRole(user) || hasAssignedModule(user, GLOBAL_MODULE_CODE);
}

// Modulos que tambien se abren con otro modulo asignado. Cumplimientos (rrhh): cada supervisor
// entra con los paneles de productividad de sus negocios y ve solo esos (lo filtra el backend).
const MODULE_GRANTED_BY = {
  rrhh: ["sc-tardia", "sc-temprana", "gm", "itau-castigo", "itau-vencida", "itau-vigente", "bit", "bit-castigo", "sth", "la-araucana"],
};

export function canAccessModule(user, moduleCode) {
  if (!moduleCode) {
    return true;
  }
  if ((MODULE_GRANTED_BY[moduleCode] || []).some((code) => hasAssignedModule(user, code))) {
    return true;
  }
  if (moduleCode === "admin") {
    return isAdminRole(user) || hasAssignedModule(user, moduleCode);
  }
  return hasGlobalAccess(user) || hasAssignedModule(user, moduleCode);
}

export function canAccessPanel(user, panel) {
  if (panel.adminOnly) {
    return isAdminRole(user) || hasAssignedModule(user, panel.code);
  }

  if (hasGlobalAccess(user) || hasAssignedModule(user, panel.code)) {
    return true;
  }

  return (panel.modules || []).some((module) => canAccessModule(user, module.code));
}

export function getVisibleModules(user, panel) {
  let modules;
  if (panel.adminOnly) {
    modules = isAdminRole(user) || hasAssignedModule(user, panel.code) ? panel.modules : [];
  } else if (hasGlobalAccess(user) || hasAssignedModule(user, panel.code)) {
    modules = panel.modules;
  } else {
    modules = (panel.modules || []).filter((module) => canAccessModule(user, module.code));
  }
  // Modulos con permiso propio: tener el panel no alcanza, hay que poder abrir el modulo.
  return (modules || []).filter((module) => !module.requiresOwnAccess || canAccessModule(user, module.code));
}
