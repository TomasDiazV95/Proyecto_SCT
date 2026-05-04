import { Link } from "react-router-dom";

export default function GmPage() {
  return (
    <div className="container py-5">
      <h1 className="h3 mb-2">GM</h1>
      <p className="text-muted">Cumplimiento de Porsche</p>
      <Link to="/" className="btn btn-outline-primary">
        Volver al Home
      </Link>
    </div>
  );
}
