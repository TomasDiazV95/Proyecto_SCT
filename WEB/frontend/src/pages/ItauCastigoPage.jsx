import { useEffect, useMemo, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { fetchItauCastigoFilters, fetchItauCastigoGeneral, fetchItauCastigoProducto } from "../api";
import { Field, FilterBar, LoadingState, PageHeader, SectionCard, StatusLegend, ViewTabs, relativeLegendItems } from "../components/productividad/ui";


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
    return "pd-status pd-status-success";
  }
  if (num >= thresholds.p33) {
    return "pd-status pd-status-warning";
  }
  return "pd-status pd-status-danger";
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
      <SectionCard title="Meta recuperación" className="pd-card-narrow" bodyClassName="">
        <div className="pd-table-scroll">
          <table className="pd-table pd-table-plain pd-table-compact pd-table-static">
            <thead>
              <tr>
                <th>Cobrador</th>
                <th className="pd-num">Meta Recupero</th>
              </tr>
            </thead>
            <tbody>
              {generalMetas.map((row) => (
                <tr key={row.cobrador_vista}>
                  <td>{row.cobrador_vista}</td>
                  <td className="pd-num">${formatMoney(row.meta_recupero)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SectionCard>
    );
  }

  function renderGeneralTable() {
    return (
      <table className="pd-table">
        <thead>
          <tr>
            <th>Ejecutivo</th>
            <th>Cobrador Vista</th>
            <th className="pd-num">Total Deuda</th>
            <th className="pd-num">Recupero Total</th>
            <th className="pd-num">% Efectividad</th>
            <th className="pd-num pd-th-key">Cumplimiento</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, idx) => (
            <tr key={`itau-general-${row.ejecutivo}-${idx}`}>
              <td>{row.ejecutivo}</td>
              <td>{row.cobrador_vista || "-"}</td>
              <td className="pd-num">${formatMoney(row.deuda_total)}</td>
              <td className="pd-num">${formatMoney(row.recupero_total)}</td>
              <td className="pd-num">{formatPct(row.pct_efectividad)}</td>
              <td className="pd-num">
                <span className={dotClass(row.cumplimiento, thresholds)}>{formatPct(row.cumplimiento)}</span>
              </td>
            </tr>
          ))}
          {total && (
            <tr className="pd-row-total">
              <td>{total.ejecutivo}</td>
              <td>{total.cobrador_vista || ""}</td>
              <td className="pd-num">${formatMoney(total.deuda_total)}</td>
              <td className="pd-num">${formatMoney(total.recupero_total)}</td>
              <td className="pd-num">{formatPct(total.pct_efectividad)}</td>
              <td className="pd-num">
                <span className="pd-status pd-status-none">{formatPct(total.cumplimiento)}</span>
              </td>
            </tr>
          )}
        </tbody>
      </table>
    );
  }

  function renderProductoTable() {
    return (
      <table className="pd-table">
        <thead>
          <tr>
            <th rowSpan={2}>Ejecutivo</th>
            <th colSpan={3} className="pd-th-group-1 pd-group-start">Phoenix</th>
            <th colSpan={3} className="pd-th-group-2 pd-group-start">Phoenix MCV</th>
          </tr>
          <tr>
            <th className="pd-num pd-th-sub-1 pd-group-start">Deuda</th>
            <th className="pd-num pd-th-sub-1">Recupero</th>
            <th className="pd-num pd-th-sub-1">% Recupero</th>
            <th className="pd-num pd-th-sub-2 pd-group-start">Deuda</th>
            <th className="pd-num pd-th-sub-2">Recupero</th>
            <th className="pd-num pd-th-sub-2">% Recupero</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, idx) => (
            <tr key={`itau-producto-${row.ejecutivo}-${idx}`}>
              <td>{row.ejecutivo}</td>
              <td className="pd-num pd-group-start">${formatMoney(row.deuda_phoenix)}</td>
              <td className="pd-num">${formatMoney(row.recupero_phoenix)}</td>
              <td className="pd-num">
                <span className={dotClass(row.pct_recupero_phoenix, thresholds)}>{formatPct(row.pct_recupero_phoenix)}</span>
              </td>
              <td className="pd-num pd-group-start">${formatMoney(row.deuda_phoenix_mcv)}</td>
              <td className="pd-num">${formatMoney(row.recupero_phoenix_mcv)}</td>
              <td className="pd-num">
                <span className={dotClass(row.pct_recupero_phoenix_mcv, thresholds)}>{formatPct(row.pct_recupero_phoenix_mcv)}</span>
              </td>
            </tr>
          ))}
          {total && (
            <tr className="pd-row-total">
              <td>{total.ejecutivo}</td>
              <td className="pd-num pd-group-start">${formatMoney(total.deuda_phoenix)}</td>
              <td className="pd-num">${formatMoney(total.recupero_phoenix)}</td>
              <td className="pd-num">
                <span className="pd-status pd-status-none">{formatPct(total.pct_recupero_phoenix)}</span>
              </td>
              <td className="pd-num pd-group-start">${formatMoney(total.deuda_phoenix_mcv)}</td>
              <td className="pd-num">${formatMoney(total.recupero_phoenix_mcv)}</td>
              <td className="pd-num">
                <span className="pd-status pd-status-none">{formatPct(total.pct_recupero_phoenix_mcv)}</span>
              </td>
            </tr>
          )}
        </tbody>
      </table>
    );
  }

  return (
    <div className="pd-page">
      <PageHeader
        title="Itaú Castigo"
        subtitle="Productividad y recupero de cartera castigada Itaú."
        actions={
          <button type="button" className="pd-btn pd-btn-ghost" onClick={logout}>
            <i className="bi bi-box-arrow-right" aria-hidden="true" /> Cerrar sesión
          </button>
        }
      />

      <FilterBar note={`Base: ${formatDate(metadata.fecha_carga || filters.fecha_carga) || "N/D"} · Mes metas/carterizado: ${formatDate(metadata.periodo) || "N/D"}`}>
        <Field label="Fecha de carga">
          <select className="form-select" value={filters.fecha_carga} onChange={(e) => onFilter("fecha_carga", e.target.value)}>
            {options.fechas_carga.map((value) => (
              <option key={value} value={value}>
                {formatDate(value)}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Ejecutivo">
          <select className="form-select" value={filters.ejecutivo} onChange={(e) => onFilter("ejecutivo", e.target.value)}>
            <option value="">Todos</option>
            {options.ejecutivos.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </Field>
      </FilterBar>

      {error && <div className="alert alert-danger">{error}</div>}

      {!loading && renderGeneralMetas()}

      <div className="pd-tabbed">
        <ViewTabs
          value={view}
          onChange={setView}
          options={[
            { value: "general", label: "Vista General" },
            { value: "producto", label: "Vista Producto" },
          ]}
        />
        <SectionCard bodyClassName="" footer={<StatusLegend items={relativeLegendItems} />}>
          {loading ? <LoadingState /> : <div className="pd-table-scroll">{view === "general" ? renderGeneralTable() : renderProductoTable()}</div>}
        </SectionCard>
      </div>
    </div>
  );
}
