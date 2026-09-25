import { Fragment, useEffect, useMemo, useState } from "react";

import { fetchBitFilters, fetchBitGeneral, fetchBitTramos } from "../api";
import { Field, FilterBar, LoadingState, PageHeader, SectionCard, StatusLegend, ViewTabs, relativeLegendItems } from "../components/productividad/ui";

function formatMoney(value) {
  return new Intl.NumberFormat("es-CL", { maximumFractionDigits: 0 }).format(Number(value || 0));
}

function formatPct(value) {
  return `${(Number(value || 0) * 100).toFixed(2)}%`;
}

function capCumplMeta(value) {
  return Math.min(Number(value || 0), 1.3);
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
    return "pd-status pd-status-success";
  }
  if (num >= thresholds.p33) {
    return "pd-status pd-status-warning";
  }
  return "pd-status pd-status-danger";
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
        .map((row) => capCumplMeta(row.pct_cumpl_meta || 0))
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
        <td className={view === "general" ? "pd-cell-indent" : undefined}>{view === "general" ? row.ejecutivo : row.tramo}</td>
        {view === "general" && <td>{row.tramo}</td>}
        <td className="pd-num">${formatMoney(row.monto_inicial)}</td>
        <td className="pd-num">${formatMoney(row.monto_contenido)}</td>
        <td className="pd-num">{formatPct(row.pct_contiene ?? row.pct_contencion)}</td>
        <td className="pd-num">
          <span className={dotClassByThresholds(row.pct_cumpl_meta, rowThresholds(row))}>{formatPct(capCumplMeta(row.pct_cumpl_meta))}</span>
        </td>
      </tr>
    );
  }

  return (
    <div className="pd-page">
      <PageHeader title="BIT Vigente" subtitle="Seguimiento y cumplimiento de Banco Internacional, cartera vigente." />

      <FilterBar>
        <Field label="Periodo">
          <select className="form-select" value={filters.periodo} onChange={(e) => onFilter("periodo", e.target.value)}>
            {options.periodos.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Ejecutivo">
          <select className="form-select" value={filters.ejecutivo} onChange={(e) => onFilter("ejecutivo", e.target.value)}>
            <option value="">Todos</option>
            {options.ejecutivos.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Tramo">
          <select className="form-select" value={filters.tramo} onChange={(e) => onFilter("tramo", e.target.value)}>
            <option value="">Todos</option>
            {options.tramos.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </Field>
      </FilterBar>

      {error && <div className="alert alert-danger">{error}</div>}

      <div className="pd-tabbed">
        <ViewTabs
          value={view}
          onChange={setView}
          options={[
            { value: "general", label: "Vista General" },
            { value: "tramo", label: "Vista Tramo" },
          ]}
        />
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
                  {Array.from({ length: view === "general" ? 6 : 5 }).map((_, idx) => (
                    <col key={`bit-col-${idx}`} style={{ width: `${100 / (view === "general" ? 6 : 5)}%` }} />
                  ))}
                </colgroup>
                <thead>
                  <tr>
                    <th>{view === "general" ? "Ejecutivo" : "Tramo"}</th>
                    {view === "general" && <th>Tramo</th>}
                    <th className="pd-num">Mto Inicial</th>
                    <th className="pd-num">Mto Contenido</th>
                    <th className="pd-num">% Contiene</th>
                    <th className="pd-num pd-th-key">% Cumplimiento meta</th>
                  </tr>
                </thead>
                <tbody>
                  {view === "general"
                    ? generalGroups.map((group) => (
                        <Fragment key={`bit-tramo-${group.tramo}`}>
                          <tr className="pd-row-group">
                            <td colSpan={6}>Tramo {group.tramo}</td>
                          </tr>
                          {group.rows.map((row, idx) => renderDataRow(row, idx))}
                        </Fragment>
                      ))
                    : rows.map((row, idx) => renderDataRow(row, idx))}
                  {totalRow && (
                    <tr className="pd-row-total">
                      <td>{view === "general" ? totalRow.ejecutivo : totalRow.tramo}</td>
                      {view === "general" && <td>{totalRow.tramo || ""}</td>}
                      <td className="pd-num">${formatMoney(totalRow.monto_inicial)}</td>
                      <td className="pd-num">${formatMoney(totalRow.monto_contenido)}</td>
                      <td className="pd-num">{formatPct(totalRow.pct_contiene ?? totalRow.pct_contencion)}</td>
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
    </div>
  );
}
