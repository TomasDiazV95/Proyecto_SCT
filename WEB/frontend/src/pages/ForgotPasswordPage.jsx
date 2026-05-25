import { useState } from "react";
import { Link } from "react-router-dom";
import { authForgotPassword } from "../auth/apiAuth";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(e) {
    e.preventDefault();
    setLoading(true);
    setError("");
    setMessage("");
    try {
      await authForgotPassword(email);
      setMessage("Si el correo existe, se envio un enlace de recuperacion.");
    } catch (err) {
      setError(err.message || "No se pudo procesar la solicitud");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="container py-5" style={{ maxWidth: 420 }}>
      <div className="card shadow-sm">
        <div className="card-body">
          <h1 className="h4 mb-3">Recuperar contraseña</h1>
          <form onSubmit={onSubmit}>
            <label className="form-label">Correo corporativo</label>
            <input className="form-control mb-3" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
            {message && <div className="alert alert-success py-2">{message}</div>}
            {error && <div className="alert alert-danger py-2">{error}</div>}
            <button className="btn btn-primary w-100" disabled={loading}>
              {loading ? "Enviando..." : "Enviar enlace"}
            </button>
          </form>
          <div className="mt-3 text-center small">
            <Link to="/login">Volver a login</Link>
          </div>
        </div>
      </div>
    </div>
  );
}
