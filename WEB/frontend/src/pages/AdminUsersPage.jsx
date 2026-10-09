import React, { useEffect, useMemo, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import {
  bulkUpdateAdminUserModules,
  createAdminUser,
  fetchAdminModules,
  fetchAdminUsers,
  updateAdminUserModules,
  updateAdminUserStatus,
} from "../api";
import { Drawer, EmptyRow, Field, FilterBar, LoadingState, PageHeader, SectionCard, Segmented } from "../components/productividad/ui";

const initialCreate = {
  email: "",
  full_name: "",
  role: "ejecutivo",
  module_codes: [],
};

const BREADCRUMB = [
  { label: "Inicio", to: "/" },
  { label: "Panel Admin", to: "/admin" },
];

const ROLE_LABEL = {
  super_admin: "Super administrador",
  admin: "Administrador",
  coordinador: "Coordinador",
  supervisor: "Supervisor",
  ejecutivo: "Ejecutivo",
};

const ALL_ROLES = ["super_admin", "admin", "coordinador", "supervisor", "ejecutivo"];
const MAX_MODULE_CHIPS = 3;

function roleLabel(code) {
  return ROLE_LABEL[code] || code || "-";
}

// Agrupa los modulos por panel (parent_code del backend). Los que no pertenecen a un panel van juntos al final.
function groupModules(modules) {
  const panels = modules.filter((module) => modules.some((item) => item.parent_code === module.code));
  const groups = panels.map((panel) => ({
    panel,
    title: panel.display_name,
    items: modules.filter((module) => module.parent_code === panel.code),
  }));
  const sueltos = modules.filter((module) => !module.parent_code && !panels.includes(module));
  return [...groups, { panel: null, title: "Otros paneles y accesos", items: sueltos }].filter((group) => group.items.length);
}

// panelIncludes: al marcar "Todo el panel" sus modulos se muestran incluidos (asi es como da acceso).
// En la asignacion masiva se apaga, porque ahi cada casilla es solo lo que se agrega o se quita.
function ModulePicker({ modules, selected, onToggle, panelIncludes = true }) {
  const groups = useMemo(() => groupModules(modules), [modules]);
  return (
    <div className="pd-module-picker">
      {groups.map((group) => {
        const panelOn = Boolean(group.panel && selected.includes(group.panel.code));
        const included = panelOn && panelIncludes;
        return (
          <fieldset className="pd-module-picker-group" key={group.title}>
            <legend>{group.title}</legend>
            {group.panel && (
              <label className={`pd-module-option pd-module-option-panel${panelOn ? " is-selected" : ""}`}>
                <input className="form-check-input" type="checkbox" checked={panelOn} onChange={() => onToggle(group.panel.code)} />
                <span>
                  Todo el panel
                  <small>Incluye sus módulos actuales y los que se agreguen después.</small>
                </span>
              </label>
            )}
            <div className="pd-module-picker-items">
              {group.items.map((module) => {
                const checked = included || selected.includes(module.code);
                return (
                  <label key={module.code} className={`pd-module-option${checked ? " is-selected" : ""}${included ? " is-included" : ""}`}>
                    <input className="form-check-input" type="checkbox" checked={checked} disabled={included} onChange={() => onToggle(module.code)} />
                    <span>{module.display_name}</span>
                  </label>
                );
              })}
            </div>
          </fieldset>
        );
      })}
    </div>
  );
}

export default function AdminUsersPage() {
  const { user } = useAuth();
  const [users, setUsers] = useState([]);
  const [modules, setModules] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState(initialCreate);

  const [editUser, setEditUser] = useState(null);
  const [editModules, setEditModules] = useState([]);

  // Asignacion masiva: usuarios marcados en la tabla y modulos a agregar o quitar.
  const [selectedIds, setSelectedIds] = useState([]);
  const [showBulk, setShowBulk] = useState(false);
  const [bulkMode, setBulkMode] = useState("add");
  const [bulkModules, setBulkModules] = useState([]);

  const canCreateAdmin = user?.role === "super_admin";

  async function loadAll() {
    setLoading(true);
    setError("");
    try {
      const [usersData, modulesData] = await Promise.all([fetchAdminUsers(), fetchAdminModules()]);
      setUsers(usersData);
      setModules(modulesData);
      setSelectedIds((prev) => prev.filter((id) => usersData.some((item) => item.id === id)));
    } catch (err) {
      setError(err.message || "No se pudo cargar la administración de usuarios.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAll();
  }, []);

  const moduleName = useMemo(() => Object.fromEntries(modules.map((module) => [module.code, module.display_name])), [modules]);

  const filteredUsers = useMemo(() => {
    const text = search.trim().toLowerCase();
    return users.filter((item) => {
      if (roleFilter && item.role_code !== roleFilter) {
        return false;
      }
      if (statusFilter === "active" && !item.is_active) {
        return false;
      }
      if (statusFilter === "inactive" && item.is_active) {
        return false;
      }
      if (!text) {
        return true;
      }
      return (
        String(item.email || "").toLowerCase().includes(text) ||
        String(item.full_name || "").toLowerCase().includes(text)
      );
    });
  }, [users, search, roleFilter, statusFilter]);

  const activos = users.filter((item) => item.is_active).length;
  const statusOptions = [
    { value: "", label: `Todos (${users.length})` },
    { value: "active", label: `Activos (${activos})` },
    { value: "inactive", label: `Inactivos (${users.length - activos})` },
  ];

  const roleOptions = useMemo(() => {
    const base = ["coordinador", "supervisor", "ejecutivo"];
    if (canCreateAdmin) {
      return ["admin", ...base];
    }
    return base;
  }, [canCreateAdmin]);

  const hasFilters = Boolean(search || roleFilter || statusFilter);

  function clearFilters() {
    setSearch("");
    setRoleFilter("");
    setStatusFilter("");
  }

  function toggleCreateModule(code) {
    setCreateForm((prev) => ({
      ...prev,
      module_codes: prev.module_codes.includes(code)
        ? prev.module_codes.filter((x) => x !== code)
        : [...prev.module_codes, code],
    }));
  }

  function closeCreate() {
    setShowCreate(false);
    setCreateForm(initialCreate);
  }

  async function onCreateUser(e) {
    e.preventDefault();
    setError("");
    setMessage("");
    const role = createForm.role;
    if ((role === "supervisor" || role === "ejecutivo") && createForm.module_codes.length === 0) {
      setError("Un supervisor o ejecutivo necesita al menos un módulo. Marca los módulos que usará.");
      return;
    }
    try {
      const result = await createAdminUser(createForm);
      await loadAll();
      closeCreate();
      if (result.email_sent) {
        setMessage("Usuario creado. Se envió el correo con la contraseña temporal.");
      } else {
        setMessage(`Usuario creado, pero el correo no se envió: ${result.email_error || "sin detalle"}. Comparte el acceso por otro medio.`);
      }
    } catch (err) {
      setError(err.message || "No se pudo crear el usuario.");
    }
  }

  function openEditModules(row) {
    setError("");
    setEditUser(row);
    setEditModules([...(row.modules || [])]);
  }

  function toggleEditModule(code) {
    setEditModules((prev) =>
      prev.includes(code) ? prev.filter((x) => x !== code) : [...prev, code]
    );
  }

  async function saveEditModules() {
    if (!editUser) {
      return;
    }
    setError("");
    setMessage("");
    try {
      await updateAdminUserModules(editUser.id, editModules);
      await loadAll();
      setEditUser(null);
      setMessage(`Módulos de ${editUser.full_name || editUser.email} actualizados.`);
    } catch (err) {
      setError(err.message || "No se pudieron actualizar los módulos.");
    }
  }

  const allFilteredSelected = filteredUsers.length > 0 && filteredUsers.every((row) => selectedIds.includes(row.id));

  function toggleSelected(id) {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }

  function toggleSelectFiltered() {
    const ids = filteredUsers.map((row) => row.id);
    setSelectedIds((prev) => (allFilteredSelected ? prev.filter((id) => !ids.includes(id)) : [...new Set([...prev, ...ids])]));
  }

  function openBulk() {
    setError("");
    setBulkMode("add");
    setBulkModules([]);
    setShowBulk(true);
  }

  function toggleBulkModule(code) {
    setBulkModules((prev) => (prev.includes(code) ? prev.filter((x) => x !== code) : [...prev, code]));
  }

  async function saveBulk() {
    setError("");
    setMessage("");
    if (!bulkModules.length) {
      setError("Marca al menos un módulo.");
      return;
    }
    try {
      const result = await bulkUpdateAdminUserModules(selectedIds, bulkMode === "add" ? { add: bulkModules } : { remove: bulkModules });
      await loadAll();
      setShowBulk(false);
      setSelectedIds([]);
      setMessage(`Módulos ${bulkMode === "add" ? "agregados a" : "quitados de"} ${result.updated} ${result.updated === 1 ? "usuario" : "usuarios"}.`);
    } catch (err) {
      setError(err.message || "No se pudieron actualizar los módulos.");
    }
  }

  async function onToggleStatus(row) {
    setError("");
    setMessage("");
    try {
      await updateAdminUserStatus(row.id, !row.is_active);
      await loadAll();
      setMessage(`${row.full_name || row.email} quedó ${row.is_active ? "desactivado" : "activado"}.`);
    } catch (err) {
      setError(err.message || "No se pudo actualizar el estado.");
    }
  }

  return (
    <div className="pd-page">
      <PageHeader
        title="Usuarios"
        subtitle="Crea usuarios, asigna los módulos que pueden ver y activa o desactiva su acceso."
        breadcrumb={BREADCRUMB}
        actions={
          <>
            <button type="button" className="pd-btn pd-btn-secondary" onClick={openBulk} disabled={!selectedIds.length} title={selectedIds.length ? undefined : "Marca usuarios en la tabla para asignarles módulos a la vez"}>
              <i className="bi bi-grid" aria-hidden="true" /> Asignar módulos{selectedIds.length ? ` (${selectedIds.length})` : ""}
            </button>
            <button type="button" className="pd-btn pd-btn-primary" onClick={() => setShowCreate(true)}>
              <i className="bi bi-person-plus" aria-hidden="true" /> Crear usuario
            </button>
          </>
        }
      />

      <FilterBar
        actions={
          <button type="button" className="pd-btn pd-btn-ghost" onClick={clearFilters} disabled={!hasFilters}>
            <i className="bi bi-x-circle" aria-hidden="true" /> Limpiar filtros
          </button>
        }
      >
        <Field label="Buscar">
          <input className="form-control" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Nombre o correo" />
        </Field>
        <Field label="Rol">
          <select className="form-select" value={roleFilter} onChange={(e) => setRoleFilter(e.target.value)}>
            <option value="">Todos</option>
            {ALL_ROLES.map((r) => (
              <option key={r} value={r}>{roleLabel(r)}</option>
            ))}
          </select>
        </Field>
        <div className="pd-field pd-field-wide">
          <span className="pd-label">Estado</span>
          <Segmented value={statusFilter} onChange={setStatusFilter} options={statusOptions} />
        </div>
      </FilterBar>

      {message && <div className="alert alert-success">{message}</div>}
      {error && !showCreate && !editUser && !showBulk && <div className="alert alert-danger">{error}</div>}

      <SectionCard bodyClassName="" footer={<span>Mostrando {filteredUsers.length} de {users.length} usuarios</span>}>
        {loading ? (
          <LoadingState text="Cargando usuarios..." />
        ) : (
          <div className="pd-table-scroll">
            <table className="pd-table pd-users-table">
              <thead>
                <tr>
                  <th className="pd-users-check">
                    <input className="form-check-input" type="checkbox" checked={allFilteredSelected} onChange={toggleSelectFiltered} aria-label="Seleccionar todos los usuarios mostrados" />
                  </th>
                  <th>Usuario</th>
                  <th>Rol</th>
                  <th>Módulos</th>
                  <th>Estado</th>
                  <th>Contraseña</th>
                  <th>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {filteredUsers.map((row) => {
                  const userModules = row.modules || [];
                  const extra = userModules.length - MAX_MODULE_CHIPS;
                  return (
                    <tr key={row.id} className={row.is_active ? undefined : "pd-row-inactive"}>
                      <td className="pd-users-check">
                        <input className="form-check-input" type="checkbox" checked={selectedIds.includes(row.id)} onChange={() => toggleSelected(row.id)} aria-label={`Seleccionar a ${row.full_name || row.email}`} />
                      </td>
                      <td>
                        <span className="pd-user-name">{row.full_name || "Sin nombre"}</span>
                        <span className="pd-cell-sub">{row.email}</span>
                      </td>
                      <td>
                        <span className={`pd-role pd-role-${row.role_code}`}>{roleLabel(row.role_code)}</span>
                      </td>
                      <td>
                        {userModules.length ? (
                          <span className="pd-user-modules">
                            {userModules.slice(0, MAX_MODULE_CHIPS).map((code) => (
                              <span className="pd-user-module" key={code}>{moduleName[code] || code}</span>
                            ))}
                            {extra > 0 && (
                              <span className="pd-user-module pd-user-module-more" title={userModules.slice(MAX_MODULE_CHIPS).map((code) => moduleName[code] || code).join(", ")}>
                                +{extra}
                              </span>
                            )}
                          </span>
                        ) : (
                          <span className="pd-cell-muted">Sin módulos</span>
                        )}
                      </td>
                      <td>
                        <span className={`pd-status ${row.is_active ? "pd-status-success" : "pd-status-neutral"}`}>{row.is_active ? "Activo" : "Inactivo"}</span>
                      </td>
                      <td>
                        {row.must_change_password ? (
                          <span className="pd-status pd-status-warning">Pendiente de cambio</span>
                        ) : (
                          <span className="pd-cell-muted">Al día</span>
                        )}
                      </td>
                      <td>
                        <span className="pd-user-actions">
                          <button type="button" className="pd-btn pd-btn-secondary pd-btn-sm" onClick={() => openEditModules(row)}>
                            <i className="bi bi-grid" aria-hidden="true" /> Editar módulos
                          </button>
                          <button
                            type="button"
                            className={`pd-btn pd-btn-ghost pd-btn-sm${row.is_active ? " pd-btn-danger-text" : ""}`}
                            onClick={() => onToggleStatus(row)}
                          >
                            {row.is_active ? "Desactivar" : "Activar"}
                          </button>
                        </span>
                      </td>
                    </tr>
                  );
                })}
                {!filteredUsers.length && (
                  <EmptyRow colSpan={7} text={users.length ? "Ningún usuario coincide con los filtros. Prueba con otro nombre o limpia los filtros." : "Aún no hay usuarios. Crea el primero con el botón Crear usuario."} />
                )}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>

      <Drawer
        open={showCreate}
        onClose={closeCreate}
        title="Crear usuario"
        subtitle="Recibirá un correo con una contraseña temporal que deberá cambiar al entrar."
        wide
        footer={
          <>
            <button type="button" className="pd-btn pd-btn-ghost" onClick={closeCreate}>Cancelar</button>
            <button type="submit" form="pd-create-user" className="pd-btn pd-btn-primary">
              <i className="bi bi-person-plus" aria-hidden="true" /> Crear usuario
            </button>
          </>
        }
      >
        <form id="pd-create-user" className="pd-user-form" onSubmit={onCreateUser}>
          {error && <div className="alert alert-danger">{error}</div>}
          <div className="pd-user-form-grid">
            <Field label="Correo corporativo">
              <input className="form-control" type="email" required value={createForm.email} onChange={(e) => setCreateForm((p) => ({ ...p, email: e.target.value }))} />
            </Field>
            <Field label="Nombre completo">
              <input className="form-control" required value={createForm.full_name} onChange={(e) => setCreateForm((p) => ({ ...p, full_name: e.target.value }))} />
            </Field>
            <Field label="Rol">
              <select className="form-select" value={createForm.role} onChange={(e) => setCreateForm((p) => ({ ...p, role: e.target.value }))}>
                {roleOptions.map((role) => (
                  <option key={role} value={role}>{roleLabel(role)}</option>
                ))}
              </select>
            </Field>
          </div>
          <div className="pd-user-form-section">
            <span className="pd-label">Módulos que podrá ver ({createForm.module_codes.length})</span>
            <ModulePicker modules={modules} selected={createForm.module_codes} onToggle={toggleCreateModule} />
          </div>
        </form>
      </Drawer>

      <Drawer
        open={Boolean(editUser)}
        onClose={() => setEditUser(null)}
        title="Editar módulos"
        subtitle={editUser ? `${editUser.full_name || ""} (${editUser.email})` : ""}
        wide
        footer={
          <>
            <button type="button" className="pd-btn pd-btn-ghost" onClick={() => setEditUser(null)}>Cancelar</button>
            <button type="button" className="pd-btn pd-btn-primary" onClick={saveEditModules}>
              <i className="bi bi-check2" aria-hidden="true" /> Guardar módulos
            </button>
          </>
        }
      >
        {error && <div className="alert alert-danger">{error}</div>}
        <span className="pd-label">Módulos que puede ver ({editModules.length})</span>
        <ModulePicker modules={modules} selected={editModules} onToggle={toggleEditModule} />
      </Drawer>

      <Drawer
        open={showBulk}
        onClose={() => setShowBulk(false)}
        title={`Asignar módulos a ${selectedIds.length} ${selectedIds.length === 1 ? "usuario" : "usuarios"}`}
        subtitle="Solo cambian los módulos que marques; el resto de los permisos de cada usuario queda igual."
        wide
        footer={
          <>
            <button type="button" className="pd-btn pd-btn-ghost" onClick={() => setShowBulk(false)}>Cancelar</button>
            <button type="button" className="pd-btn pd-btn-primary" onClick={saveBulk}>
              <i className="bi bi-check2" aria-hidden="true" /> {bulkMode === "add" ? "Agregar módulos" : "Quitar módulos"}
            </button>
          </>
        }
      >
        {error && <div className="alert alert-danger">{error}</div>}
        <div className="pd-user-form-section pd-bulk-mode">
          <span className="pd-label">Acción</span>
          <Segmented
            value={bulkMode}
            onChange={setBulkMode}
            options={[
              { value: "add", label: "Agregar" },
              { value: "remove", label: "Quitar" },
            ]}
          />
        </div>
        <span className="pd-label">Módulos a {bulkMode === "add" ? "agregar" : "quitar"} ({bulkModules.length})</span>
        <ModulePicker modules={modules} selected={bulkModules} onToggle={toggleBulkModule} panelIncludes={false} />
      </Drawer>
    </div>
  );
}
