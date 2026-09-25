import { useEffect, useMemo, useState } from "react";

import { fetchBitCastigoFilters, fetchBitCastigoGeneral } from "../api";
import { Field, FilterBar, LoadingState, PageHeader, SectionCard, StatusLegend, relativeLegendItems } from "../components/productividad/ui";


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
    return "pd-status pd-status-success";
  }
  if (num >= thresholds.p33) {
    return "pd-status pd-status-warning";
  }
  return "pd-status pd-status-danger";
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
    <div className="pd-page">
      <PageHeader title="BIT Castigo" subtitle="Seguimiento y cumplimiento de Banco Internacional, cartera castigo." />

      <FilterBar>
        <Field label="Periodo">
          <select className="form-select" value={filters.periodo} onChange={(e) => onFilter("periodo", e.target.value)}>
            {options.periodos.map((value) => (
              <option key={value} value={value}>
                {value}
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

      <SectionCard
        bodyClassName=""
        footer={
          <>
            <StatusLegend items={relativeLegendItems} />
            <span>Archivo: {contencionFile || "N/D"}</span>
          </>
        }
      >
        {loading ? (
          <LoadingState />
        ) : (
          <div className="pd-table-scroll">
            <table className="pd-table">
              <colgroup>
                {Array.from({ length: 4 }).map((_, idx) => (
                  <col key={`bit-castigo-col-${idx}`} style={{ width: "25%" }} />
                ))}
              </colgroup>
              <thead>
                <tr>
                  <th>Ejecutivo</th>
                  <th className="pd-num">Mto Inicial</th>
                  <th className="pd-num">Recupero</th>
                  <th className="pd-num pd-th-key">% Cumplimiento meta</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, idx) => (
                  <tr key={`bit-castigo-${row.ejecutivo}-${idx}`}>
                    <td>{row.ejecutivo}</td>
                    <td className="pd-num">${formatMoney(row.monto_inicial)}</td>
                    <td className="pd-num">${formatMoney(row.monto_contenido)}</td>
                    <td className="pd-num">
                      <span className={dotClassByThresholds(row.pct_cumpl_meta, thresholds)}>{formatPct(capCumplMeta(row.pct_cumpl_meta))}</span>
                    </td>
                  </tr>
                ))}
                {totalRow && (
                  <tr className="pd-row-total">
                    <td>{totalRow.ejecutivo}</td>
                    <td className="pd-num">${formatMoney(totalRow.monto_inicial)}</td>
                    <td className="pd-num">${formatMoney(totalRow.monto_contenido)}</td>
                    <td className="pd-num">
                      <span className="pd-status pd-status-none">{formatPct(totalRow.pct_cumpl_meta)}</span>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>
    </div>
  );
}
