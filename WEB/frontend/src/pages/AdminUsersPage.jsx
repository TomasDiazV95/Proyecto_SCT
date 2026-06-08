import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import {
  createAdminUser,
  fetchAdminModules,
  fetchAdminUsers,
  updateAdminUserModules,
  updateAdminUserStatus,
} from "../api";

const initialCreate = {
  email: "",
  full_name: "",
  role: "ejecutivo",
  module_codes: [],
};

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

  const canCreateAdmin = user?.role === "super_admin";

  async function loadAll() {
    setLoading(true);
    setError("");
    try {
      const [usersData, modulesData] = await Promise.all([fetchAdminUsers(), fetchAdminModules()]);
      setUsers(usersData);
      setModules(modulesData);
    } catch (err) {
      setError(err.message || "No se pudo cargar administracion de usuarios");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAll();
  }, []);

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

  const roleOptions = useMemo(() => {
    const base = ["coordinador", "supervisor", "ejecutivo"];
    if (canCreateAdmin) {
      return ["admin", ...base];
    }
    return base;
  }, [canCreateAdmin]);

  function toggleCreateModule(code) {
    setCreateForm((prev) => ({
      ...prev,
      module_codes: prev.module_codes.includes(code)
        ? prev.module_codes.filter((x) => x !== code)
        : [...prev.module_codes, code],
    }));
  }

  async function onCreateUser(e) {
    e.preventDefault();
    setError("");
    setMessage("");
    const role = createForm.role;
    if ((role === "supervisor" || role === "ejecutivo") && createForm.module_codes.length === 0) {
      setError("Supervisor y ejecutivo deben tener al menos un modulo");
      return;
    }
    try {
      const result = await createAdminUser(createForm);
      await loadAll();
      setShowCreate(false);
      setCreateForm(initialCreate);
      if (result.email_sent) {
        setMessage("Usuario creado y correo enviado correctamente.");
      } else {
        setMessage(`Usuario creado, pero el correo no se envio: ${result.email_error || "sin detalle"}`);
      }
    } catch (err) {
      setError(err.message || "No se pudo crear el usuario");
    }
  }

  function openEditModules(row) {
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
      setMessage("Modulos actualizados correctamente.");
    } catch (err) {
      setError(err.message || "No se pudieron actualizar modulos");
    }
  }

  async function onToggleStatus(row) {
    setError("");
    setMessage("");
    try {
      await updateAdminUserStatus(row.id, !row.is_active);
      await loadAll();
      setMessage("Estado de usuario actualizado.");
    } catch (err) {
      setError(err.message || "No se pudo actualizar estado");
    }
  }

  return (
    <div className="container-fluid py-4 app-shell">
      <div className="d-flex justify-content-between align-items-center mb-3">
        <div>
          <h1 className="h3 m-0">Administracion de usuarios</h1>
          <Link to="/" className="small text-decoration-none">Volver al Home</Link>
        </div>
        <button className="btn btn-primary" onClick={() => setShowCreate(true)}>Crear usuario</button>
      </div>

      <div className="card shadow-sm mb-3">
        <div className="card-body">
          <div className="row g-2">
            <div className="col-12 col-md-4">
              <label className="form-label">Buscar</label>
              <input className="form-control" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Email o nombre" />
            </div>
            <div className="col-12 col-md-3">
              <label className="form-label">Rol</label>
              <select className="form-select" value={roleFilter} onChange={(e) => setRoleFilter(e.target.value)}>
                <option value="">Todos</option>
                {["super_admin", "admin", "coordinador", "supervisor", "ejecutivo"].map((r) => (
                  <option key={r} value={r}>{r}</option>
                ))}
              </select>
            </div>
            <div className="col-12 col-md-3">
              <label className="form-label">Estado</label>
              <select className="form-select" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
                <option value="">Todos</option>
                <option value="active">Activos</option>
                <option value="inactive">Inactivos</option>
              </select>
            </div>
          </div>
        </div>
      </div>

      {message && <div className="alert alert-success">{message}</div>}
      {error && <div className="alert alert-danger">{error}</div>}

      <div className="card shadow-sm">
        <div className="card-body table-responsive">
          {loading ? (
            <div className="text-center py-4">Cargando...</div>
          ) : (
            <table className="table table-striped align-middle">
              <thead>
                <tr>
                  <th>Email</th>
                  <th>Nombre</th>
                  <th>Rol</th>
                  <th>Modulos</th>
                  <th>Estado</th>
                  <th>Cambio clave</th>
                  <th>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {filteredUsers.map((row) => (
                  <tr key={row.id}>
                    <td>{row.email}</td>
                    <td>{row.full_name}</td>
                    <td><span className="badge text-bg-secondary">{row.role_code}</span></td>
                    <td>{(row.modules || []).length ? row.modules.join(", ") : "-"}</td>
                    <td>
                      <span className={`badge ${row.is_active ? "text-bg-success" : "text-bg-danger"}`}>
                        {row.is_active ? "Activo" : "Inactivo"}
                      </span>
                    </td>
                    <td>{row.must_change_password ? "Pendiente" : "OK"}</td>
                    <td className="d-flex gap-2">
                      <button className="btn btn-sm btn-outline-primary" onClick={() => openEditModules(row)}>Modulos</button>
                      <button className="btn btn-sm btn-outline-secondary" onClick={() => onToggleStatus(row)}>
                        {row.is_active ? "Desactivar" : "Activar"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {showCreate && (
        <div className="admin-modal-backdrop">
          <div className="admin-modal card shadow">
            <div className="card-body">
              <h2 className="h5 mb-3">Crear usuario</h2>
              <form onSubmit={onCreateUser}>
                <label className="form-label">Correo corporativo</label>
                <input className="form-control mb-2" type="email" required value={createForm.email} onChange={(e) => setCreateForm((p) => ({ ...p, email: e.target.value }))} />
                <label className="form-label">Nombre completo</label>
                <input className="form-control mb-2" required value={createForm.full_name} onChange={(e) => setCreateForm((p) => ({ ...p, full_name: e.target.value }))} />
                <label className="form-label">Rol</label>
                <select className="form-select mb-2" value={createForm.role} onChange={(e) => setCreateForm((p) => ({ ...p, role: e.target.value }))}>
                  {roleOptions.map((role) => (
                    <option key={role} value={role}>{role}</option>
                  ))}
                </select>
                <label className="form-label">Modulos</label>
                <div className="admin-module-grid mb-3">
                  {modules.map((module) => (
                    <label key={module.code} className="form-check admin-module-item">
                      <input className="form-check-input" type="checkbox" checked={createForm.module_codes.includes(module.code)} onChange={() => toggleCreateModule(module.code)} />
                      <span className="form-check-label">{module.display_name}</span>
                    </label>
                  ))}
                </div>
                <div className="d-flex gap-2">
                  <button className="btn btn-primary" type="submit">Crear</button>
                  <button className="btn btn-outline-secondary" type="button" onClick={() => setShowCreate(false)}>Cancelar</button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

      {editUser && (
        <div className="admin-modal-backdrop">
          <div className="admin-modal card shadow">
            <div className="card-body">
              <h2 className="h5 mb-2">Editar modulos</h2>
              <p className="small text-muted mb-3">{editUser.email}</p>
              <div className="admin-module-grid mb-3">
                {modules.map((module) => (
                  <label key={module.code} className="form-check admin-module-item">
                    <input className="form-check-input" type="checkbox" checked={editModules.includes(module.code)} onChange={() => toggleEditModule(module.code)} />
                    <span className="form-check-label">{module.display_name}</span>
                  </label>
                ))}
              </div>
              <div className="d-flex gap-2">
                <button className="btn btn-primary" onClick={saveEditModules}>Guardar</button>
                <button className="btn btn-outline-secondary" onClick={() => setEditUser(null)}>Cancelar</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
