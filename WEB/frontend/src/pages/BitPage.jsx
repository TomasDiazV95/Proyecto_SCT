import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { fetchBitFilters, fetchBitGeneral, fetchBitTramos } from "../api";

function formatMoney(value) {
  return new Intl.NumberFormat("es-CL", { maximumFractionDigits: 0 }).format(Number(value || 0));
}

function formatPct(value) {
  return `${(Number(value || 0) * 100).toFixed(2)}%`;
}

function getContencionToneClass(value, tramo) {
  const pct = Number(value || 0) * 100;
  const tramoKey = String(tramo || "").trim();

  if (tramoKey === "30-89") {
    if (pct >= 71) return "gm-dot gm-dot-ok";
    if (pct >= 64) return "gm-dot gm-dot-warn";
    if (pct >= 57) return "gm-dot gm-dot-low";
    return "gm-dot gm-dot-bad";
  }
  if (tramoKey === "90+") {
    if (pct >= 15) return "gm-dot gm-dot-ok";
    if (pct >= 12) return "gm-dot gm-dot-warn";
    if (pct >= 9) return "gm-dot gm-dot-low";
    return "gm-dot gm-dot-bad";
  }

  if (pct >= 100) return "gm-dot gm-dot-ok";
  if (pct >= 90) return "gm-dot gm-dot-warn";
  return "gm-dot gm-dot-bad";
}

export default function BitPage() {
  const [view, setView] = useState("general");
  const [filters, setFilters] = useState({ periodo: "", ejecutivo: "", tramo: "" });
  const [options, setOptions] = useState({ periodos: [], ejecutivos: [], tramos: [] });
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(null);
  const [contencionFile, setContencionFile] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadFilters() {
      try {
        const data = await fetchBitFilters();
        setOptions(data);
        setFilters((prev) => ({ ...prev, periodo: data.periodos?.[0] || "" }));
      } catch (err) {
        setError(err.message);
      }
    }
    loadFilters();
  }, []);

  useEffect(() => {
    if (!filters.periodo) {
      return;
    }
    async function loadData() {
      setLoading(true);
      setError("");
      try {
        const data = view === "general" ? await fetchBitGeneral(filters) : await fetchBitTramos(filters);
        setRows(data.rows || []);
        setTotal(data.total || null);
        setContencionFile(data.contencion_file || "");
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, [view, filters]);

  function onFilter(name, value) {
    setFilters((prev) => ({ ...prev, [name]: value }));
  }

  return (
    <div className="container-fluid py-4 app-shell gm-page">
      <div className="d-flex justify-content-between align-items-center mb-3">
        <div>
          <h1 className="h3 m-0">BIT - Seguimiento</h1>
          <Link to="/" className="small text-decoration-none">
            Volver al Home
          </Link>
        </div>
        <div className="btn-group">
          <button className={`btn btn-${view === "general" ? "primary" : "outline-primary"}`} onClick={() => setView("general")}>
            Vista General
          </button>
          <button className={`btn btn-${view === "tramo" ? "primary" : "outline-primary"}`} onClick={() => setView("tramo")}>
            Vista Tramo
          </button>
        </div>
      </div>

      <div className="card shadow-sm mb-3">
        <div className="card-body">
          <div className="row g-2">
            <div className="col-12 col-md-2">
              <label className="form-label">Periodo</label>
              <select className="form-select" value={filters.periodo} onChange={(e) => onFilter("periodo", e.target.value)}>
                {options.periodos.map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
              </select>
            </div>
            <div className="col-12 col-md-3">
              <label className="form-label">Ejecutivo</label>
              <select className="form-select" value={filters.ejecutivo} onChange={(e) => onFilter("ejecutivo", e.target.value)}>
                <option value="">Todos</option>
                {options.ejecutivos.map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
              </select>
            </div>
            <div className="col-12 col-md-2">
              <label className="form-label">Tramo</label>
              <select className="form-select" value={filters.tramo} onChange={(e) => onFilter("tramo", e.target.value)}>
                <option value="">Todos</option>
                {options.tramos.map((v) => (
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
          ) : (
            <table className="table table-striped table-hover align-middle gm-data-table">
              <colgroup>
                {Array.from({ length: view === "general" ? 6 : 5 }).map((_, idx) => (
                  <col key={`bit-col-${idx}`} style={{ width: `${100 / (view === "general" ? 6 : 5)}%` }} />
                ))}
              </colgroup>
              <thead>
                <tr>
                  <th>{view === "general" ? "Ejecutivo" : "Tramo"}</th>
                  {view === "general" && <th className="text-center">Tramo</th>}
                  <th className="text-center">Mto Inicial</th>
                  <th className="text-center">Mto Contenido</th>
                  <th className="text-center">% Contiene</th>
                  <th className="text-center">% Cumplimiento meta</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, idx) => (
                  <tr key={`${view}-${idx}`}>
                    <td>{view === "general" ? row.ejecutivo : row.tramo}</td>
                    {view === "general" && <td className="text-center">{row.tramo}</td>}
                    <td className="text-center">${formatMoney(row.monto_inicial)}</td>
                    <td className="text-center">${formatMoney(row.monto_contenido)}</td>
                    <td className="text-center">{formatPct(row.pct_contiene ?? row.pct_contencion)}</td>
                    <td className="fw-semibold text-center bit-meta-cell">
                      <span className="bit-meta-indicator" role="presentation">
                        <span className={getContencionToneClass(row.pct_contiene ?? row.pct_contencion, row.tramo)} />
                        <span>{formatPct(row.pct_cumpl_meta)}</span>
                      </span>
                    </td>
                  </tr>
                ))}
                {total && (
                  <tr className="fw-semibold table-primary">
                    <td>{view === "general" ? total.ejecutivo : total.tramo}</td>
                    {view === "general" && <td className="text-center">{total.tramo || ""}</td>}
                    <td className="text-center">${formatMoney(total.monto_inicial)}</td>
                    <td className="text-center">${formatMoney(total.monto_contenido)}</td>
                    <td className="text-center">{formatPct(total.pct_contiene ?? total.pct_contencion)}</td>
                    <td className="fw-semibold text-center bit-meta-cell">
                      <span className="bit-meta-indicator bit-meta-indicator-total" role="presentation">
                        <span className="gm-dot" />
                        <span>{formatPct(total.pct_cumpl_meta)}</span>
                      </span>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          )}
        </div>
      </div>

      <div className="card shadow-sm mt-3">
        <div className="card-body py-2">
          <div className="small text-muted mb-1">Archivo: {contencionFile || "N/D"}</div>
          <div className="small">
            <strong>Significado de colores:</strong>
            <span className="ms-3"><span className="gm-dot gm-dot-bad" /> Muy bajo</span>
            <span className="ms-3"><span className="gm-dot gm-dot-low" /> Bajo</span>
            <span className="ms-3"><span className="gm-dot gm-dot-warn" /> Esperado</span>
            <span className="ms-3"><span className="gm-dot gm-dot-ok" /> Sobre lo esperado</span>
          </div>
        </div>
      </div>
    </div>
  );
}
