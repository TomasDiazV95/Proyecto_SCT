import React from "react";
import { Link } from "react-router-dom";
import { modulePanels } from "../app/moduleCatalog";
import { useAuth } from "../auth/AuthContext";
import { canAccessPanel } from "../auth/permissions";

export default function HomePage() {
  const { user, logout } = useAuth();
  const visiblePanels = modulePanels.filter((panel) => canAccessPanel(user, panel));

  return (
    <div className="container py-5">
      <div className="d-flex flex-column flex-md-row justify-content-between align-items-md-center gap-3 mb-4">
        <div>
          <h1 className="h2 mb-1">Plataforma Operativa</h1>
          <p className="text-muted m-0">{user?.full_name} ({user?.role})</p>
        </div>
        <button className="btn btn-outline-secondary" onClick={logout}>Cerrar sesion</button>
      </div>

      <div className="row g-4">
        {visiblePanels.map((panel) => (
          <div className="col-12 col-md-6 col-xl-4" key={panel.code}>
            <Link to={panel.path} className="text-decoration-none text-reset">
              <section className={`card shadow-sm h-100 module-panel module-panel-${panel.accent} home-panel-card`}>
                <div className="card-body d-flex flex-column p-4">
                  <p className="text-uppercase small fw-semibold text-muted mb-2">{panel.code}</p>
                  <h2 className="h4 mb-2">{panel.title}</h2>
                  <p className="text-muted flex-grow-1">{panel.description}</p>
                  <span className={`btn btn-${panel.accent} align-self-start`}>Abrir panel</span>
                </div>
              </section>
            </Link>
          </div>
        ))}
      </div>

      {!visiblePanels.length && <div className="alert alert-warning mt-4">Tu usuario no tiene modulos asignados.</div>}
    </div>
  );
}
