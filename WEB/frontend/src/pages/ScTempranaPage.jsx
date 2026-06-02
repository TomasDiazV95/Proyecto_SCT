import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { fetchScTempranaCycle, fetchScTempranaFilters, fetchScTempranaGeneral } from "../api";

const initialFilters = {
  periodo: "",
  ejecutivo: "",
};

function formatPct(value) {
  return `${Number(value || 0).toFixed(2)}%`;
}

function formatMoney(value) {
  return `$${new Intl.NumberFormat("es-CL", { minimumFractionDigits: 0, maximumFractionDigits: 0 }).format(Number(value || 0))}`;
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
  const num = Number(value || 0);
  if (num >= thresholds.p66) {
    return "gm-dot gm-dot-ok";
  }
  if (num >= thresholds.p33) {
    return "gm-dot gm-dot-warn";
  }
  return "gm-dot gm-dot-bad";
}

export default function ScTempranaPage() {
  const [view, setView] = useState("general");
  const [filters, setFilters] = useState(initialFilters);
  const [options, setOptions] = useState({ periodos: [], ejecutivos: [] });
  const [generalRows, setGeneralRows] = useState([]);
  const [cycleRows, setCycleRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadFilters() {
      try {
        const data = await fetchScTempranaFilters();
        setOptions({
          periodos: data.periodos || [],
          ejecutivos: data.ejecutivos || [],
        });
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
        const [general, cycle] = await Promise.all([fetchScTempranaGeneral(filters), fetchScTempranaCycle(filters)]);
        setGeneralRows(general);
        setCycleRows(cycle);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, [filters]);

  function onChange(name, value) {
    setFilters((prev) => ({ ...prev, [name]: value }));
  }

  const cycleDataRows = useMemo(() => cycleRows.filter((row) => row.ejecutivo !== "Total"), [cycleRows]);
  const cycleTotalRow = useMemo(() => cycleRows.find((row) => row.ejecutivo === "Total") || null, [cycleRows]);

  const c1Thresholds = useMemo(() => {
    const values = cycleDataRows
      .map((row) => Number(row.c1_porc_aporte || 0))
      .filter((v) => Number.isFinite(v))
      .sort((a, b) => a - b);
    return {
      p33: percentile(values, 0.33),
      p66: percentile(values, 0.66),
    };
  }, [cycleDataRows]);

  const c2Thresholds = useMemo(() => {
    const values = cycleDataRows
      .map((row) => Number(row.c2_porc_aporte || 0))
      .filter((v) => Number.isFinite(v))
      .sort((a, b) => a - b);
    return {
      p33: percentile(values, 0.33),
      p66: percentile(values, 0.66),
    };
  }, [cycleDataRows]);

  return (
    <div className="container-fluid py-4 app-shell">
      <div className="d-flex justify-content-between align-items-center mb-3">
        <div>
          <h1 className="h3 m-0">SC Temprana - Productividad</h1>
          <Link to="/" className="small text-decoration-none">
            Volver al Home
          </Link>
        </div>
        <div className="btn-group">
          <button className={`btn btn-${view === "general" ? "primary" : "outline-primary"}`} onClick={() => setView("general")}>
            Vista General
          </button>
          <button className={`btn btn-${view === "ejecutivos" ? "primary" : "outline-primary"}`} onClick={() => setView("ejecutivos")}>
            Vista Ejecutivos
          </button>
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
          </div>
        </div>
      </div>

      {error && <div className="alert alert-danger">{error}</div>}

      <div className="card shadow-sm">
        <div className="card-body table-responsive">
          {loading ? (
            <div className="text-center py-4">Cargando...</div>
          ) : view === "general" ? (
            <div className="text-center py-4 text-muted">Sin informacion disponible para vista general.</div>
          ) : (
            <table className="table table-striped table-hover align-middle">
              <thead>
                <tr>
                  <th rowSpan={2}>Ejecutiva</th>
                  <th colSpan={4} className="text-center">
                    Tramo C1
                  </th>
                  <th colSpan={4} className="text-center">
                    Tramo C2
                  </th>
                </tr>
                <tr>
                  <th>Deuda Asignada</th>
                  <th>Monto Cont</th>
                  <th>% Cont</th>
                  <th>% cumplimiento</th>
                  <th>Deuda Asignada</th>
                  <th>Monto Cont</th>
                  <th>% Cont</th>
                  <th>% cumplimiento</th>
                </tr>
              </thead>
              <tbody>
                {cycleDataRows.map((row) => (
                  <tr key={row.ejecutivo}>
                    <td>{row.ejecutivo}</td>
                    <td>{formatMoney(row.c1_deuda_asignada)}</td>
                    <td>{formatMoney(row.c1_monto_cont)}</td>
                    <td>{formatPct(row.c1_porc_contenido)}</td>
                    <td className="fw-semibold">
                      <span className={dotClassByThresholds(row.c1_porc_aporte, c1Thresholds)} /> {formatPct(row.c1_porc_aporte)}
                    </td>
                    <td>{formatMoney(row.c2_deuda_asignada)}</td>
                    <td>{formatMoney(row.c2_monto_cont)}</td>
                    <td>{formatPct(row.c2_porc_contenido)}</td>
                    <td className="fw-semibold">
                      <span className={dotClassByThresholds(row.c2_porc_aporte, c2Thresholds)} /> {formatPct(row.c2_porc_aporte)}
                    </td>
                  </tr>
                ))}
                {cycleTotalRow && (
                  <tr className="table-primary fw-semibold">
                    <td>{cycleTotalRow.ejecutivo}</td>
                    <td>{formatMoney(cycleTotalRow.c1_deuda_asignada)}</td>
                    <td>{formatMoney(cycleTotalRow.c1_monto_cont)}</td>
                    <td>{formatPct(cycleTotalRow.c1_porc_contenido)}</td>
                    <td>{formatPct(cycleTotalRow.c1_porc_aporte)}</td>
                    <td>{formatMoney(cycleTotalRow.c2_deuda_asignada)}</td>
                    <td>{formatMoney(cycleTotalRow.c2_monto_cont)}</td>
                    <td>{formatPct(cycleTotalRow.c2_porc_contenido)}</td>
                    <td>{formatPct(cycleTotalRow.c2_porc_aporte)}</td>
                  </tr>
                )}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
