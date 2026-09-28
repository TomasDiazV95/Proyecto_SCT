import { Link, Navigate } from "react-router-dom";
import { modulePanels } from "../app/moduleCatalog";
import { useAuth } from "../auth/AuthContext";
import { canAccessPanel, getVisibleModules } from "../auth/permissions";
import { SectionCard } from "../components/productividad/ui";

export default function PanelPage({ panelCode, emptyTitle = "Modulo en preparacion", emptyDescription = "Este panel quedo reservado para una siguiente etapa." }) {
  const { user } = useAuth();
  const panel = modulePanels.find((item) => item.code === panelCode);

  if (!panel || !canAccessPanel(user, panel)) {
    return <Navigate to="/" replace />;
  }

  const modules = getVisibleModules(user, panel);

  return (
    <div className="pd-page">
      <header className="pd-header">
        <div>
          <nav className="pd-breadcrumb" aria-label="Ruta">
            <Link to="/">Inicio</Link>
            <span aria-hidden="true">/</span>
            <span>{panel.title}</span>
          </nav>
          <h1 className="pd-title">{panel.title}</h1>
          <p className="pd-subtitle">{panel.description}</p>
        </div>
      </header>

      {modules.length ? (
        <div className="pd-module-grid">
          {modules.map((module) => (
            <Link to={module.path} className="pd-card pd-module-card" key={module.path}>
              <h2 className="pd-section-title">{module.title}</h2>
              <p className="pd-section-desc">{module.description}</p>
              <span className="pd-module-link">
                {module.buttonLabel} <i className="bi bi-arrow-right" aria-hidden="true" />
              </span>
            </Link>
          ))}
        </div>
      ) : (
        <SectionCard title={emptyTitle}>
          <p className="pd-muted m-0">{emptyDescription}</p>
        </SectionCard>
      )}
    </div>
  );
}
