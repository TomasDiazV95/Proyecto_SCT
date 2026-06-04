import { useState } from "react";
import { Link } from "react-router-dom";
import { authForgotPassword } from "../auth/apiAuth";
import nexusLogo from "../assets/logo/Logo_Nexus.png";

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
    <div className="login-form-panel">
      <div className="login-card">
        <div className="login-card-header">
          <img className="login-card-logo" src={nexusLogo} alt="Nexus" />
          <h1 className="h4 mb-3">Recuperar contraseña</h1>
          <form onSubmit={onSubmit} className="login-form">
            <label className="login-email">Correo corporativo</label>
            <div className="login-input-shell">
              <span className="login-input-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" focusable="false"><path d="M12 12a4 4 0 1 0-4-4 4 4 0 0 0 4 4Zm0 2c-4.42 0-8 2.24-8 5v1h16v-1c0-2.76-3.58-5-8-5Z" /></svg>
              </span>
              <input id="login-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Ingresa tu usuario" required />
            </div>            
            {message && <div className="alert alert-success py-2">{message}</div>}
            {error && <div className="alert alert-danger py-2">{error}</div>}
            <button className="login-submit" disabled={loading}>
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
