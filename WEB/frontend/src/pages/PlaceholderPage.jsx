import { Link } from "react-router-dom";

export default function PlaceholderPage({ title, description }) {
  return (
    <div className="container py-5 app-shell">
      <div className="card shadow-sm">
        <div className="card-body p-4">
          <h1 className="h3 mb-2">{title}</h1>
          <p className="text-muted mb-4">{description}</p>
          <div className="alert alert-info mb-4">
            Este modulo quedo reservado para implementarlo en la siguiente etapa.
          </div>
          <Link to="/" className="btn btn-primary">Volver al Home</Link>
        </div>
      </div>
    </div>
  );
}
