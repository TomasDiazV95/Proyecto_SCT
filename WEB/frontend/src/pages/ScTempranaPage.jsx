import { Link } from "react-router-dom";

export default function ScTempranaPage() {
  return (
    <div className="container py-5">
      <h1 className="h3 mb-2">SC Temprana</h1>
      <p className="text-muted">Modulo en construccion. Aqui se conectara el ETL y dashboard de mora temprana.</p>
      <Link to="/" className="btn btn-outline-primary">
        Volver al Home
      </Link>
    </div>
  );
}
