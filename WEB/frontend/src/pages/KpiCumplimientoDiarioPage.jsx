import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { fetchKpiDiarioCycle, fetchKpiDiarioFilters, fetchKpiDiarioGeneral } from "../api";

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

function percentile(sortedValues, p) {
  if (!sortedValues.length) {
    return 0;
  }
  const idx = (sortedValues.length - 1) * p;
  const lower = Math.floor(idx);
  const upper = Math.ceil(idx);
  if (lower === upper) {
    return sortedValues[lower];
  }
  const weight = idx - lower;
  return sortedValues[lower] * (1 - weight) + sortedValues[upper] * weight;
}

function dotClassByThresholds(value, thresholds) {
  const n = Number(value || 0);
  if (n >= thresholds.p66) return "gm-dot gm-dot-ok";
  if (n >= thresholds.p33) return "gm-dot gm-dot-warn";
  return "gm-dot gm-dot-bad";
}

export default function KpiCumplimientoDiarioPage() {
  const [view, setView] = useState("general");
  const [filters, setFilters] = useState(initialFilters);
  const [options, setOptions] = useState({ periodos: [], zonas: [], ejecutivos: [] });
  const [generalRows, setGeneralRows] = useState([]);
  const [cycleRows, setCycleRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadFilters() {
      try {
        const data = await fetchKpiDiarioFilters();
        setOptions(data);
        setFilters((prev) => ({
          ...prev,
          periodo: data.periodos?.[0] || "",
        }));
      } catch (err) {
        setError(err.message);
      }
    }
    loadFilters();
  }, []);

  useEffect(() => {
    async function loadData() {
      if (!filters.periodo) {
        return;
      }

      setLoading(true);
      setError("");
      try {
        if (view === "general") {
          const data = await fetchKpiDiarioGeneral(filters);
          setGeneralRows(data);
        } else {
          const data = await fetchKpiDiarioCycle(filters);
          setCycleRows(data);
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
    const set = new Set();
    (generalRows || []).forEach((row) => {
      if (row.ciclos) {
        Object.keys(row.ciclos).forEach((ciclo) => set.add(ciclo));
      }
    });
    const dynamic = Array.from(set);
    const extra = dynamic.filter((x) => !cycleBuckets.includes(x)).sort();
    return [...cycleBuckets, ...extra];
  }, [generalRows]);

  const thresholds = useMemo(() => {
    const sourceRows = view === "general" ? generalRows : cycleRows;
    const values = sourceRows
      .map((row) => Number(row.cumplimiento_final || 0))
      .filter((v) => Number.isFinite(v))
      .sort((a, b) => a - b);

    return {
      p33: percentile(values, 0.33),
      p66: percentile(values, 0.66),
    };
  }, [generalRows, cycleRows, view]);

  const totalSummary = useMemo(() => {
    const sourceRows = view === "general" ? generalRows : cycleRows;
    const deuda = sourceRows.reduce((acc, row) => acc + Number(row.deuda_asignada || row.deuda_total || 0), 0);
    const casos = sourceRows.reduce((acc, row) => acc + Number(row.casos_asignados || 0), 0);
    const ponderado = sourceRows.reduce((acc, row) => acc + Number(row.cumplimiento_final || 0) * Number(row.deuda_asignada || row.deuda_total || 0), 0);
    return {
      deuda,
      casos,
      cumplimiento_final: deuda ? ponderado / deuda : 0,
    };
  }, [generalRows, cycleRows, view]);

  function onChange(name, value) {
    setFilters((prev) => ({ ...prev, [name]: value }));
  }

  return (
    <div className="container-fluid py-4 app-shell gm-page">
      <div className="d-flex justify-content-between align-items-center mb-3">
        <div>
          <h1 className="h3 m-0">KPI Cumplimiento diario</h1>
          <Link to="/productividad" className="small text-decoration-none">
            Volver al Home
          </Link>
        </div>
        <div className="btn-group">
          <button className={`btn btn-${view === "general" ? "primary" : "outline-primary"}`} onClick={() => setView("general")}>
            Vista General
          </button>
          <button className={`btn btn-${view === "ciclo" ? "primary" : "outline-primary"}`} onClick={() => setView("ciclo")}>
            Vista Por Ciclo
          </button>
        </div>
      </div>

      <div className="row g-3 mb-3">
        <div className="col-12 col-md-4">
          <div className="card shadow-sm h-100">
            <div className="card-body">
              <div className="text-uppercase small text-muted mb-1">Cumplimiento diario</div>
              <div className="h2 mb-0 text-success">{formatPct(totalSummary.cumplimiento_final)}</div>
              <div className="text-muted small">Ponderado sobre la deuda asignada del periodo seleccionado.</div>
            </div>
          </div>
        </div>
        <div className="col-12 col-md-4">
          <div className="card shadow-sm h-100">
            <div className="card-body">
              <div className="text-uppercase small text-muted mb-1">Deuda total</div>
              <div className="h2 mb-0">{formatMoney(totalSummary.deuda)}</div>
              <div className="text-muted small">Base del cálculo para el cumplimiento diario.</div>
            </div>
          </div>
        </div>
        <div className="col-12 col-md-4">
          <div className="card shadow-sm h-100">
            <div className="card-body">
              <div className="text-uppercase small text-muted mb-1">Casos asignados</div>
              <div className="h2 mb-0">{formatMoney(totalSummary.casos)}</div>
              <div className="text-muted small">Casos procesados en la foto del día.</div>
            </div>
          </div>
        </div>
      </div>

      <div className="card shadow-sm mb-3">
        <div className="card-body">
          <div className="row g-2">
            <div className="col-12 col-md-2">
              <label className="form-label">Periodo</label>
              <select className="form-select" value={filters.periodo} onChange={(e) => onChange("periodo", e.target.value)}>
                {options.periodos.map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
              </select>
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
            <div className="col-12 col-md-3">
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
                <label className="form-label">Ciclo</label>
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
                {generalRows.map((row) => (
                  <tr key={row.ejecutivo}>
                    <td>{row.ejecutivo}</td>
                    <td>{row.zona || "-"}</td>
                    <td>{row.casos_asignados}</td>
                    <td>{formatMoney(row.deuda_total)}</td>
                    {cycleColumns.map((c) => (
                      <td key={`${row.ejecutivo}-${c}`}>{formatPct(row.ciclos?.[c])}</td>
                    ))}
                    <td className="fw-semibold">
                      <span className={dotClassByThresholds(row.cumplimiento_final, thresholds)} /> {formatPct(row.cumplimiento_final)}
                    </td>
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
                {cycleRows.map((row, idx) => (
                  <tr key={`${row.ejecutivo}-${row.tramo}-${idx}`}>
                    <td>{row.ejecutivo}</td>
                    <td>{row.tramo}</td>
                    <td>{formatMoney(row.deuda_asignada)}</td>
                    <td>{formatMoney(row.saldo_contenido)}</td>
                    <td>{formatPct(row.porcentaje_contenido)}</td>
                    <td>{formatMoney(row.saldo_normalizado)}</td>
                    <td>{formatPct(row.porcentaje_normalizado)}</td>
                    <td className="fw-semibold">
                      <span className={dotClassByThresholds(row.cumplimiento_final, thresholds)} /> {formatPct(row.cumplimiento_final)}
                    </td>
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
