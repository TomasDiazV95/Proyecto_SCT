import { useEffect, useState } from "react";
import { downloadEstrategiaItauCastigo, fetchEstrategiaItauCastigoPeriodos } from "../../api";
import { Field, FilterBar, PageHeader } from "../../components/productividad/ui";
import { saveDownload } from "../../utils/download";

const BREADCRUMB = [
  { label: "Inicio", to: "/" },
  { label: "Panel Estrategia de Asignación", to: "/estrategia-asignacion" },
];

// El periodo de la asignacion viene como YYYYMM.
function formatPeriodo(periodo) {
  if (!periodo) {
    return "";
  }
  const date = new Date(Number(String(periodo).slice(0, 4)), Number(String(periodo).slice(4)) - 1, 1);
  const text = new Intl.DateTimeFormat("es-CL", { month: "long", year: "numeric" }).format(date);
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export default function EstrategiaItauCastigoPage() {
  const [periodos, setPeriodos] = useState([]);
  const [limites, setLimites] = useState({ min: 2, max: 50 });
  const [periodo, setPeriodo] = useState("");
  const [ejecutivos, setEjecutivos] = useState("8");
  const [loadingPeriodos, setLoadingPeriodos] = useState(false);
  const [generando, setGenerando] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadPeriodos() {
      setLoadingPeriodos(true);
      setError("");
      try {
        const data = await fetchEstrategiaItauCastigoPeriodos();
        const lista = data.periodos || [];
        setPeriodos(lista);
        setPeriodo(lista[0] || "");
        setLimites({ min: data.min_ejecutivos || 2, max: data.max_ejecutivos || 50 });
      } catch (err) {
        setError(err.message || "No se pudieron cargar los periodos disponibles.");
      } finally {
        setLoadingPeriodos(false);
      }
    }

    loadPeriodos();
  }, []);

  const cantidad = Number(ejecutivos);
  const cantidadValida = Number.isInteger(cantidad) && cantidad >= limites.min && cantidad <= limites.max;

  async function onGenerar(event) {
    event.preventDefault();
    setGenerando(true);
    setError("");
    try {
      const file = await downloadEstrategiaItauCastigo(periodo, cantidad);
      saveDownload(file.blob, file.filename);
    } catch (err) {
      setError(err.message || "No se pudo generar la estrategia. Intenta de nuevo o elige otro periodo.");
    } finally {
      setGenerando(false);
    }
  }

  return (
    <div className="pd-page">
      <PageHeader
        title="Itaú Castigo"
        subtitle="Reparte la asignación Phoenix del mes entre los ejecutivos en igualdad de condiciones y la descarga en Excel."
        breadcrumb={BREADCRUMB}
      />

      {error && <div className="alert alert-danger">{error}</div>}

      <form onSubmit={onGenerar}>
        <FilterBar
          actions={
            <button type="submit" className="pd-btn pd-btn-primary" disabled={!periodo || !cantidadValida || loadingPeriodos || generando}>
              <i className="bi bi-download" aria-hidden="true" /> {generando ? "Generando..." : "Generar estrategia"}
            </button>
          }
          note={
            <>
              Cada ejecutivo queda con la misma cantidad de RUT y operaciones, el mismo saldo castigado y la misma mezcla de contacto
              titular de los últimos 6 meses, MOB y nota. Los RUT con saldo de $2.000.000 hacia abajo van en el Excel sin ejecutivo.
              {!cantidadValida && ` La cantidad de ejecutivos debe estar entre ${limites.min} y ${limites.max}.`}
            </>
          }
        >
          <Field label="Periodo">
            <select
              className="form-select"
              value={periodo}
              onChange={(event) => setPeriodo(event.target.value)}
              disabled={!periodos.length || loadingPeriodos || generando}
            >
              {!periodos.length && <option value="">{loadingPeriodos ? "Cargando periodos..." : "Sin periodos"}</option>}
              {periodos.map((item) => (
                <option key={item} value={item}>
                  {formatPeriodo(item)}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Cantidad de ejecutivos">
            <input
              type="number"
              className="form-control"
              min={limites.min}
              max={limites.max}
              step={1}
              value={ejecutivos}
              onChange={(event) => setEjecutivos(event.target.value)}
              disabled={generando}
            />
          </Field>
        </FilterBar>
      </form>
    </div>
  );
}
