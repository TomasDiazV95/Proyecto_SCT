import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

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
    <div className="container py-5" style={{ maxWidth: 420 }}>
      <div className="card shadow-sm">
        <div className="card-body">
          <h1 className="h4 mb-3">Iniciar sesion</h1>
          <form onSubmit={onSubmit}>
            <label className="form-label">Correo corporativo</label>
            <input className="form-control mb-3" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />

            <label className="form-label">Contraseña</label>
            <input className="form-control mb-3" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />

            {error && <div className="alert alert-danger py-2">{error}</div>}
            <button className="btn btn-primary w-100" disabled={loading}>
              {loading ? "Entrando..." : "Entrar"}
            </button>
          </form>
          <div className="mt-3 text-center small">
            <Link to="/forgot-password">Olvide mi contraseña</Link>
          </div>
        </div>
      </div>
    </div>
  );
}
