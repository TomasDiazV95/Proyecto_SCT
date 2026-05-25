import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

const modules = [
  {
    title: "SC Tardia",
    description: "Productividad y cumplimiento de cartera tardia.",
    path: "/sc-tardia",
    code: "sc-tardia",
    btn: "Ir a SC Tardia",
  },
  {
    title: "SC Temprana",
    description: "Modulo en construccion para mora temprana.",
    path: "/sc-temprana",
    code: "sc-temprana",
    btn: "Ir a SC Temprana",
  },
  {
    title: "GM",
    description: "Seguimiento y cumplimiento de GM.",
    path: "/gm",
    code: "gm",
    btn: "Ir a GM",
  },
  {
    title: "BIT",
    description: "Seguimiento y cumplimiento de BIT.",
    path: "/bit",
    code: "bit",
    btn: "Ir a BIT",
  },
  {
    title: "Porsche",
    description: "Seguimiento y cumplimiento de Porsche",
    path: "/porsche",
    code: "porsche",
    btn: "Ir a Porsche",
  },
  {
    title: "La Araucana",
    description: "Productividad La Araucana",
    path: "/la-araucana",
    code: "la-araucana",
    btn: "Ir a La Araucana",
  },
  {
    title: "STH",
    description: "KPI Hipotecario con 4 productos.",
    path: "/sth",
    code: "sth",
    btn: "Ir a STH",
  },
];

export default function HomePage() {
  const { user, logout } = useAuth();
  const isGlobal = ["super_admin", "admin", "coordinador"].includes(user?.role || "");
  const isAdminView = ["super_admin", "admin"].includes(user?.role || "");
  const allowed = isGlobal
    ? modules
    : modules.filter((module) => (user?.modules || []).includes(module.code));

  return (
    <div className="container py-5">
      <div className="d-flex justify-content-between align-items-center mb-4">
        <div>
          <h1 className="h2 mb-1">Plataforma de Productividad</h1>
          <p className="text-muted m-0">{user?.full_name} ({user?.role})</p>
        </div>
        <button className="btn btn-outline-secondary" onClick={logout}>Cerrar sesion</button>
      </div>

      <div className="row g-3">
        {isAdminView && (
          <div className="col-12 col-md-4">
            <div className="card shadow-sm h-100 border-primary">
              <div className="card-body d-flex flex-column">
                <h2 className="h5">Administrar usuarios</h2>
                <p className="text-muted flex-grow-1">Crear usuarios, asignar modulos y activar o desactivar cuentas.</p>
                <Link to="/admin/usuarios" className="btn btn-outline-primary">Ir a Administracion</Link>
              </div>
            </div>
          </div>
        )}
        {allowed.map((module) => (
          <div className="col-12 col-md-4" key={module.path}>
            <div className="card shadow-sm h-100">
              <div className="card-body d-flex flex-column">
                <h2 className="h5">{module.title}</h2>
                <p className="text-muted flex-grow-1">{module.description}</p>
                <Link to={module.path} className="btn btn-primary">
                  {module.btn}
                </Link>
              </div>
            </div>
          </div>
        ))}
      </div>
      {!allowed.length && <div className="alert alert-warning mt-4">Tu usuario no tiene modulos asignados.</div>}
    </div>
  );
}
