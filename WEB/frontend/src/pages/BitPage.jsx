import { Fragment, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { fetchBitFilters, fetchBitGeneral, fetchBitTramos } from "../api";

function formatMoney(value) {
  return new Intl.NumberFormat("es-CL", { maximumFractionDigits: 0 }).format(Number(value || 0));
}

function formatPct(value) {
  return `${(Number(value || 0) * 100).toFixed(2)}%`;
}

const tramoOrder = {
  "30-90": 0,
  "90+": 1,
};

function percentil(sortedValues, p) {
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

function compareTramos(a, b) {
  const aKey = String(a || "").trim();
  const bKey = String(b || "").trim();
  const aOrder = tramoOrder[aKey] ?? 99;
  const bOrder = tramoOrder[bKey] ?? 99;
  if (aOrder !== bOrder) {
    return aOrder - bOrder;
  }
  return aKey.localeCompare(bKey);
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

  const generalGroups = useMemo(() => {
    const groups = new Map();
    rows.forEach((row) => {
      const tramo = String(row.tramo || "Sin tramo").trim();
      if (!groups.has(tramo)) {
        groups.set(tramo, []);
      }
      groups.get(tramo).push(row);
    });
    return Array.from(groups, ([tramo, groupRows]) => ({ tramo, rows: groupRows })).sort((a, b) => compareTramos(a.tramo, b.tramo));
  }, [rows]);

  const thresholdsByTramo = useMemo(() => {
    const out = {};
    generalGroups.forEach((group) => {
      const values = group.rows
        .map((row) => Number(row.pct_cumpl_meta || 0))
        .filter((value) => Number.isFinite(value))
        .sort((a, b) => a - b);
      out[group.tramo] = {
        p33: percentil(values, 0.33),
        p66: percentil(values, 0.66),
      };
    });
    return out;
  }, [generalGroups]);

  const tramoThresholds = useMemo(() => {
    const values = rows
      .map((row) => Number(row.pct_cumpl_meta || 0))
      .filter((value) => Number.isFinite(value))
      .sort((a, b) => a - b);
    return {
      p33: percentil(values, 0.33),
      p66: percentil(values, 0.66),
    };
  }, [rows]);

  const totalRow = useMemo(() => {
    if (!total) {
      return null;
    }
    const visibleCumplMeta = rows
      .map((row) => Number(row.pct_cumpl_meta))
      .filter((value) => Number.isFinite(value));
    const avgCumplMeta = visibleCumplMeta.length
      ? visibleCumplMeta.reduce((acc, value) => acc + value, 0) / visibleCumplMeta.length
      : Number(total.pct_cumpl_meta || 0);

    return {
      ...total,
      pct_cumpl_meta: avgCumplMeta,
    };
  }, [rows, total]);

  function rowThresholds(row) {
    if (view === "general") {
      const tramo = String(row.tramo || "Sin tramo").trim();
      return thresholdsByTramo[tramo] || { p33: 0, p66: 0 };
    }
    return tramoThresholds;
  }

  function renderDataRow(row, idx) {
    return (
      <tr key={`${view}-${row.tramo || "sin-tramo"}-${row.ejecutivo || row.tramo}-${idx}`}>
        <td>{view === "general" ? row.ejecutivo : row.tramo}</td>
        {view === "general" && <td className="text-center">{row.tramo}</td>}
        <td className="text-center">${formatMoney(row.monto_inicial)}</td>
        <td className="text-center">${formatMoney(row.monto_contenido)}</td>
        <td className="text-center">{formatPct(row.pct_contiene ?? row.pct_contencion)}</td>
        <td className="fw-semibold text-center bit-meta-cell">
          <span className="bit-meta-indicator" role="presentation">
            <span className={dotClassByThresholds(row.pct_cumpl_meta, rowThresholds(row))} />
            <span>{formatPct(row.pct_cumpl_meta)}</span>
          </span>
        </td>
      </tr>
    );
  }

  return (
    <div className="container-fluid py-4 app-shell gm-page">
      <div className="d-flex justify-content-between align-items-center mb-3">
        <div>
          <h1 className="h3 m-0">BIT - Seguimiento</h1>
          <Link to="/productividad" className="small text-decoration-none">
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
                {view === "general"
                  ? generalGroups.map((group) => (
                      <Fragment key={`bit-tramo-${group.tramo}`}>
                        <tr className="bit-tramo-separator">
                          <td colSpan={6}>Tramo {group.tramo}</td>
                        </tr>
                        {group.rows.map((row, idx) => renderDataRow(row, idx))}
                      </Fragment>
                    ))
                  : rows.map((row, idx) => renderDataRow(row, idx))}
                {totalRow && (
                  <tr className="fw-semibold table-primary">
                    <td>{view === "general" ? totalRow.ejecutivo : totalRow.tramo}</td>
                    {view === "general" && <td className="text-center">{totalRow.tramo || ""}</td>}
                    <td className="text-center">${formatMoney(totalRow.monto_inicial)}</td>
                    <td className="text-center">${formatMoney(totalRow.monto_contenido)}</td>
                    <td className="text-center">{formatPct(totalRow.pct_contiene ?? totalRow.pct_contencion)}</td>
                    <td className="fw-semibold text-center bit-meta-cell">
                      <span className="bit-meta-indicator bit-meta-indicator-total" role="presentation">
                        <span className="gm-dot" />
                        <span>{formatPct(totalRow.pct_cumpl_meta)}</span>
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
            <span className="ms-3"><span className="gm-dot gm-dot-bad" /> Bajo</span>
            <span className="ms-3"><span className="gm-dot gm-dot-warn" /> Esperado</span>
            <span className="ms-3"><span className="gm-dot gm-dot-ok" /> Sobre lo esperado</span>
          </div>
        </div>
      </div>
    </div>
  );
}
