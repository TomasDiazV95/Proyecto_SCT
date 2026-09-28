import { useEffect, useState } from "react";
import {
  downloadItauAsignacionVencida,
  downloadItauCuotasPagadas,
  downloadItauCuotasVencida,
  fetchItauAdministrativasPeriodos,
} from "../../api";
import { PageHeader, SectionCard } from "../../components/productividad/ui";
import { saveDownload } from "../../utils/download";
import MediblesItauCard from "./MediblesItauCard";

const BREADCRUMB = [
  { label: "Inicio", to: "/" },
  { label: "Panel Administrativo", to: "/administrativas" },
];

function formatPeriodo(periodo) {
  if (!periodo) {
    return "";
  }
  const [year, month] = String(periodo).split("-");
  const date = new Date(Number(year), Number(month) - 1, 1);
  const text = new Intl.DateTimeFormat("es-CL", { month: "long", year: "numeric" }).format(date);
  return text.charAt(0).toUpperCase() + text.slice(1);
}

// Descargas disponibles: cada una usa su propia lista de periodos (clave en la respuesta del backend).
const DESCARGAS = [
  {
    key: "cuotas",
    title: "Cuotas",
    description: "Todas las cuotas que envió Itaú en el mes, según la fecha de proceso.",
    periodosKey: "cuotas",
    download: downloadItauCuotasVencida,
  },
  {
    key: "asignacion",
    title: "Asignación",
    description: "Toda la asignación que envió Itaú en el mes, según el periodo del nombre del archivo.",
    periodosKey: "asignacion",
    download: downloadItauAsignacionVencida,
  },
  {
    key: "cuotasPagadas",
    title: "Cuotas pagadas",
    description: "Consolidado del mes de cuotas estimadas como pagadas, comparando cortes consecutivos de cuotas.",
    periodosKey: "cuotas",
    download: downloadItauCuotasPagadas,
  },
];

export default function ItauAdministrativasPage() {
  const [periodos, setPeriodos] = useState({ cuotas: [], asignacion: [] });
  const [selected, setSelected] = useState({ cuotas: "", asignacion: "", cuotasPagadas: "" });
  const [loadingPeriodos, setLoadingPeriodos] = useState(false);
  const [downloading, setDownloading] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadPeriodos() {
      setLoadingPeriodos(true);
      setError("");
      try {
        const data = await fetchItauAdministrativasPeriodos();
        const cuotas = data.cuotas || [];
        const asignacion = data.asignacion || [];
        setPeriodos({ cuotas, asignacion });
        setSelected({ cuotas: cuotas[0] || "", asignacion: asignacion[0] || "", cuotasPagadas: cuotas[0] || "" });
      } catch (err) {
        setError(err.message || "No se pudieron cargar los periodos disponibles.");
      } finally {
        setLoadingPeriodos(false);
      }
    }

    loadPeriodos();
  }, []);

  async function onDownload(item) {
    setDownloading(item.key);
    setError("");
    try {
      const file = await item.download(selected[item.key]);
      saveDownload(file.blob, file.filename);
    } catch (err) {
      setError(err.message || `No se pudo descargar ${item.title.toLowerCase()}. Intenta de nuevo o elige otro periodo.`);
    } finally {
      setDownloading("");
    }
  }

  return (
    <div className="pd-page">
      <PageHeader
        title="Itaú Vencida"
        subtitle="Descarga los archivos que envía Itaú y define qué casos cuentan para el cumplimiento del mes."
        breadcrumb={BREADCRUMB}
      />

      {error && <div className="alert alert-danger">{error}</div>}

      <SectionCard title="Descargas" description="Elige el mes de cada archivo y descárgalo en Excel." bodyClassName="">
        <ul className="pd-download-list">
          {DESCARGAS.map((item) => {
            const opciones = periodos[item.periodosKey];
            const busy = downloading === item.key;
            return (
              <li className="pd-download-row" key={item.key}>
                <div className="pd-download-text">
                  <span className="pd-download-title">{item.title}</span>
                  <span className="pd-download-desc">{item.description}</span>
                </div>
                <label className="pd-download-periodo">
                  <span className="visually-hidden">Periodo de {item.title.toLowerCase()}</span>
                  <select
                    className="form-select"
                    value={selected[item.key]}
                    onChange={(event) => setSelected((prev) => ({ ...prev, [item.key]: event.target.value }))}
                    disabled={!opciones.length || loadingPeriodos || busy}
                  >
                    {!opciones.length && <option value="">{loadingPeriodos ? "Cargando periodos..." : "Sin periodos"}</option>}
                    {opciones.map((periodo) => (
                      <option key={periodo} value={periodo}>
                        {formatPeriodo(periodo)}
                      </option>
                    ))}
                  </select>
                </label>
                <button
                  type="button"
                  className="pd-btn pd-btn-primary"
                  onClick={() => onDownload(item)}
                  disabled={!selected[item.key] || loadingPeriodos || Boolean(downloading)}
                >
                  <i className="bi bi-download" aria-hidden="true" /> {busy ? "Descargando..." : "Descargar"}
                </button>
              </li>
            );
          })}
        </ul>
      </SectionCard>

      <MediblesItauCard />
    </div>
  );
}
