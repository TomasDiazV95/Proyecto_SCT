import { useEffect, useMemo, useState } from "react";
import { fetchCycle, fetchFilters, fetchGeneral } from "./api";

const initialFilters = {
  periodo: "",
  zona: "",
  ejecutivo: "",
  ciclo: "",
};

const cycleBuckets = ["C3", "SUSCEPTIBLE CV", "C5", "C6", "PRE CASTIGO"];

function formatPct(value) {
  return `${Number(value || 0).toFixed(2)}%`;
}

function formatMoney(value) {
  return new Intl.NumberFormat("es-CL", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(Number(value || 0));
}

export default function App() {
  const [view, setView] = useState("general");
  const [filters, setFilters] = useState(initialFilters);
  const [options, setOptions] = useState({
    periodos: [],
    zonas: [],
    ejecutivos: [],
  });
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadFilters() {
      try {
        const data = await fetchFilters();
        setOptions(data);
        setFilters((prev) => ({
          ...prev,
          periodo: data.periodos?.[0] || "",
          ciclo: cycleBuckets[0],
        }));
      } catch (err) {
        setError(err.message);
      }
    }
    loadFilters();
  }, []);

  useEffect(() => {
    async function loadData() {
      setLoading(true);
      setError("");
      try {
        if (view === "general") {
          const data = await fetchGeneral(filters);
          setRows(data);
        } else {
          const data = await fetchCycle(filters);
          setRows(data);
        }
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }

    if (view === "ciclo" && !filters.ciclo) {
      return;
    }
    loadData();
  }, [view, filters]);

  const cycleColumns = useMemo(() => {
    const preferredOrder = cycleBuckets;
    const set = new Set();
    rows.forEach((row) => {
      if (row.ciclos) {
        Object.keys(row.ciclos).forEach((ciclo) => set.add(ciclo));
      }
    });

    const dynamic = Array.from(set);
    const extra = dynamic.filter((x) => !preferredOrder.includes(x)).sort();
    return [...preferredOrder, ...extra];
  }, [rows]);

  function onChange(name, value) {
    setFilters((prev) => ({ ...prev, [name]: value }));
  }

  return (
    <div className="container-fluid py-4 app-shell">
      <div className="d-flex justify-content-between align-items-center mb-3">
        <h1 className="h3 m-0">Productividad de Ejecutivos</h1>
        <div className="btn-group">
          <button
            className={`btn btn-${view === "general" ? "primary" : "outline-primary"}`}
            onClick={() => setView("general")}
          >
            Vista General
          </button>
          <button
            className={`btn btn-${view === "ciclo" ? "primary" : "outline-primary"}`}
            onClick={() => setView("ciclo")}
          >
            Vista Por Ciclo
          </button>
        </div>
      </div>

      <div className="card shadow-sm mb-3">
        <div className="card-body">
          <div className="row g-2">
            <div className="col-12 col-md-2">
              <label className="form-label">Periodo</label>
              <input
                type="date"
                className="form-control"
                value={filters.periodo}
                onChange={(e) => onChange("periodo", e.target.value)}
              />
            </div>
            <div className="col-12 col-md-2">
              <label className="form-label">Zona</label>
              <select className="form-select" value={filters.zona} onChange={(e) => onChange("zona", e.target.value)}>
                <option value="">Todas</option>
                {options.zonas.map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
              </select>
            </div>
            <div className="col-12 col-md-2">
              <label className="form-label">Ejecutivo</label>
              <select className="form-select" value={filters.ejecutivo} onChange={(e) => onChange("ejecutivo", e.target.value)}>
                <option value="">Todos</option>
                {options.ejecutivos.map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
              </select>
            </div>
            {view === "ciclo" && (
              <div className="col-12 col-md-2">
                <label className="form-label">Ciclo a mostrar</label>
                <select className="form-select" value={filters.ciclo} onChange={(e) => onChange("ciclo", e.target.value)}>
                  <option value="">Selecciona</option>
                  {cycleBuckets.map((v) => (
                    <option key={v} value={v}>
                      {v}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>
        </div>
      </div>

      {error && <div className="alert alert-danger">{error}</div>}

      <div className="card shadow-sm">
        <div className="card-body table-responsive">
          {loading ? (
            <div className="text-center py-4">Cargando...</div>
          ) : view === "general" ? (
            <table className="table table-striped table-hover align-middle">
              <thead>
                <tr>
                  <th>Ejecutivo</th>
                  <th>Zona</th>
                  <th>Casos Asignados</th>
                  <th>Deuda Asignada</th>
                  {cycleColumns.map((c) => (
                    <th key={c}>Cumpl. {c}</th>
                  ))}
                  <th>Cumplimiento Final</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.ejecutivo}>
                    <td>{row.ejecutivo}</td>
                    <td>{row.zona || "-"}</td>
                    <td>{row.casos_asignados}</td>
                    <td>{formatMoney(row.deuda_total)}</td>
                    {cycleColumns.map((c) => (
                      <td key={`${row.ejecutivo}-${c}`}>{formatPct(row.ciclos?.[c])}</td>
                    ))}
                    <td className="fw-semibold">{formatPct(row.cumplimiento_final)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <table className="table table-striped table-hover align-middle">
              <thead>
                <tr>
                  <th>Ejecutivo</th>
                  <th>Tramo</th>
                  <th>Deuda Asignada</th>
                  <th>Saldo Contenido</th>
                  <th>% Contenido</th>
                  <th>Saldo Normalizado</th>
                  <th>% Normalizado</th>
                  <th>Cumplimiento Final</th>
                  <th>Casos Asignados</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, idx) => (
                  <tr key={`${row.ejecutivo}-${row.tramo}-${idx}`}>
                    <td>{row.ejecutivo}</td>
                    <td>{row.tramo}</td>
                    <td>{formatMoney(row.deuda_asignada)}</td>
                    <td>{formatMoney(row.saldo_contenido)}</td>
                    <td>{formatPct(row.porcentaje_contenido)}</td>
                    <td>{formatMoney(row.saldo_normalizado)}</td>
                    <td>{formatPct(row.porcentaje_normalizado)}</td>
                    <td className="fw-semibold">{formatPct(row.cumplimiento_final)}</td>
                    <td>{row.casos_asignados}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
