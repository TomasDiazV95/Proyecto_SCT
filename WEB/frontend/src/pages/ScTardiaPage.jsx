import { useEffect, useMemo, useState } from "react";
import { fetchCycle, fetchFilters } from "../api";
import { EmptyRow, Field, FilterBar, LoadingState, PageHeader, SectionCard, StatusLegend } from "../components/productividad/ui";

const initialFilters = {
  periodo: "",
  zona: "",
  ejecutivo: "",
};

const blockOrder = ["C3", "SUSCEPTIBLE CV", "C5", "C6", "PRE CASTIGO", "F1", "F2", "F3", "F4", "TOTAL F1 - F4"];
const castigoBlocks = ["F1", "F2", "F3", "F4", "TOTAL F1 - F4"];

const blockMeta = {
  C3: { title: "C3", subtitle: "Contencion y normalizacion", icon: "bi-bullseye" },
  "SUSCEPTIBLE CV": { title: "Susceptible CV", subtitle: "Contencion convenio", icon: "bi-shield-check" },
  C5: { title: "C5", subtitle: "Contencion tramo 90-119", icon: "bi-layers" },
  C6: { title: "C6", subtitle: "Salidas convenio", icon: "bi-arrow-up-right-circle" },
  "PRE CASTIGO": { title: "Pre Castigo", subtitle: "Contencion susceptible castigo", icon: "bi-exclamation-diamond" },
  F1: { title: "F1", subtitle: "Recupero castigo", icon: "bi-cash-coin" },
  F2: { title: "F2", subtitle: "Recupero castigo", icon: "bi-cash-stack" },
  F3: { title: "F3", subtitle: "Recupero castigo", icon: "bi-currency-dollar" },
  F4: { title: "F4", subtitle: "Seguimiento castigo", icon: "bi-archive" },
  "TOTAL F1 - F4": { title: "Total F1 - F4", subtitle: "Castigo consolidado", icon: "bi-diagram-3" },
};

function num(value) {
  return Number(value || 0);
}

function safePct(numerator, denominator) {
  const den = num(denominator);
  if (!den) return 0;
  return (num(numerator) / den) * 100;
}

function capPct(value) {
  return Math.max(0, Math.min(130, num(value)));
}

function cappedPct(numerator, denominator) {
  return capPct(safePct(numerator, denominator));
}

function rowCompliance(row) {
  const cont = cappedPct(row.contenido, row.monto_meta_cont);
  const norm = cappedPct(row.normalizado, row.monto_meta_norm);
  if (row.bloque === "C3" && num(row.monto_meta_norm) > 0) {
    return capPct((cont * 0.4) + (norm * 0.6));
  }
  return capPct(cont);
}

function statusOf(value) {
  const pct = num(value);
  if (pct >= 100) return "success";
  if (pct >= 70) return "warning";
  if (pct === 0) return "neutral";
  return "danger";
}

function statusLabel(status) {
  if (status === "success") return "Sobre meta";
  if (status === "warning") return "En riesgo";
  if (status === "neutral") return "Sin avance";
  return "Bajo meta";
}

function metricClass(value) {
  const status = statusOf(value);
  return `pd-status pd-status-${status}`;
}

function formatPct(value, digits = 1) {
  return `${num(value).toLocaleString("es-CL", { minimumFractionDigits: digits, maximumFractionDigits: digits })}%`;
}

function formatMoney(value) {
  return `$${num(value).toLocaleString("es-CL", { maximumFractionDigits: 0 })}`;
}

function formatMoneyShort(value) {
  const amount = num(value);
  if (Math.abs(amount) >= 1000000) {
    return `$${(amount / 1000000).toLocaleString("es-CL", { maximumFractionDigits: 0 })} MM`;
  }
  return formatMoney(amount);
}

function sortBlocks(a, b) {
  const ai = blockOrder.indexOf(a);
  const bi = blockOrder.indexOf(b);
  return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi) || a.localeCompare(b);
}

export default function ScTardiaPage() {
  const [filters, setFilters] = useState(initialFilters);
  const [options, setOptions] = useState({ periodos: [], zonas: [], ejecutivos: [] });
  const [rows, setRows] = useState([]);
  const [selectedBlock, setSelectedBlock] = useState("C3");
  const [statusFilters, setStatusFilters] = useState({ success: true, warning: true, danger: true, neutral: true });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadFilters() {
      try {
        const data = await fetchFilters();
        setOptions({
          periodos: data.periodos || [],
          zonas: data.zonas || [],
          ejecutivos: data.ejecutivos || [],
        });
        setFilters((prev) => ({ ...prev, periodo: data.periodos?.[0] || "" }));
      } catch (err) {
        setError(err.message);
      }
    }
    loadFilters();
  }, []);

  useEffect(() => {
    async function loadData() {
      if (!filters.periodo) return;
      setLoading(true);
      setError("");
      try {
        const data = await fetchCycle(filters);
        setRows(data || []);
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

  function clearFilters() {
    setFilters((prev) => ({ ...prev, zona: "", ejecutivo: "" }));
    setStatusFilters({ success: true, warning: true, danger: true, neutral: true });
  }

  const allRows = rows || [];
  const availableBlocks = useMemo(() => {
    const blocks = Array.from(new Set(allRows.map((row) => row.bloque).filter(Boolean))).sort(sortBlocks);
    return blocks.length ? blocks : blockOrder;
  }, [allRows]);

  useEffect(() => {
    if (availableBlocks.length && !availableBlocks.includes(selectedBlock)) {
      setSelectedBlock(availableBlocks[0]);
    }
  }, [availableBlocks, selectedBlock]);

  const rowsWithMetrics = useMemo(
    () =>
      allRows.map((row) => {
        const cumplimiento = rowCompliance(row);
        return {
          ...row,
          pct_contencion: cappedPct(row.contenido, row.monto_meta_cont),
          pct_normalizacion: cappedPct(row.normalizado, row.monto_meta_norm),
          cumplimiento_operativo: cumplimiento,
          estado: statusOf(cumplimiento),
        };
      }),
    [allRows]
  );

  const visibleMetricRows = useMemo(() => rowsWithMetrics.filter((row) => statusFilters[row.estado]), [rowsWithMetrics, statusFilters]);

  const blockSummary = useMemo(() => {
    return availableBlocks.map((block) => {
      const blockRows = rowsWithMetrics.filter((row) => row.bloque === block);
      const deuda = blockRows.reduce((acc, row) => acc + num(row.deuda_asignada), 0);
      const meta = blockRows.reduce((acc, row) => acc + num(row.monto_meta_cont), 0);
      const contenido = blockRows.reduce((acc, row) => acc + num(row.contenido), 0);
      const cumplimiento = cappedPct(contenido, meta);
      return {
        block,
        rows: blockRows.length,
        deuda,
        meta,
        contenido,
        cumplimiento: capPct(cumplimiento),
        status: statusOf(cumplimiento),
      };
    });
  }, [availableBlocks, rowsWithMetrics]);

  const selectedBlockRows = rowsWithMetrics.filter((row) => row.bloque === selectedBlock);
  const showNormalizationColumns = selectedBlock === "C3";
  const selectedBlockSums = castigoBlocks.includes(selectedBlock) && selectedBlockRows.length
    ? selectedBlockRows.reduce(
        (acc, row) => ({
          deuda_asignada: acc.deuda_asignada + num(row.deuda_asignada),
          monto_meta_cont: acc.monto_meta_cont + num(row.monto_meta_cont),
          contenido: acc.contenido + num(row.contenido),
          cantidad_casos: acc.cantidad_casos + num(row.cantidad_casos),
        }),
        { deuda_asignada: 0, monto_meta_cont: 0, contenido: 0, cantidad_casos: 0 }
      )
    : null;
  // Total castigo: se suma primero y se divide despues (no es el promedio de los %).
  const selectedBlockTotal = selectedBlockSums
    ? { ...selectedBlockSums, pct_contencion: cappedPct(selectedBlockSums.contenido, selectedBlockSums.monto_meta_cont) }
    : null;
  const selectedMeta = blockMeta[selectedBlock] || { title: selectedBlock, subtitle: "Detalle de bloque", icon: "bi-layers" };

  return (
    <div className="pd-page">
      <PageHeader title="SC Tardía" subtitle="Seguimiento de metas y cumplimiento operativo por ejecutivo, ciclo y reporte." />

      <FilterBar
        actions={
          <button type="button" className="pd-btn pd-btn-ghost" onClick={clearFilters}>
            <i className="bi bi-x-circle" aria-hidden="true" /> Limpiar filtros
          </button>
        }
        note="La fecha seleccionada se usa como fecha de consulta de la sábana y define el mes de metas."
      >
        <Field label="Fecha consulta">
          <select className="form-select" value={filters.periodo} onChange={(e) => onChange("periodo", e.target.value)}>
            {options.periodos.map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
        </Field>
        <Field label="Zona">
          <select className="form-select" value={filters.zona} onChange={(e) => onChange("zona", e.target.value)}>
            <option value="">Todas las zonas</option>
            {options.zonas.map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
        </Field>
        <Field label="Ejecutivo">
          <select className="form-select" value={filters.ejecutivo} onChange={(e) => onChange("ejecutivo", e.target.value)}>
            <option value="">Todos los ejecutivos</option>
            {options.ejecutivos.map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
        </Field>
        <div className="pd-field pd-field-wide">
          <span className="pd-label">Estado de cumplimiento</span>
          <div className="pd-chip-group">
            {statusOptions.map(([key, label]) => (
              <button
                key={key}
                type="button"
                className="pd-chip"
                aria-pressed={statusFilters[key]}
                onClick={() => setStatusFilters((prev) => ({ ...prev, [key]: !prev[key] }))}
              >
                <span className={`pd-dot pd-dot-${key}`} />
                {label}
              </button>
            ))}
          </div>
        </div>
      </FilterBar>

      {error && <div className="alert alert-danger">{error}</div>}

      {loading ? (
        <div className="pd-card"><LoadingState /></div>
        <>
          <div className="pd-select-grid">
            {blockOrder.map((block) => {
              const summary = blockSummary.find((item) => item.block === block) || { block, cumplimiento: 0, deuda: 0, rows: 0, status: "neutral" };
              const meta = blockMeta[block] || { title: block, subtitle: "Detalle", icon: "bi-layers" };
              return (
                <button key={block} type="button" className={`pd-select-card${selectedBlock === block ? " active" : ""}`} aria-pressed={selectedBlock === block} onClick={() => setSelectedBlock(block)}>
                  <div className="pd-select-card-top">
                    <span className="pd-eyebrow"><i className={`bi ${meta.icon} me-1`} aria-hidden="true" />{block}</span>
                    <span className={`pd-status pd-status-${summary.status}`}>{formatPct(summary.cumplimiento)}</span>
                  </div>
                  <span className="pd-select-card-title">{meta.title}</span>
                  <span className="pd-small pd-muted">{meta.subtitle} · {formatMoneyShort(summary.deuda)} asignado</span>
                </button>
              );
            })}
          </div>

          <SectionCard
            title={selectedMeta.title}
            description={`Detalle del ciclo · ${selectedMeta.subtitle}`}
            actions={<span className="pd-pill"><i className="bi bi-calendar3" aria-hidden="true" />Fecha consulta: {filters.periodo}</span>}
            bodyClassName=""
            footer={<StatusLegend items={statusLegendItems} />}
          >
            <div className="pd-table-scroll">
              <table className="pd-table">
                <thead>
                  <tr>
                    <th>Ejecutivo</th>
                    <th className="pd-num">Deuda asignada</th>
                    <th className="pd-num">Meta cont.</th>
                    <th className="pd-num">Contenido</th>
                    <th className="pd-num">% Cont.</th>
                    {showNormalizationColumns && <th className="pd-num">Meta norm.</th>}
                    {showNormalizationColumns && <th className="pd-num">Normalizado</th>}
                    {showNormalizationColumns && <th className="pd-num">% Norm.</th>}
                    {showNormalizationColumns && <th className="pd-num pd-th-key">Cumplimiento</th>}
                    <th className="pd-num">Casos</th>
                  </tr>
                </thead>
                <tbody>
                  {selectedBlockRows.map((row, index) => (
                    <tr key={`${row.reporte}-${row.bloque}-${row.ejecutivo}-${index}`}>
                      <td className="pd-cell-strong">{row.ejecutivo}</td>
                      <td className="pd-num">{formatMoney(row.deuda_asignada)}</td>
                      <td className="pd-num">{formatMoney(row.monto_meta_cont)}</td>
                      <td className="pd-num">{formatMoney(row.contenido)}</td>
                      <td className="pd-num"><span className={metricClass(row.pct_contencion)}>{formatPct(row.pct_contencion)}</span></td>
                      {showNormalizationColumns && <td className="pd-num">{row.monto_meta_norm ? formatMoney(row.monto_meta_norm) : "-"}</td>}
                      {showNormalizationColumns && <td className="pd-num">{row.normalizado ? formatMoney(row.normalizado) : "-"}</td>}
                      {showNormalizationColumns && <td className="pd-num"><span className={metricClass(row.pct_normalizacion)}>{row.monto_meta_norm ? formatPct(row.pct_normalizacion) : "-"}</span></td>}
                      {showNormalizationColumns && <td className="pd-num"><span className={metricClass(row.cumplimiento_operativo)}>{formatPct(row.cumplimiento_operativo)}</span></td>}
                      <td className="pd-num">{num(row.cantidad_casos).toLocaleString("es-CL")}</td>
                    </tr>
                  ))}
                  {selectedBlockTotal && (
                    <tr className="pd-row-total">
                      <td>Total</td>
                      <td className="pd-num">{formatMoney(selectedBlockTotal.deuda_asignada)}</td>
                      <td className="pd-num">{formatMoney(selectedBlockTotal.monto_meta_cont)}</td>
                      <td className="pd-num">{formatMoney(selectedBlockTotal.contenido)}</td>
                      <td className="pd-num"><span className={metricClass(selectedBlockTotal.pct_contencion)}>{formatPct(selectedBlockTotal.pct_contencion)}</span></td>
                      <td className="pd-num">{selectedBlockTotal.cantidad_casos.toLocaleString("es-CL")}</td>
                    </tr>
                  )}
                  {!selectedBlockRows.length && <EmptyRow colSpan={showNormalizationColumns ? 10 : 6} />}
                </tbody>
              </table>
            </div>
          </SectionCard>
        </>
      )}
    </div>
  );
}

const statusOptions = [
  ["success", "Sobre meta"],
  ["warning", "En riesgo"],
  ["danger", "Bajo meta"],
  ["neutral", "Sin avance"],
];

/*
const statusLegendItems = [
  { status: "success", range: "≥ 100%", label: "Sobre meta" },
  { status: "warning", range: "70% – 99%", label: "En riesgo" },
  { status: "danger", range: "< 70%", label: "Bajo meta" },
  { status: "neutral", range: "0%", label: "Sin avance" },
];

      <div className="pd-small pd-muted mt-1">Meta: {formatMoneyShort(item.meta)} · Contenido: {formatMoneyShort(item.contenido)}</div>
    </div>
  );
}

*/


