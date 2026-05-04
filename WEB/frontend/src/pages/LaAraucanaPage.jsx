import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { fetchLaAraucanaFilters, fetchLaAraucanaResumen } from "../api";

function formatMoney(value) {
  return new Intl.NumberFormat("es-CL", { maximumFractionDigits: 0 }).format(Number(value || 0));
}

function formatPct(value) {
  if (value === null || value === undefined) {
    return "";
  }
  return `${(Number(value || 0) * 100).toFixed(2)}%`;
}

export default function LaAraucanaPage() {
  const [filters, setFilters] = useState({ periodos: [], tipo_cartera: [] });
  const [selected, setSelected] = useState({ periodo: "", cartera_crm: 531, tipo_cartera: "", ejecutivo: "" });
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadFilters() {
      try {
        const data = await fetchLaAraucanaFilters();
        setFilters(data);
        const periodo = data.periodos?.[0] || "";
        setSelected((prev) => ({ ...prev, periodo }));
      } catch (err) {
        setError(err.message);
      }
    }
    loadFilters();
  }, []);

  useEffect(() => {
    if (!selected.periodo) {
      return;
    }
    async function loadResumen() {
      setLoading(true);
      setError("");
      try {
        const data = await fetchLaAraucanaResumen(selected);
        setRows(data.rows || []);
        setTotal(data.total || null);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }
    loadResumen();
  }, [selected]);

  function onFilter(name, value) {
    setSelected((prev) => ({ ...prev, [name]: value }));
  }

  return (
    <div className="container-fluid py-4 app-shell">
      <div className="d-flex justify-content-between align-items-center mb-3">
        <div>
          <h1 className="h3 m-0">Resumen Productividad - La Araucana</h1>
          <Link to="/" className="small text-decoration-none">
            Volver al Home
          </Link>
        </div>
      </div>

      <div className="card shadow-sm mb-3">
        <div className="card-body">
          <div className="row g-2">
            <div className="col-12 col-md-2">
              <label className="form-label">Periodo</label>
              <select className="form-select" value={selected.periodo} onChange={(e) => onFilter("periodo", e.target.value)}>
                {filters.periodos.map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
              </select>
            </div>
            <div className="col-12 col-md-2">
              <label className="form-label">Tipo cartera</label>
              <select className="form-select" value={selected.tipo_cartera} onChange={(e) => onFilter("tipo_cartera", e.target.value)}>
                <option value="">Todas</option>
                {filters.tipo_cartera.map((v) => (
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
            <table className="table table-striped table-hover align-middle">
              <colgroup>
                <col style={{ width: "20%" }} />
                <col style={{ width: "20%" }} />
                <col style={{ width: "20%" }} />
                <col style={{ width: "20%" }} />
                <col style={{ width: "20%" }} />
              </colgroup>
              <thead>
                <tr>
                  <th>Ejecutivo</th>
                  <th>Q Folios</th>
                  <th>Recupero</th>
                  <th>% Contacto Titular</th>
                  <th>% Aporte</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.ejecutivo}>
                    <td>{row.ejecutivo}</td>
                    <td>{formatMoney(row.q_folios)}</td>
                    <td>${formatMoney(row.recupero)}</td>
                    <td>{formatPct(row.pct_contacto_titular)}</td>
                    <td>{formatPct(row.pct_aporte)}</td>
                  </tr>
                ))}
                {total && (
                  <tr className="fw-semibold">
                    <td>{total.ejecutivo}</td>
                    <td>{formatMoney(total.q_folios)}</td>
                    <td>${formatMoney(total.recupero)}</td>
                    <td>{formatPct(total.pct_contacto_titular)}</td>
                    <td>{formatPct(total.pct_aporte)}</td>
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
