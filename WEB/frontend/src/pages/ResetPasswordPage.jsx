import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { authResetPassword } from "../auth/apiAuth";
import nexusLogo from "../assets/logo/Logo_Nexus.png";

export default function ResetPasswordPage() {
  const [search] = useSearchParams();
  const token = useMemo(() => search.get("token") || "", [search]);
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(e) {
    e.preventDefault();
    if (!token) {
      setError("Token faltante");
      return;
    }
    if (password !== confirmPassword) {
      setError("La confirmacion no coincide");
      return;
    }
    setLoading(true);
    setError("");
    setMessage("");
    try {
      await authResetPassword(token, password);
      setMessage("Contraseña actualizada correctamente. Ya puedes iniciar sesion.");
    } catch (err) {
      setError(err.message || "No se pudo restablecer la contraseña");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-form-panel">
      <div className="login-card">
        <div className="login-card-header">
          <img className="login-card-logo" src={nexusLogo} alt="Nexus" />
          <h1 className="h4 mb-3">Cambiar contraseña</h1>
          <form onSubmit={onSubmit} className="login-form">
            <label className="login-password">Nueva contraseña</label>
            <div className="login-input-shell login-password-shell">
                <span className="login-input-icon" aria-hidden="true">
                  <svg viewBox="0 0 24 24" focusable="false"><path d="M17 9h-1V7a4 4 0 0 0-8 0v2H7a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-8a2 2 0 0 0-2-2Zm-7-2a2 2 0 0 1 4 0v2h-4Zm3 9.73V18h-2v-1.27a2 2 0 1 1 2 0Z" /></svg>
                </span>
                <input className="login-password" type={showNewPassword ? "text" : "password"} value={password} onChange={(e) => setPassword(e.target.value)} required />
                <button
                  type="button"
                  className="login-password-toggle"
                  onClick={() => setShowNewPassword((prev) => !prev)}
                  aria-label={showNewPassword ? "Ocultar contraseña" : "Mostrar contraseña"}
                >
                  <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
                    {showNewPassword ? (
                      <path d="M3.28 2 2 3.27l3.02 3.02C3.25 7.46 1.89 9.11 1 12c1.73 5.62 6.33 7 11 7 1.74 0 3.43-.2 4.95-.86L20.73 22 22 20.73 3.28 2Zm8.65 14.5A4.5 4.5 0 0 1 7.5 12c0-.85.24-1.65.65-2.32l1.5 1.5A2.5 2.5 0 0 0 12.82 14.35l1.5 1.5c-.68.41-1.5.65-2.39.65ZM12 5c4.67 0 8.27 1.38 10 7-.45 1.45-1.13 2.62-2 3.55l-3.15-3.15A4.5 4.5 0 0 0 11.6 7.52L9.25 5.17C10.11 5.05 11.02 5 12 5Z" />
                    ) : (
                      <path d="M12 5c4.67 0 8.27 1.38 10 7-1.73 5.62-5.33 7-10 7S3.73 17.62 2 12c1.73-5.62 5.33-7 10-7Zm0 2C8.26 7 5.54 7.92 4.12 12 5.54 16.08 8.26 17 12 17s6.46-.92 7.88-5C18.46 7.92 15.74 7 12 7Zm0 2.5A2.5 2.5 0 1 1 12 14a2.5 2.5 0 0 1 0-5Z" />
                    )}
                  </svg>
                </button>
              </div>
            <label className="login-password">Confirmar nueva contraseña</label>
            <div className="login-input-shell login-password-shell">
                <span className="login-input-icon" aria-hidden="true">
                  <svg viewBox="0 0 24 24" focusable="false"><path d="M17 9h-1V7a4 4 0 0 0-8 0v2H7a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-8a2 2 0 0 0-2-2Zm-7-2a2 2 0 0 1 4 0v2h-4Zm3 9.73V18h-2v-1.27a2 2 0 1 1 2 0Z" /></svg>
                </span>
                <input className="login-password" type={showConfirmPassword ? "text" : "password"} value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} required />
                <button
                  type="button"
                  className="login-password-toggle"
                  onClick={() => setShowConfirmPassword((prev) => !prev)}
                  aria-label={showConfirmPassword ? "Ocultar contraseña" : "Mostrar contraseña"}
                >
                  <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
                    {showConfirmPassword ? (
                      <path d="M3.28 2 2 3.27l3.02 3.02C3.25 7.46 1.89 9.11 1 12c1.73 5.62 6.33 7 11 7 1.74 0 3.43-.2 4.95-.86L20.73 22 22 20.73 3.28 2Zm8.65 14.5A4.5 4.5 0 0 1 7.5 12c0-.85.24-1.65.65-2.32l1.5 1.5A2.5 2.5 0 0 0 12.82 14.35l1.5 1.5c-.68.41-1.5.65-2.39.65ZM12 5c4.67 0 8.27 1.38 10 7-.45 1.45-1.13 2.62-2 3.55l-3.15-3.15A4.5 4.5 0 0 0 11.6 7.52L9.25 5.17C10.11 5.05 11.02 5 12 5Z" />
                    ) : (
                      <path d="M12 5c4.67 0 8.27 1.38 10 7-1.73 5.62-5.33 7-10 7S3.73 17.62 2 12c1.73-5.62 5.33-7 10-7Zm0 2C8.26 7 5.54 7.92 4.12 12 5.54 16.08 8.26 17 12 17s6.46-.92 7.88-5C18.46 7.92 15.74 7 12 7Zm0 2.5A2.5 2.5 0 1 1 12 14a2.5 2.5 0 0 1 0-5Z" />
                    )}
                  </svg>
                </button>
              </div>
            {message && <div className="alert alert-success py-2">{message}</div>}
            {error && <div className="alert alert-danger py-2">{error}</div>}
            <button className="login-submit" disabled={loading}>
              {loading ? "Guardando..." : "Guardar"}
            </button>
          </form>
          <div className="mt-3 text-center small">
            <Link to="/login">Ir a login</Link>
          </div>
        </div>
      </div>
    </div>
  );
}
