import { Link, Navigate } from "react-router-dom";
import { modulePanels } from "../app/moduleCatalog";
import { useAuth } from "../auth/AuthContext";
import { canAccessPanel, getVisibleModules } from "../auth/permissions";

export default function PanelPage({ panelCode, emptyTitle = "Modulo en preparacion", emptyDescription = "Este panel quedo reservado para una siguiente etapa." }) {
  const { user } = useAuth();
  const panel = modulePanels.find((item) => item.code === panelCode);

  if (!panel || !canAccessPanel(user, panel)) {
    return <Navigate to="/" replace />;
  }

  const modules = getVisibleModules(user, panel);

  return (
    <div className="container py-5 app-shell">
      <div className={`card shadow-sm module-panel module-panel-${panel.accent} mb-4`}>
        <div className="card-body p-4">
          <Link to="/" className="small text-decoration-none">Volver al Home</Link>
          <h1 className="h3 mt-2 mb-2">{panel.title}</h1>
          <p className="text-muted mb-0">{panel.description}</p>
        </div>
      </div>

      {modules.length ? (
        <div className="row g-3">
          {modules.map((module) => (
            <div className="col-12 col-md-6 col-xl-4" key={module.path}>
              <div className="card shadow-sm h-100 module-card">
                <div className="card-body d-flex flex-column">
                  <h2 className="h5">{module.title}</h2>
                  <p className="text-muted flex-grow-1">{module.description}</p>
                  <Link to={module.path} className={`btn btn-${panel.accent}`}>
                    {module.buttonLabel}
                  </Link>
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="card shadow-sm">
          <div className="card-body p-4">
            <h2 className="h5">{emptyTitle}</h2>
            <p className="text-muted mb-0">{emptyDescription}</p>
          </div>
        </div>
      )}
    </div>
  );
}
