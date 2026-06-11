import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { fetchItauCastigoFilters, fetchItauCastigoGeneral, fetchItauCastigoProducto } from "../api";


function formatMoney(value) {
  return new Intl.NumberFormat("es-CL", { maximumFractionDigits: 0 }).format(Number(value || 0));
}


function formatPct(value) {
  return `${(Number(value || 0) * 100).toFixed(2)}%`;
}


function formatDate(value) {
  if (!value) {
    return "";
  }
  const [year, month, day] = String(value).slice(0, 10).split("-");
  if (!year || !month || !day) {
    return value;
  }
  return `${day}-${month}-${year}`;
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


function dotClass(value, thresholds) {
  const num = Number(value || 0);
  if (num >= thresholds.p66) {
    return "gm-dot gm-dot-ok";
  }
  if (num >= thresholds.p33) {
    return "gm-dot gm-dot-warn";
  }
  return "gm-dot gm-dot-bad";
}


export default function ItauCastigoPage() {
  const [view, setView] = useState("general");
  const [filters, setFilters] = useState({ fecha_carga: "", ejecutivo: "" });
  const [options, setOptions] = useState({ fechas_carga: [], ejecutivos: [], productos: [] });
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(null);
  const [metadata, setMetadata] = useState({ fecha_carga: "", periodo: "" });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const { user, logout } = useAuth();
  
  useEffect(() => {
    async function loadFilters() {
      try {
        const data = await fetchItauCastigoFilters();
        setOptions(data);
        setFilters((prev) => ({ ...prev, fecha_carga: data.fechas_carga?.[0] || "" }));
      } catch (err) {
        setError(err.message);
      }
    }
    loadFilters();
  }, []);

  useEffect(() => {
    if (!filters.fecha_carga) {
      return;
    }

    async function loadData() {
      setLoading(true);
      setError("");
      try {
        const data = view === "general" ? await fetchItauCastigoGeneral(filters) : await fetchItauCastigoProducto(filters);
        setRows(data.rows || []);
        setTotal(data.total || null);
        setMetadata({ fecha_carga: data.fecha_carga || filters.fecha_carga, periodo: data.periodo || "" });
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

  const thresholds = useMemo(() => {
    const values = rows
      .map((row) => (view === "general" ? Number(row.cumplimiento || 0) : Math.max(Number(row.pct_recupero_phoenix || 0), Number(row.pct_recupero_phoenix_mcv || 0))))
      .filter((value) => Number.isFinite(value))
      .sort((a, b) => a - b);

    return {
      p33: percentile(values, 0.33),
      p66: percentile(values, 0.66),
    };
  }, [rows, view]);

  const generalMetas = useMemo(() => {
    const metas = new Map();
    rows.forEach((row) => {
      const cobrador = String(row.cobrador_vista || "Sin cobrador").trim();
      if (!metas.has(cobrador)) {
        metas.set(cobrador, {
          cobrador_vista: cobrador,
          meta_recupero: Number(row.meta_recupero || 0),
        });
      }
    });
    return Array.from(metas.values()).sort((a, b) => a.cobrador_vista.localeCompare(b.cobrador_vista));
  }, [rows]);

  function renderGeneralMetas() {
    if (view !== "general" || !generalMetas.length) {
      return null;
    }

    return (
      <div className="card shadow-sm mb-3 itau-meta-card">
        <div className="card-body py-2">
          <div className="itau-meta-title">Meta recuperación</div>
          <div className="table-responsive">
            <table className="table table-sm mb-0 itau-meta-table">
              <thead>
                <tr>
                  <th>Cobrador</th>
                  <th className="text-end">Meta Recupero</th>
                </tr>
              </thead>
              <tbody>
                {generalMetas.map((row) => (
                  <tr key={row.cobrador_vista}>
                    <td>{row.cobrador_vista}</td>
                    <td className="text-end">${formatMoney(row.meta_recupero)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    );
  }

  function renderGeneralTable() {
    return (
      <table className="table table-striped table-hover align-middle gm-data-table itau-castigo-table">
        <thead>
          <tr>
            <th>Ejecutivo</th>
            <th>Cobrador Vista</th>
            <th className="text-center">Total Deuda</th>
            <th className="text-center">Recupero Total</th>
            <th className="text-center">% Efectividad</th>
            <th className="text-center">Cumplimiento</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, idx) => (
            <tr key={`itau-general-${row.ejecutivo}-${idx}`}>
              <td>{row.ejecutivo}</td>
              <td>{row.cobrador_vista || "-"}</td>
              <td className="text-center">${formatMoney(row.deuda_total)}</td>
              <td className="text-center">${formatMoney(row.recupero_total)}</td>
              <td className="text-center">{formatPct(row.pct_efectividad)}</td>
              <td className="fw-semibold text-center">
                <span className={dotClass(row.cumplimiento, thresholds)} /> {formatPct(row.cumplimiento)}
              </td>
            </tr>
          ))}
          {total && (
            <tr className="fw-semibold itau-total-row">
              <td>{total.ejecutivo}</td>
              <td>{total.cobrador_vista || ""}</td>
              <td className="text-center">${formatMoney(total.deuda_total)}</td>
              <td className="text-center">${formatMoney(total.recupero_total)}</td>
              <td className="text-center">{formatPct(total.pct_efectividad)}</td>
              <td className="text-center">{formatPct(total.cumplimiento)}</td>
            </tr>
          )}
        </tbody>
      </table>
    );
  }

  function renderProductoTable() {
    return (
      <table className="table table-striped table-hover align-middle gm-data-table itau-castigo-table">
        <thead>
          <tr>
            <th rowSpan={2}>Ejecutivo</th>
            <th colSpan={3} className="text-center">Phoenix</th>
            <th colSpan={3} className="text-center">Phoenix MCV</th>
          </tr>
          <tr>
            <th className="text-center">Deuda</th>
            <th className="text-center">Recupero</th>
            <th className="text-center">% Recupero</th>
            <th className="text-center">Deuda</th>
            <th className="text-center">Recupero</th>
            <th className="text-center">% Recupero</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, idx) => (
            <tr key={`itau-producto-${row.ejecutivo}-${idx}`}>
              <td>{row.ejecutivo}</td>
              <td className="text-center">${formatMoney(row.deuda_phoenix)}</td>
              <td className="text-center">${formatMoney(row.recupero_phoenix)}</td>
              <td className="fw-semibold text-center">
                <span className={dotClass(row.pct_recupero_phoenix, thresholds)} /> {formatPct(row.pct_recupero_phoenix)}
              </td>
              <td className="text-center">${formatMoney(row.deuda_phoenix_mcv)}</td>
              <td className="text-center">${formatMoney(row.recupero_phoenix_mcv)}</td>
              <td className="fw-semibold text-center">
                <span className={dotClass(row.pct_recupero_phoenix_mcv, thresholds)} /> {formatPct(row.pct_recupero_phoenix_mcv)}
              </td>
            </tr>
          ))}
          {total && (
            <tr className="fw-semibold itau-total-row">
              <td>{total.ejecutivo}</td>
              <td className="text-center">${formatMoney(total.deuda_phoenix)}</td>
              <td className="text-center">${formatMoney(total.recupero_phoenix)}</td>
              <td className="text-center">{formatPct(total.pct_recupero_phoenix)}</td>
              <td className="text-center">${formatMoney(total.deuda_phoenix_mcv)}</td>
              <td className="text-center">${formatMoney(total.recupero_phoenix_mcv)}</td>
              <td className="text-center">{formatPct(total.pct_recupero_phoenix_mcv)}</td>
            </tr>
          )}
        </tbody>
      </table>
    );
  }

  return (
    <div className="container-fluid py-4 app-shell itau-castigo-page">
      <div className="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
        <div>
          <h1 className="h3 m-0">Itaú Castigo - Productividad</h1>
          <Link to="/productividad" className="small text-decoration-none">
            Volver al Home
          </Link>
        </div>
        <div className="btn-group">
          <button className={`btn btn-${view === "general" ? "warning" : "outline-warning"}`} onClick={() => setView("general")}>
            Vista General
          </button>
          <button className={`btn btn-${view === "producto" ? "warning" : "outline-warning"}`} onClick={() => setView("producto")}>
            Vista Producto
          </button>
          <button className="btn btn-outline-secondary" onClick={logout}>Cerrar sesion</button>
        </div>
      </div>

      <div className="card shadow-sm mb-3 itau-filter-card">
        <div className="card-body">
          <div className="row g-2 align-items-end">
            <div className="col-12 col-md-3">
              <label className="form-label">Fecha de carga</label>
              <select className="form-select" value={filters.fecha_carga} onChange={(e) => onFilter("fecha_carga", e.target.value)}>
                {options.fechas_carga.map((value) => (
                  <option key={value} value={value}>
                    {formatDate(value)}
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
            <div className="col-12 col-md-4 small text-muted">
              Base: {formatDate(metadata.fecha_carga || filters.fecha_carga) || "N/D"} | Mes metas/carterizado: {formatDate(metadata.periodo) || "N/D"}
            </div>
          </div>
        </div>
      </div>

      {error && <div className="alert alert-danger">{error}</div>}

      {!loading && renderGeneralMetas()}

      <div className="card shadow-sm">
        <div className="card-body table-responsive">
          {loading ? <div className="text-center py-4">Cargando...</div> : view === "general" ? renderGeneralTable() : renderProductoTable()}
        </div>
      </div>

      <div className="card shadow-sm mt-3 itau-legend-card">
        <div className="card-body py-2 small">
          <strong>Significado de colores:</strong>
          <span className="ms-3"><span className="gm-dot gm-dot-bad" /> Bajo</span>
          <span className="ms-3"><span className="gm-dot gm-dot-warn" /> Esperado</span>
          <span className="ms-3"><span className="gm-dot gm-dot-ok" /> Sobre lo esperado</span>
        </div>
      </div>
    </div>
  );
}
