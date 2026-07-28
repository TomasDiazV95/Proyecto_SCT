import { Link } from "react-router-dom";

export default function AdministrativasPage() {
  return (
    <div className="container py-5 app-shell">
      <div className="card shadow-sm module-panel module-panel-info mb-4">
        <div className="card-body p-4">
          <Link to="/" className="small text-decoration-none">Volver al Home</Link>
          <h1 className="h3 mt-2 mb-2">Panel de Administrativo</h1>
          <p className="text-muted mb-0">Formularios y procesos administrativos internos.</p>
        </div>
      </div>

      <div className="row g-3">
        <div className="col-12 col-md-6 col-xl-4">
          <div className="card shadow-sm h-100 module-card">
            <div className="card-body d-flex flex-column">
              <h2 className="h5">Itaú Vencida</h2>
              <p className="text-muted flex-grow-1">Vista administrativa para procesos asociados a Itaú.</p>
              <Link to="/administrativas/itau" className="btn btn-info">
                Abrir Itaú
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
