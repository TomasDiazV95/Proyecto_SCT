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

export function canAccessModule(user, moduleCode) {
  if (!moduleCode) {
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

  return (panel.modules || []).some((module) => hasAssignedModule(user, module.code));
}

export function getVisibleModules(user, panel) {
  if (panel.adminOnly) {
    return isAdminRole(user) || hasAssignedModule(user, panel.code) ? panel.modules : [];
  }

  if (hasGlobalAccess(user) || hasAssignedModule(user, panel.code)) {
    return panel.modules;
  }

  return (panel.modules || []).filter((module) => hasAssignedModule(user, module.code));
}
