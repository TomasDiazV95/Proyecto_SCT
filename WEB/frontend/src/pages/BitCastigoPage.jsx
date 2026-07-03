import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { fetchBitCastigoFilters, fetchBitCastigoGeneral } from "../api";


function formatMoney(value) {
  return new Intl.NumberFormat("es-CL", { maximumFractionDigits: 0 }).format(Number(value || 0));
}


function formatPct(value) {
  return `${(Number(value || 0) * 100).toFixed(2)}%`;
}


function capCumplMeta(value) {
  return Math.min(Number(value || 0), 1.3);
}


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


export default function BitCastigoPage() {
  const [filters, setFilters] = useState({ periodo: "", ejecutivo: "" });
  const [options, setOptions] = useState({ periodos: [], ejecutivos: [] });
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(null);
  const [contencionFile, setContencionFile] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadFilters() {
      try {
        const data = await fetchBitCastigoFilters();
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
        const data = await fetchBitCastigoGeneral(filters);
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
  }, [filters]);

  function onFilter(name, value) {
    setFilters((prev) => ({ ...prev, [name]: value }));
  }

  const thresholds = useMemo(() => {
    const values = rows
      .map((row) => capCumplMeta(row.pct_cumpl_meta || 0))
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
      .map((row) => capCumplMeta(row.pct_cumpl_meta))
      .filter((value) => Number.isFinite(value));
    const avgCumplMeta = visibleCumplMeta.length
      ? visibleCumplMeta.reduce((acc, value) => acc + value, 0) / visibleCumplMeta.length
      : Number(total.pct_cumpl_meta || 0);

    return {
      ...total,
      pct_cumpl_meta: capCumplMeta(avgCumplMeta),
    };
  }, [rows, total]);

  return (
    <div className="container-fluid py-4 app-shell gm-page">
      <div className="d-flex justify-content-between align-items-center mb-3">
        <div>
          <h1 className="h3 m-0">BIT Castigo - Seguimiento</h1>
          <Link to="/productividad" className="small text-decoration-none">
            Volver al Home
          </Link>
        </div>
      </div>

      <div className="card shadow-sm mb-3">
        <div className="card-body">
          <div className="row g-2">
            <div className="col-12 col-md-2">
              <label className="form-label">Periodo</label>
              <select className="form-select" value={filters.periodo} onChange={(e) => onFilter("periodo", e.target.value)}>
                {options.periodos.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </div>
            <div className="col-12 col-md-3">
              <label className="form-label">Ejecutivo</label>
              <select className="form-select" value={filters.ejecutivo} onChange={(e) => onFilter("ejecutivo", e.target.value)}>
                <option value="">Todos</option>
                {options.ejecutivos.map((value) => (
                  <option key={value} value={value}>
                    {value}
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
                {Array.from({ length: 4 }).map((_, idx) => (
                  <col key={`bit-castigo-col-${idx}`} style={{ width: "25%" }} />
                ))}
              </colgroup>
              <thead>
                <tr>
                  <th>Ejecutivo</th>
                  <th className="text-center">Mto Inicial</th>
                  <th className="text-center">Recupero</th>
                  <th className="text-center">% Cumplimiento meta</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, idx) => (
                  <tr key={`bit-castigo-${row.ejecutivo}-${idx}`}>
                    <td>{row.ejecutivo}</td>
                    <td className="text-center">${formatMoney(row.monto_inicial)}</td>
                    <td className="text-center">${formatMoney(row.monto_contenido)}</td>
                    <td className="fw-semibold text-center bit-meta-cell">
                      <span className="bit-meta-indicator" role="presentation">
                        <span className={dotClassByThresholds(row.pct_cumpl_meta, thresholds)} />
                        <span>{formatPct(capCumplMeta(row.pct_cumpl_meta))}</span>
                      </span>
                    </td>
                  </tr>
                ))}
                {totalRow && (
                  <tr className="fw-semibold table-primary">
                    <td>{totalRow.ejecutivo}</td>
                    <td className="text-center">${formatMoney(totalRow.monto_inicial)}</td>
                    <td className="text-center">${formatMoney(totalRow.monto_contenido)}</td>
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
