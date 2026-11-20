import { useEffect, useMemo, useState } from "react";
import { useAuth } from "../../auth/AuthContext";
import {
  bulkUpdateAdminUserModules,
  createAdminUser,
  fetchAdminModules,
  fetchAdminUsers,
  resetAdminUserPassword,
  unlockAdminUser,
  updateAdminUser,
  updateAdminUserModules,
  updateAdminUserStatus,
} from "../../api";
import { Drawer, EmptyRow, Field, FilterBar, LoadingState, PageHeader, SectionCard, Segmented, ViewTabs } from "../../components/productividad/ui";
import AccessPicker from "./AccessPicker";
import { armarPaneles, contarCambios, cumpleFiltroAcceso, expandirParaQuitar, filtroDeChip, opcionesFiltroAcceso, resumenAccesos } from "./accesos";

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
const ROLES_ADMIN = ["super_admin", "admin"];
const MAX_CHIPS = 3;

const TABS = [
  { value: "accesos", label: "Accesos", icon: "bi-grid" },
  { value: "datos", label: "Datos", icon: "bi-person" },
  { value: "seguridad", label: "Seguridad", icon: "bi-shield-lock" },
];

function roleLabel(code) {
  return ROLE_LABEL[code] || code || "-";
}

function nombreDe(row) {
  return row?.full_name || row?.email || "";
}

// Un solo estado por usuario, en orden de importancia.
function estadoUsuario(row) {
  if (!row.is_active) return { label: "Inactivo", cls: "pd-status-neutral" };
  if (row.locked) return { label: "Bloqueado", cls: "pd-status-danger" };
  if (row.must_change_password) return { label: "Contraseña pendiente", cls: "pd-status-warning" };
  return { label: "Activo", cls: "pd-status-success" };
}

// Fechas siempre en hora de Chile (el backend las entrega en UTC).
const ZONA_CHILE = "America/Santiago";
const DIA_CHILE = new Intl.DateTimeFormat("en-CA", { timeZone: ZONA_CHILE, year: "numeric", month: "2-digit", day: "2-digit" });

function fechaHora(iso) {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("es-CL", { dateStyle: "medium", timeStyle: "short", timeZone: ZONA_CHILE }).format(new Date(iso));
}

// Dias de calendario (en Chile) entre la fecha y hoy: ayer a las 15:33 es "Ayer" aunque no hayan pasado 24 h.
function diasCalendario(fecha) {
  const [a, m, d] = DIA_CHILE.format(fecha).split("-").map(Number);
  return Date.UTC(a, m - 1, d) / 86400000;
}

function haceCuanto(iso) {
  if (!iso) return "Nunca";
  const dias = diasCalendario(new Date()) - diasCalendario(new Date(iso));
  if (dias <= 0) return "Hoy";
  if (dias === 1) return "Ayer";
  if (dias < 30) return `Hace ${dias} días`;
  const meses = Math.floor(dias / 30);
  return meses < 12 ? `Hace ${meses} ${meses === 1 ? "mes" : "meses"}` : "Hace más de un año";
}

// Cada chip filtra la tabla por ese acceso (onFiltrar recibe el codigo del chip).
function AccesosChips({ resumen, onFiltrar }) {
  const { items } = resumen;
  if (!items.length) {
    return <span className="pd-cell-muted">Sin accesos</span>;
  }
  const resto = items.slice(MAX_CHIPS);
  return (
    <span className="pd-user-modules">
      {items.slice(0, MAX_CHIPS).map((item) => {
        const clase = `pd-user-module${item.completo ? " is-completo" : ""}`;
        const titulo = [item.detalle, "Clic para ver quién más tiene este acceso"].filter(Boolean).join("\n");
        return item.code === "_todo" ? (
          <span key={item.code} className={clase}>{item.etiqueta}</span>
        ) : (
          <button key={item.code} type="button" className={`${clase} pd-user-module-filtro`} title={titulo} onClick={() => onFiltrar(item.code)}>
            {item.etiqueta}
          </button>
        );
      })}
      {resto.length > 0 && (
        <span className="pd-user-module pd-user-module-more" title={resto.map((item) => item.etiqueta).join("\n")}>
          +{resto.length}
        </span>
      )}
    </span>
  );
}

// Accion de la pestana Seguridad, con confirmacion dentro del mismo bloque.
function AccionSeguridad({ icono, titulo, detalle, boton, confirmar, peligro = false, disabled = false, motivo, onRun }) {
  const [preguntando, setPreguntando] = useState(false);
  const [busy, setBusy] = useState(false);
  async function run() {
    setBusy(true);
    try {
      await onRun();
    } finally {
      setBusy(false);
      setPreguntando(false);
    }
  }
  return (
    <div className="pd-user-accion">
      <i className={`bi ${icono}`} aria-hidden="true" />
      <div className="pd-user-accion-texto">
        <strong>{titulo}</strong>
        <span>{disabled && motivo ? motivo : detalle}</span>
        {preguntando && (
          <div className="pd-user-accion-confirmar" role="alert">
            <span>{confirmar}</span>
            <button type="button" className={`pd-btn pd-btn-sm ${peligro ? "pd-btn-danger" : "pd-btn-primary"}`} onClick={run} disabled={busy}>
              {busy ? <span className="spinner-border spinner-border-sm" aria-hidden="true" /> : "Sí, continuar"}
            </button>
            <button type="button" className="pd-btn pd-btn-ghost pd-btn-sm" onClick={() => setPreguntando(false)} disabled={busy}>Cancelar</button>
          </div>
        )}
      </div>
      {!preguntando && (
        <button
          type="button"
          className={`pd-btn pd-btn-sm ${peligro ? "pd-btn-ghost pd-btn-danger-text" : "pd-btn-secondary"}`}
          onClick={() => (confirmar ? setPreguntando(true) : run())}
          disabled={disabled || busy}
        >
          {boton}
        </button>
      )}
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
  const [accessFilter, setAccessFilter] = useState("");

  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState(initialCreate);

  // Panel lateral de un usuario: accesos, datos y seguridad.
  const [gestionId, setGestionId] = useState(null);
  const [tab, setTab] = useState("accesos");
  const [editModules, setEditModules] = useState([]);
  const [editDatos, setEditDatos] = useState({ full_name: "", role: "" });
  const [guardando, setGuardando] = useState(false);

  // Asignacion masiva: usuarios marcados en la tabla y accesos a agregar o quitar.
  const [selectedIds, setSelectedIds] = useState([]);
  const [showBulk, setShowBulk] = useState(false);
  const [bulkMode, setBulkMode] = useState("add");
  const [bulkModules, setBulkModules] = useState([]);

  const isSuperAdmin = user?.role === "super_admin";

  async function loadAll() {
    setLoading(true);
    setError("");
    try {
      const [usersData, modulesData] = await Promise.all([fetchAdminUsers(), fetchAdminModules()]);
      setUsers(usersData);
      setModules(modulesData);
      setSelectedIds((prev) => prev.filter((id) => usersData.some((item) => item.id === id)));
      return usersData;
    } catch (err) {
      setError(err.message || "No se pudo cargar la administración de usuarios.");
      return null;
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAll();
  }, []);

  const paneles = useMemo(() => armarPaneles(modules), [modules]);
  const opcionesAcceso = useMemo(() => opcionesFiltroAcceso(paneles), [paneles]);
  const resumenes = useMemo(
    () => Object.fromEntries(users.map((row) => [row.id, resumenAccesos(row.role_code, row.modules, row.access, paneles)])),
    [users, paneles]
  );
  const gestion = users.find((row) => row.id === gestionId) || null;

  function puedeModificar(row) {
    return isSuperAdmin || !ROLES_ADMIN.includes(row.role_code);
  }

  const filteredUsers = useMemo(() => {
    const text = search.trim().toLowerCase();
    return users.filter((item) => {
      if (roleFilter && item.role_code !== roleFilter) return false;
      if (statusFilter === "active" && !item.is_active) return false;
      if (statusFilter === "inactive" && item.is_active) return false;
      if (statusFilter === "locked" && !item.locked) return false;
      if (accessFilter && !cumpleFiltroAcceso(accessFilter, item, paneles)) return false;
      if (!text) return true;
      return String(item.email || "").toLowerCase().includes(text) || String(item.full_name || "").toLowerCase().includes(text);
    });
  }, [users, search, roleFilter, statusFilter, accessFilter, paneles]);

  const activos = users.filter((item) => item.is_active).length;
  const bloqueados = users.filter((item) => item.locked).length;
  const statusOptions = [
    { value: "", label: `Todos (${users.length})` },
    { value: "active", label: `Activos (${activos})` },
    { value: "inactive", label: `Inactivos (${users.length - activos})` },
    ...(bloqueados ? [{ value: "locked", label: `Bloqueados (${bloqueados})` }] : []),
  ];

  const roleOptions = useMemo(() => {
    const base = ["coordinador", "supervisor", "ejecutivo"];
    return isSuperAdmin ? ["admin", ...base] : base;
  }, [isSuperAdmin]);

  const hasFilters = Boolean(search || roleFilter || statusFilter || accessFilter);

  function clearFilters() {
    setSearch("");
    setRoleFilter("");
    setStatusFilter("");
    setAccessFilter("");
  }

  // ---- Crear ----
  function closeCreate() {
    setShowCreate(false);
    setCreateForm(initialCreate);
    setError("");
  }

  async function onCreateUser(e) {
    e.preventDefault();
    setError("");
    setMessage("");
    const role = createForm.role;
    if ((role === "supervisor" || role === "ejecutivo") && createForm.module_codes.length === 0) {
      setError("Un supervisor o ejecutivo necesita al menos un acceso. Marca los paneles o módulos que usará.");
      return;
    }
    setGuardando(true);
    try {
      const result = await createAdminUser(createForm);
      await loadAll();
      closeCreate();
      setMessage(
        result.email_sent
          ? "Usuario creado. Se envió el correo con la contraseña temporal."
          : `Usuario creado, pero el correo no se envió: ${result.email_error || "sin detalle"}. Comparte el acceso por otro medio.`
      );
    } catch (err) {
      setError(err.message || "No se pudo crear el usuario.");
    } finally {
      setGuardando(false);
    }
  }

  // ---- Gestionar un usuario ----
  function abrirGestion(row, pestana = "accesos") {
    setError("");
    setMessage("");
    setGestionId(row.id);
    setTab(pestana);
    setEditModules([...(row.modules || [])]);
    setEditDatos({ full_name: row.full_name || "", role: row.role_code });
  }

  function cerrarGestion() {
    setGestionId(null);
    setError("");
  }

  const cambiosAccesos = gestion ? contarCambios(gestion.modules, editModules) : 0;
  const cambiosDatos = gestion ? editDatos.full_name.trim() !== (gestion.full_name || "") || editDatos.role !== gestion.role_code : false;
  const esYo = gestion && Number(gestion.id) === Number(user?.id);

  async function guardar(accion, exito) {
    setError("");
    setMessage("");
    setGuardando(true);
    try {
      const result = await accion();
      await loadAll();
      setMessage(typeof exito === "function" ? exito(result) : exito);
      return true;
    } catch (err) {
      setError(err.message || "No se pudo guardar.");
      return false;
    } finally {
      setGuardando(false);
    }
  }

  async function guardarAccesos() {
    const ok = await guardar(() => updateAdminUserModules(gestion.id, editModules), `Accesos de ${nombreDe(gestion)} actualizados.`);
    if (ok) cerrarGestion();
  }

  async function guardarDatos() {
    if (!editDatos.full_name.trim()) {
      setError("Ingresa el nombre del usuario.");
      return;
    }
    await guardar(() => updateAdminUser(gestion.id, { full_name: editDatos.full_name.trim(), role: editDatos.role }), `Datos de ${editDatos.full_name.trim()} actualizados.`);
  }

  // ---- Asignacion masiva ----
  const allFilteredSelected = filteredUsers.length > 0 && filteredUsers.filter(puedeModificar).every((row) => selectedIds.includes(row.id));

  function toggleSelected(id) {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }

  function toggleSelectFiltered() {
    const ids = filteredUsers.filter(puedeModificar).map((row) => row.id);
    setSelectedIds((prev) => (allFilteredSelected ? prev.filter((id) => !ids.includes(id)) : [...new Set([...prev, ...ids])]));
  }

  function openBulk() {
    setError("");
    setBulkMode("add");
    setBulkModules([]);
    setShowBulk(true);
  }

  async function saveBulk() {
    setError("");
    setMessage("");
    if (!bulkModules.length) {
      setError("Marca al menos un panel o módulo.");
      return;
    }
    const codes = bulkMode === "add" ? bulkModules : expandirParaQuitar(bulkModules, paneles);
    setGuardando(true);
    try {
      const result = await bulkUpdateAdminUserModules(selectedIds, bulkMode === "add" ? { add: codes } : { remove: codes });
      await loadAll();
      setShowBulk(false);
      setSelectedIds([]);
      setMessage(`Accesos ${bulkMode === "add" ? "agregados a" : "quitados de"} ${result.updated} ${result.updated === 1 ? "usuario" : "usuarios"}.`);
    } catch (err) {
      setError(err.message || "No se pudieron actualizar los accesos.");
    } finally {
      setGuardando(false);
    }
  }

  const drawerAbierto = showCreate || Boolean(gestion) || showBulk;

  let footerGestion = null;
  if (gestion && tab === "accesos") {
    footerGestion = (
      <>
        <button type="button" className="pd-btn pd-btn-ghost" onClick={cerrarGestion}>Cerrar</button>
        <button type="button" className="pd-btn pd-btn-ghost" onClick={() => setEditModules([...(gestion.modules || [])])} disabled={!cambiosAccesos || guardando}>
          Deshacer cambios
        </button>
        <button type="button" className="pd-btn pd-btn-primary" onClick={guardarAccesos} disabled={!cambiosAccesos || guardando}>
          <i className="bi bi-check2" aria-hidden="true" /> Guardar accesos
        </button>
      </>
    );
  } else if (gestion && tab === "datos") {
    footerGestion = (
      <>
        <button type="button" className="pd-btn pd-btn-ghost" onClick={cerrarGestion}>Cerrar</button>
        <button type="button" className="pd-btn pd-btn-primary" onClick={guardarDatos} disabled={!cambiosDatos || guardando}>
          <i className="bi bi-check2" aria-hidden="true" /> Guardar datos
        </button>
      </>
    );
  } else if (gestion) {
    footerGestion = <button type="button" className="pd-btn pd-btn-ghost" onClick={cerrarGestion}>Cerrar</button>;
  }

  const rolesDatos = gestion && !roleOptions.includes(gestion.role_code) ? [gestion.role_code, ...roleOptions] : roleOptions;

  return (
    <div className="pd-page">
      <PageHeader
        title="Usuarios"
        subtitle="Crea usuarios, define qué paneles y módulos pueden ver y administra su acceso."
        breadcrumb={BREADCRUMB}
        actions={
          <>
            <button type="button" className="pd-btn pd-btn-secondary" onClick={openBulk} disabled={!selectedIds.length} title={selectedIds.length ? undefined : "Marca usuarios en la tabla para cambiarles accesos a la vez"}>
              <i className="bi bi-grid" aria-hidden="true" /> Asignar accesos{selectedIds.length ? ` (${selectedIds.length})` : ""}
            </button>
            <button type="button" className="pd-btn pd-btn-primary" onClick={() => { setError(""); setShowCreate(true); }}>
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
        <Field label="Con acceso a">
          <select className="form-select" value={accessFilter} onChange={(e) => setAccessFilter(e.target.value)}>
            <option value="">Cualquier panel</option>
            {opcionesAcceso.map((grupo) => (
              <optgroup key={grupo.grupo} label={grupo.grupo}>
                {grupo.opciones.map((op) => (
                  <option key={op.value} value={op.value}>{op.label}</option>
                ))}
              </optgroup>
            ))}
          </select>
        </Field>
        <div className="pd-field pd-field-wide">
          <span className="pd-label">Estado</span>
          <Segmented value={statusFilter} onChange={setStatusFilter} options={statusOptions} />
        </div>
      </FilterBar>

      {message && <div className="alert alert-success">{message}</div>}
      {error && !drawerAbierto && <div className="alert alert-danger">{error}</div>}

      <SectionCard bodyClassName="" footer={<span>Mostrando {filteredUsers.length} de {users.length} usuarios</span>}>
        {loading && !users.length ? (
          <LoadingState text="Cargando usuarios..." />
        ) : (
          <div className="pd-table-scroll">
            <table className="pd-table pd-users-table">
              <thead>
                <tr>
                  <th className="pd-users-check">
                    <input className="form-check-input" type="checkbox" checked={allFilteredSelected} onChange={toggleSelectFiltered} aria-label="Seleccionar todos los usuarios mostrados" />
                  </th>
                  <th className="text-start">Usuario</th>
                  <th>Rol</th>
                  <th>Accesos</th>
                  <th>Estado</th>
                  <th>Último ingreso</th>
                  <th aria-label="Acciones" />
                </tr>
              </thead>
              <tbody>
                {filteredUsers.map((row) => {
                  const estado = estadoUsuario(row);
                  const editable = puedeModificar(row);
                  return (
                    <tr key={row.id} className={row.is_active ? undefined : "pd-row-inactive"}>
                      <td className="pd-users-check">
                        <input
                          className="form-check-input"
                          type="checkbox"
                          checked={selectedIds.includes(row.id)}
                          onChange={() => toggleSelected(row.id)}
                          disabled={!editable}
                          aria-label={`Seleccionar a ${nombreDe(row)}`}
                        />
                      </td>
                      <td className="text-start">
                        <span className="pd-user-name">{row.full_name || "Sin nombre"}</span>
                        <span className="pd-cell-sub">{row.email}</span>
                      </td>
                      <td>
                        <span className={`pd-role pd-role-${row.role_code}`}>{roleLabel(row.role_code)}</span>
                      </td>
                      <td>
                        <AccesosChips
                          resumen={resumenes[row.id] || { items: [] }}
                          onFiltrar={(code) => {
                            const filtro = filtroDeChip(code, paneles);
                            if (filtro) setAccessFilter(filtro);
                          }}
                        />
                      </td>
                      <td>
                        <span className={`pd-status ${estado.cls}`}>{estado.label}</span>
                      </td>
                      <td title={row.last_login_at ? fechaHora(row.last_login_at) : undefined}>
                        <span className={row.last_login_at ? undefined : "pd-cell-muted"}>{haceCuanto(row.last_login_at)}</span>
                      </td>
                      <td>
                        <button
                          type="button"
                          className="pd-btn pd-btn-secondary pd-btn-sm"
                          onClick={() => abrirGestion(row)}
                          disabled={!editable}
                          title={editable ? "Accesos, datos y seguridad" : "Solo el super admin puede modificar administradores"}
                        >
                          <i className="bi bi-sliders" aria-hidden="true" /> Gestionar
                        </button>
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

      {/* ---- Crear usuario ---- */}
      <Drawer
        open={showCreate}
        onClose={closeCreate}
        title="Crear usuario"
        subtitle="Recibirá un correo con una contraseña temporal que deberá cambiar al entrar."
        wide
        className="pd-drawer-usuario"
        footer={
          <>
            <button type="button" className="pd-btn pd-btn-ghost" onClick={closeCreate}>Cancelar</button>
            <button type="submit" form="pd-create-user" className="pd-btn pd-btn-primary" disabled={guardando}>
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
            <AccessPicker
              modules={modules}
              paneles={paneles}
              seleccion={createForm.module_codes}
              onChange={(codes) => setCreateForm((p) => ({ ...p, module_codes: codes }))}
              rol={createForm.role}
              usuarios={users}
            />
          </div>
        </form>
      </Drawer>

      {/* ---- Gestionar usuario ---- */}
      <Drawer
        open={Boolean(gestion)}
        onClose={cerrarGestion}
        title={gestion ? nombreDe(gestion) : ""}
        subtitle={gestion ? `${gestion.email} · ${roleLabel(gestion.role_code)}` : ""}
        wide
        className="pd-drawer-usuario"
        footer={footerGestion}
      >
        {gestion && (
          <>
            <ViewTabs value={tab} onChange={(valor) => { setTab(valor); setError(""); }} options={TABS} />
            {error && <div className="alert alert-danger pd-user-tab-alert">{error}</div>}

            {tab === "accesos" && (
              <div className="pd-user-tab">
                <AccessPicker
                  key={gestion.id}
                  modules={modules}
                  paneles={paneles}
                  seleccion={editModules}
                  onChange={setEditModules}
                  rol={gestion.role_code}
                  original={gestion.modules}
                  usuarios={users}
                  excluirId={gestion.id}
                />
              </div>
            )}

            {tab === "datos" && (
              <div className="pd-user-tab pd-user-form-grid">
                <Field label="Correo">
                  <input className="form-control" value={gestion.email} disabled readOnly />
                </Field>
                <Field label="Nombre completo">
                  <input className="form-control" value={editDatos.full_name} onChange={(e) => setEditDatos((p) => ({ ...p, full_name: e.target.value }))} />
                </Field>
                <Field label="Rol">
                  <select className="form-select" value={editDatos.role} onChange={(e) => setEditDatos((p) => ({ ...p, role: e.target.value }))} disabled={esYo || gestion.role_code === "super_admin"}>
                    {rolesDatos.map((role) => (
                      <option key={role} value={role} disabled={!roleOptions.includes(role)}>{roleLabel(role)}</option>
                    ))}
                  </select>
                </Field>
                <p className="pd-user-tab-nota">
                  {esYo
                    ? "No puedes cambiar tu propio rol."
                    : "El rol define qué tan amplio es su acceso: administradores ven todo; coordinadores, supervisores y ejecutivos ven solo lo asignado en Accesos."}
                </p>
              </div>
            )}

            {tab === "seguridad" && (
              <div className="pd-user-tab">
                <dl className="pd-user-ficha">
                  <div><dt>Estado</dt><dd><span className={`pd-status ${estadoUsuario(gestion).cls}`}>{estadoUsuario(gestion).label}</span></dd></div>
                  <div><dt>Último ingreso</dt><dd>{gestion.last_login_at ? `${fechaHora(gestion.last_login_at)} (${haceCuanto(gestion.last_login_at).toLowerCase()})` : "Nunca ha ingresado"}</dd></div>
                  <div><dt>Creado</dt><dd>{fechaHora(gestion.created_at)}</dd></div>
                  <div><dt>Contraseña</dt><dd>{gestion.must_change_password ? "Temporal: debe cambiarla al entrar" : "Definida por el usuario"}</dd></div>
                </dl>

                <div className="pd-user-acciones">
                  <AccionSeguridad
                    icono="bi-envelope-paper"
                    titulo="Reenviar contraseña temporal"
                    detalle="Le deja la contraseña temporal y se la envía por correo; deberá cambiarla al entrar. Úsalo si la olvidó o nunca recibió el correo."
                    boton="Reenviar"
                    confirmar="Su contraseña actual dejará de funcionar. ¿Continuar?"
                    disabled={esYo}
                    motivo="Para tu propia contraseña usa Cambiar contraseña en el inicio."
                    onRun={() =>
                      guardar(
                        () => resetAdminUserPassword(gestion.id),
                        (r) => (r.email_sent ? `Se envió la contraseña temporal a ${gestion.email}.` : `Contraseña restablecida, pero el correo no se envió: ${r.email_error || "sin detalle"}. Compártela por otro medio.`)
                      )
                    }
                  />
                  {gestion.locked && (
                    <AccionSeguridad
                      icono="bi-unlock"
                      titulo="Desbloquear"
                      detalle="Quedó bloqueado por intentos fallidos de contraseña. Al desbloquearlo puede volver a intentar de inmediato."
                      boton="Desbloquear"
                      onRun={() => guardar(() => unlockAdminUser(gestion.id), `${nombreDe(gestion)} quedó desbloqueado.`)}
                    />
                  )}
                  <AccionSeguridad
                    icono={gestion.is_active ? "bi-person-x" : "bi-person-check"}
                    titulo={gestion.is_active ? "Desactivar usuario" : "Activar usuario"}
                    detalle={gestion.is_active ? "No podrá ingresar a la plataforma. Sus accesos se conservan por si se reactiva." : "Podrá volver a ingresar con sus accesos actuales."}
                    boton={gestion.is_active ? "Desactivar" : "Activar"}
                    confirmar={gestion.is_active ? `${nombreDe(gestion)} no podrá ingresar. ¿Continuar?` : null}
                    peligro={gestion.is_active}
                    disabled={esYo}
                    motivo="No puedes desactivar tu propio usuario."
                    onRun={() =>
                      guardar(() => updateAdminUserStatus(gestion.id, !gestion.is_active), `${nombreDe(gestion)} quedó ${gestion.is_active ? "desactivado" : "activado"}.`)
                    }
                  />
                </div>
              </div>
            )}
          </>
        )}
      </Drawer>

      {/* ---- Asignacion masiva ---- */}
      <Drawer
        open={showBulk}
        onClose={() => setShowBulk(false)}
        title={`Cambiar accesos de ${selectedIds.length} ${selectedIds.length === 1 ? "usuario" : "usuarios"}`}
        subtitle="Solo cambia lo que marques; el resto de los accesos de cada usuario queda igual."
        wide
        className="pd-drawer-usuario"
        footer={
          <>
            <button type="button" className="pd-btn pd-btn-ghost" onClick={() => setShowBulk(false)}>Cancelar</button>
            <button type="button" className="pd-btn pd-btn-primary" onClick={saveBulk} disabled={guardando || !bulkModules.length}>
              <i className="bi bi-check2" aria-hidden="true" /> {bulkMode === "add" ? "Agregar accesos" : "Quitar accesos"}
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
          <p className="pd-user-tab-nota">
            {bulkMode === "add"
              ? "Lo que marques se suma a los accesos de cada usuario."
              : "Lo que marques se quita. \"Todo el panel\" quita el panel completo y también sus módulos sueltos."}
          </p>
        </div>
        <AccessPicker modules={modules} paneles={paneles} seleccion={bulkModules} onChange={setBulkModules} bulk />
      </Drawer>
    </div>
  );
}
