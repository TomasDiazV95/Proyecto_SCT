import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  downloadItauAsignacionVencida,
  downloadItauCuotasVencida,
  fetchItauAdministrativasPeriodos,
} from "../../api";

function formatPeriodo(periodo) {
  if (!periodo) {
    return "";
  }
  const [year, month] = String(periodo).split("-");
  const date = new Date(Number(year), Number(month) - 1, 1);
  return new Intl.DateTimeFormat("es-CL", { month: "long", year: "numeric" }).format(date);
}

function saveDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function DownloadCard({ title, description, periodos, value, onChange, loading, onDownload }) {
  return (
    <div className="card shadow-sm h-100 module-card">
      <div className="card-body d-flex flex-column p-4">
        <h2 className="h5 mb-2">{title}</h2>
        <p className="text-muted flex-grow-1">{description}</p>
        <label className="form-label">Periodo</label>
        <select className="form-select mb-3" value={value} onChange={(event) => onChange(event.target.value)} disabled={!periodos.length || loading}>
          {!periodos.length && <option value="">Sin periodos disponibles</option>}
          {periodos.map((periodo) => (
            <option key={periodo} value={periodo}>
              {formatPeriodo(periodo)}
            </option>
          ))}
        </select>
        <button className="btn btn-info" type="button" onClick={onDownload} disabled={!value || loading}>
          {loading ? "Descargando..." : "Descargar"}
        </button>
      </div>
    </div>
  );
}

export default function ItauAdministrativasPage() {
  const [periodos, setPeriodos] = useState({ cuotas: [], asignacion: [] });
  const [selectedCuotas, setSelectedCuotas] = useState("");
  const [selectedAsignacion, setSelectedAsignacion] = useState("");
  const [loading, setLoading] = useState({ periodos: false, cuotas: false, asignacion: false });
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadPeriodos() {
      setLoading((prev) => ({ ...prev, periodos: true }));
      setError("");
      try {
        const data = await fetchItauAdministrativasPeriodos();
        const cuotas = data.cuotas || [];
        const asignacion = data.asignacion || [];
        setPeriodos({ cuotas, asignacion });
        setSelectedCuotas(cuotas[0] || "");
        setSelectedAsignacion(asignacion[0] || "");
      } catch (err) {
        setError(err.message || "No se pudieron cargar los periodos");
      } finally {
        setLoading((prev) => ({ ...prev, periodos: false }));
      }
    }

    loadPeriodos();
  }, []);

  async function downloadCuotas() {
    setLoading((prev) => ({ ...prev, cuotas: true }));
    setError("");
    try {
      const file = await downloadItauCuotasVencida(selectedCuotas);
      saveDownload(file.blob, file.filename);
    } catch (err) {
      setError(err.message || "No se pudo descargar cuotas Itaú");
    } finally {
      setLoading((prev) => ({ ...prev, cuotas: false }));
    }
  }

  async function downloadAsignacion() {
    setLoading((prev) => ({ ...prev, asignacion: true }));
    setError("");
    try {
      const file = await downloadItauAsignacionVencida(selectedAsignacion);
      saveDownload(file.blob, file.filename);
    } catch (err) {
      setError(err.message || "No se pudo descargar asignacion Itaú");
    } finally {
      setLoading((prev) => ({ ...prev, asignacion: false }));
    }
  }

  return (
    <div className="container py-5 app-shell">
      <div className="card shadow-sm module-panel module-panel-info mb-4">
        <div className="card-body p-4">
          <Link to="/administrativas" className="small text-decoration-none">Volver a Administrativas</Link>
          <h1 className="h3 mt-2 mb-2">Itaú - Administrativo</h1>
          <p className="text-muted mb-0">Espacio preparado para implementar procesos administrativos de Itaú.</p>
        </div>
      </div>

      {error && <div className="alert alert-danger">{error}</div>}
      {loading.periodos && <div className="alert alert-info">Cargando periodos disponibles...</div>}

      <div className="row g-3">
        <div className="col-12 col-lg-6">
          <DownloadCard
            title="Cuotas Itaú Vencida"
            description="Descarga todas las cuotas enviadas por Itaú para el mes seleccionado, usando FechaDeProceso."
            periodos={periodos.cuotas}
            value={selectedCuotas}
            onChange={setSelectedCuotas}
            loading={loading.cuotas || loading.periodos}
            onDownload={downloadCuotas}
          />
        </div>
        <div className="col-12 col-lg-6">
          <DownloadCard
            title="Asignación Itaú Vencida"
            description="Descarga toda la asignación enviada por Itaú para el mes seleccionado, usando el periodo detectado en el nombre del archivo."
            periodos={periodos.asignacion}
            value={selectedAsignacion}
            onChange={setSelectedAsignacion}
            loading={loading.asignacion || loading.periodos}
            onDownload={downloadAsignacion}
          />
        </div>
      </div>
    </div>
  );
}
