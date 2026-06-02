import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import nexusLogo from "../assets/logo/Logo_Nexus.png";
import nexusLogoWhite from "../assets/logo/Logo_Nexus_White.png";

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(e) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const user = await login(email, password);
      if (user.must_change_password) {
        navigate("/change-password", { replace: true });
        return;
      }
      const target = location.state?.from?.pathname || "/";
      navigate(target, { replace: true });
    } catch (err) {
      setError(err.message || "Error de autenticacion");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="login-page">
      <section className="login-brand-panel">
        <div className="login-brand-content">
          <img className="login-brand-logo" src={nexusLogoWhite} alt="Nexus" />

          <div className="login-hero-copy">
            <h1>
              <span>Conecta.</span>
              <span>Gestiona.</span>
              <span className="login-gradient-text">Impulsa.</span>
            </h1>
            {/* <p>Nexus integra procesos, personas y datos para una operacion mas inteligente y eficiente.</p> */}
          </div>

          <p className="login-copyright">© 2026 Nexus. Todos los derechos reservados.</p>
        </div>
      </section>

      <section className="login-form-panel">
        <div className="login-card">
          <div className="login-card-header">
            <img className="login-card-logo" src={nexusLogo} alt="Nexus" />
            <h2>Bienvenido de nuevo</h2>
            <p>Inicia sesion para continuar</p>
          </div>

          <form onSubmit={onSubmit} className="login-form">
            <div className="login-field-group">
              <label htmlFor="login-email">Usuario</label>
              <div className="login-input-shell">
                <span className="login-input-icon" aria-hidden="true">
                  <svg viewBox="0 0 24 24" focusable="false"><path d="M12 12a4 4 0 1 0-4-4 4 4 0 0 0 4 4Zm0 2c-4.42 0-8 2.24-8 5v1h16v-1c0-2.76-3.58-5-8-5Z" /></svg>
                </span>
                <input id="login-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Ingresa tu usuario" required />
              </div>
            </div>

            <div className="login-field-group">
              <label htmlFor="login-password">Contraseña</label>
              <div className="login-input-shell">
                <span className="login-input-icon" aria-hidden="true">
                  <svg viewBox="0 0 24 24" focusable="false"><path d="M17 9h-1V7a4 4 0 0 0-8 0v2H7a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-8a2 2 0 0 0-2-2Zm-7-2a2 2 0 0 1 4 0v2h-4Zm3 9.73V18h-2v-1.27a2 2 0 1 1 2 0Z" /></svg>
                </span>
                <input id="login-password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Ingresa tu contraseña" required />
              </div>
            </div>

            <div className="login-options-row">
              <label className="login-remember">
                <input type="checkbox" />
                <span>Recordarme</span>
              </label>
              <Link to="/forgot-password">¿Olvidaste tu contraseña?</Link>
            </div>

            {error && <div className="alert alert-danger py-2 mb-0">{error}</div>}

            <button className="login-submit" disabled={loading}>
              <span>{loading ? "Entrando..." : "Iniciar sesion"}</span>
              <span aria-hidden="true">→</span>
            </button>
          </form>
        </div>

{/*         <div className="login-social-note">
          <span />
          <p>o continua con</p>
          <span />
        </div>
        <div className="login-social-buttons" aria-hidden="true">
          <button type="button" tabIndex={-1}>M</button>
          <button type="button" tabIndex={-1}>G</button>
        </div> */}
      </section>
    </main>
  );
}
