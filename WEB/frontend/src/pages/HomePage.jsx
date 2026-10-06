import React from "react";
import { Link } from "react-router-dom";
import "@fontsource-variable/montserrat";
import nexusMark from "../assets/logo/Logo_N.png";
import { modulePanels } from "../app/moduleCatalog";
import { useAuth } from "../auth/AuthContext";
import { canAccessPanel, getVisibleModules } from "../auth/permissions";

// Color e icono de cada panel (segun el accent del catalogo). El color identifica al panel en su fila.
const PANEL_STYLE = {
  primary: { color: "#0f766e", icon: "bi-graph-up-arrow" },
  pink: { color: "#db2777", icon: "bi-speedometer2" },
  success: { color: "#16a34a", icon: "bi-telephone-outbound" },
  warning: { color: "#d97706", icon: "bi-receipt" },
  info: { color: "#0891b2", icon: "bi-folder2-open" },
  violet: { color: "#7c3aed", icon: "bi-diagram-3" },
  danger: { color: "#dc2626", icon: "bi-shield-lock" },
};

const ROLE_LABEL = {
  super_admin: "Super administrador",
  admin: "Administrador",
  coordinador: "Coordinador",
};

function greeting() {
  const hour = new Date().getHours();
  if (hour < 12) return "Buenos días";
  if (hour < 20) return "Buenas tardes";
  return "Buenas noches";
}

function todayLabel() {
  const text = new Intl.DateTimeFormat("es-CL", { weekday: "long", day: "numeric", month: "long", year: "numeric" }).format(new Date());
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function roleLabel(role) {
  if (!role) return "Usuario";
  return ROLE_LABEL[role] || role.charAt(0).toUpperCase() + role.slice(1);
}

function plural(count, singular, pluralForm) {
  return `${count} ${count === 1 ? singular : pluralForm}`;
}

export default function HomePage() {
  const { user, logout } = useAuth();
  const panels = modulePanels
    .filter((panel) => canAccessPanel(user, panel))
    .map((panel) => ({ ...panel, visibleModules: getVisibleModules(user, panel) }));
  const totalModules = panels.reduce((acc, panel) => acc + panel.visibleModules.length, 0);
  const firstName = String(user?.full_name || "").trim().split(/\s+/)[0];

  return (
    <div className="pd-home">
      <header className="pd-home-hero">
        <div className="pd-home-hero-inner">
          <div className="pd-home-brand">
            <span className="pd-home-mark">
              <img src={nexusMark} alt="Nexus" />
            </span>
            <nav className="pd-home-account" aria-label="Cuenta">
              <Link to="/change-password" className="pd-home-account-link">
                <i className="bi bi-key" aria-hidden="true" /> Cambiar contraseña
              </Link>
              <button type="button" className="pd-home-account-link" onClick={logout}>
                <i className="bi bi-box-arrow-right" aria-hidden="true" /> Cerrar sesión
              </button>
            </nav>
          </div>

          <h1 className="pd-home-title">
            {greeting()}
            {firstName ? `, ${firstName}` : ""}
          </h1>
          <p className="pd-home-meta">
            <span>{todayLabel()}</span>
            <span className="pd-home-role">{roleLabel(user?.role)}</span>
          </p>
          {panels.length > 0 && (
            <p className="pd-home-summary">
              Tienes {plural(panels.length, "panel", "paneles")} y {plural(totalModules, "módulo habilitado", "módulos habilitados")}.
            </p>
          )}
        </div>
      </header>

      <main className="pd-home-body">
        {panels.length ? (
          <section aria-labelledby="pd-home-panels-title">
            <div className="pd-home-section-head">
              <h2 id="pd-home-panels-title" className="pd-home-section-title">Paneles</h2>
              <p className="pd-home-section-hint">Abre un panel completo o entra directo a uno de sus módulos.</p>
            </div>

            <ul className="pd-home-index">
              {panels.map((panel) => {
                const style = PANEL_STYLE[panel.accent] || PANEL_STYLE.primary;
                return (
                  <li className="pd-home-row" style={{ "--accent": style.color }} key={panel.code}>
                    <Link to={panel.path} className="pd-home-row-head">
                      <i className={`bi ${style.icon} pd-home-row-icon`} aria-hidden="true" />
                      <span className="pd-home-row-text">
                        <span className="pd-home-row-name">{panel.title}</span>
                        <span className="pd-home-row-desc">{panel.description}</span>
                      </span>
                    </Link>
                    <div className="pd-home-row-modules">
                      {panel.visibleModules.length ? (
                        panel.visibleModules.map((module) => (
                          <Link to={module.path} className="pd-home-module" key={`${panel.code}-${module.path}`}>
                            {module.title}
                          </Link>
                        ))
                      ) : (
                        <span className="pd-home-row-empty">Aún no tiene módulos. Abre el panel para ver su estado.</span>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          </section>
        ) : (
          <div className="pd-home-empty">
            <h2 className="pd-home-section-title">Aún no tienes paneles asignados</h2>
            <p>Pide a un administrador que te habilite los módulos que necesitas y vuelve a iniciar sesión.</p>
          </div>
        )}
      </main>
    </div>
  );
}
