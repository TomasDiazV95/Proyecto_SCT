import { Link } from "react-router-dom";

const modules = [
  {
    title: "SC Tardia",
    description: "Productividad y cumplimiento de cartera tardia.",
    path: "/sc-tardia",
    btn: "Ir a SC Tardia",
  },
  {
    title: "SC Temprana",
    description: "Modulo en construccion para mora temprana.",
    path: "/sc-temprana",
    btn: "Ir a SC Temprana",
  },
  {
    title: "GM",
    description: "Modulo en construccion para asignacion y pagos.",
    path: "/gm",
    btn: "Ir a GM",
  },
  {
    title: "Porsche",
    description: "Seguimiento y cumplimiento de Porsche",
    path: "/porsche",
    btn: "Ir a Porsche",
  },
  {
    title: "La Araucana",
    description: "Modulo en construccion para el negocio de La Araucana.",
    path: "/la-araucana",
    btn: "Ir a La Araucana",
  },
];

export default function HomePage() {
  return (
    <div className="container py-5">
      <div className="text-center mb-4">
        <h1 className="h2 mb-2">Plataforma de Productividad</h1>
        <p className="text-muted m-0">Selecciona el modulo que deseas revisar.</p>
      </div>

      <div className="row g-3">
        {modules.map((module) => (
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
    </div>
  );
}
