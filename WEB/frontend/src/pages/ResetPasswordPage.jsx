import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { authResetPassword } from "../auth/apiAuth";

export default function ResetPasswordPage() {
  const [search] = useSearchParams();
  const token = useMemo(() => search.get("token") || "", [search]);
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
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
    <div className="container py-5" style={{ maxWidth: 460 }}>
      <div className="card shadow-sm">
        <div className="card-body">
          <h1 className="h4 mb-3">Nueva contraseña</h1>
          <form onSubmit={onSubmit}>
            <label className="form-label">Nueva contraseña</label>
            <input className="form-control mb-3" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
            <label className="form-label">Confirmar nueva contraseña</label>
            <input className="form-control mb-3" type="password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} required />
            {message && <div className="alert alert-success py-2">{message}</div>}
            {error && <div className="alert alert-danger py-2">{error}</div>}
            <button className="btn btn-primary w-100" disabled={loading}>
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
