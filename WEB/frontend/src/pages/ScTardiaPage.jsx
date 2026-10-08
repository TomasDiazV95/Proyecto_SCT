import { useEffect, useMemo, useState } from "react";
import { fetchCycle, fetchFilters, fetchGeneral, fetchScTardiaMetas } from "../api";
import { EmptyRow, Field, FilterBar, LoadingState, MetasBlock, MetasButton, MetasDrawer, PageHeader, SectionCard, StatusLegend, ViewTabs, cumplimientoLegendItems, cumplimientoStatus, phoenixGrupalAlFinal, exportFileName } from "../components/productividad/ui";

const initialFilters = {
  periodo: "",
  zona: "",
  ejecutivo: "",
};

// Altas cuantias: la meta mide C1 y C2 juntos, con contencion y normalizacion (como C3);
// por ciclo se muestran ademas C1 y C2 por separado.
const altasCuantiasBlock = "C1 - C2";
const normalizationBlocks = ["C1", "C2", altasCuantiasBlock, "C3"];
const blockOrder = ["C1", "C2", altasCuantiasBlock, "C3", "SUSCEPTIBLE CV", "C5", "C6", "PRE CASTIGO", "F1", "F2", "F3", "F4", "TOTAL F1 - F4"];
const generalMoraBlocks = [
  { block: "C3", label: "C3" },
  { block: "SUSCEPTIBLE CV", label: "Susc. CV" },
  { block: "C5", label: "C5" },
  { block: "C6", label: "C6" },
  { block: "PRE CASTIGO", label: "Pre Castigo" },
];
const NO_ROWS = [];
const castigoBlocks = ["F1", "F2", "F3", "F4", "TOTAL F1 - F4"];

const blockMeta = {
  C1: { title: "C1", subtitle: "Altas cuantias", icon: "bi-gem" },
  C2: { title: "C2", subtitle: "Altas cuantias", icon: "bi-gem" },
  [altasCuantiasBlock]: { title: "Total C1 - C2", subtitle: "Altas cuantias consolidado", icon: "bi-diagram-3" },
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

// Semaforo comun de cumplimiento: < 80% critico, 80% - 99,9% en seguimiento, >= 100% cumplido.
function statusOf(value) {
  return cumplimientoStatus(num(value));
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
  const [view, setView] = useState("general");
  const [filters, setFilters] = useState(initialFilters);
  const [options, setOptions] = useState({ periodos: [], zonas: [], ejecutivos: [] });
  // Cada vista trae filas distintas (por ejecutivo / por bloque): se guardan junto a la vista que las pidio.
  const [result, setResult] = useState({ view: "general", rows: [] });
  const [selectedBlock, setSelectedBlock] = useState("C3");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [metasOpen, setMetasOpen] = useState(false);
  const [metas, setMetas] = useState([]);

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

  // El filtro de ejecutivo ofrece solo los que aparecen en la tabla para la fecha y zona elegidas.
  useEffect(() => {
    if (!filters.periodo) {
      return;
    }
    fetchFilters(filters.periodo, filters.zona)
      .then((data) => {
        const disponibles = data.ejecutivos || [];
        setOptions((prev) => ({ ...prev, ejecutivos: disponibles }));
        setFilters((prev) => (prev.ejecutivo && !disponibles.includes(prev.ejecutivo) ? { ...prev, ejecutivo: "" } : prev));
      })
      .catch((err) => setError(err.message));
  }, [filters.periodo, filters.zona]);

  useEffect(() => {
    async function loadData() {
      if (!filters.periodo) return;
      setLoading(true);
      setError("");
      try {
        const data = view === "general" ? await fetchGeneral(filters) : await fetchCycle(filters);
        setResult({ view, rows: data || [] });
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, [filters, view]);

  // Las metas se cargan al abrir el panel, para el mes de la fecha consultada.
  useEffect(() => {
    if (!metasOpen || !filters.periodo) return;
    fetchScTardiaMetas(filters)
      .then(setMetas)
      .catch((err) => setError(err.message));
  }, [metasOpen, filters.periodo]);

  function renderMetasDrawer() {
    const tipos = Array.from(new Set(metas.map((meta) => meta.meta_tipo)));
    return (
      <MetasDrawer open={metasOpen} onClose={() => setMetasOpen(false)} wide subtitle={`Vigentes para ${filters.periodo ? filters.periodo.slice(0, 7) : "N/D"}`}>
        {tipos.length ? (
          <div className="iv-drawer-grid iv-drawer-grid-single">
            {tipos.map((tipo, idx) => {
              const items = metas.filter((meta) => meta.meta_tipo === tipo);
              const ponderador = items.find((meta) => meta.ponderador_nivel_1_pct !== null && meta.ponderador_nivel_1_pct !== undefined)?.ponderador_nivel_1_pct;
              return (
                <MetasBlock
                  key={tipo}
                  title={tipo || "Sin tipo"}
                  note={ponderador !== undefined ? `Pondera ${formatPct(ponderador, 0)}` : ""}
                  accent={idx % 2 === 0 ? "consumo" : "hipot"}
                >
                  <table className="pd-table pd-table-plain pd-table-compact pd-table-static">
                    <thead>
                      <tr>
                        <th>Variable</th>
                        <th className="pd-num">Meta</th>
                        <th className="pd-num">Pond. N2</th>
                        <th className="pd-num">Pond. N3</th>
                      </tr>
                    </thead>
                    <tbody>
                      {items.map((meta) => (
                        <tr key={meta.variable}>
                          <td>{meta.variable}</td>
                          <td className="pd-num pd-cell-strong">{meta.meta_valor === null ? "-" : formatPct(meta.meta_valor, 2)}</td>
                          <td className="pd-num">{meta.ponderador_nivel_2_pct === null ? "-" : formatPct(meta.ponderador_nivel_2_pct, 0)}</td>
                          <td className="pd-num">{meta.ponderador_nivel_3_pct === null ? "-" : formatPct(meta.ponderador_nivel_3_pct, 0)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </MetasBlock>
              );
            })}
          </div>
        ) : (
          <div className="alert alert-light border">No hay metas cargadas para este mes.</div>
        )}
      </MetasDrawer>
    );
  }

  function onChange(name, value) {
    setFilters((prev) => ({ ...prev, [name]: value }));
  }

  function clearFilters() {
    setFilters((prev) => ({ ...prev, zona: "", ejecutivo: "" }));
  }

  // El cumplimiento (por bloque y final) viene calculado del backend.
  const allRows = result.rows;
  const executiveRows = result.view === "general" ? allRows : NO_ROWS;
  const rowsWithMetrics = result.view === "ciclo" ? allRows : NO_ROWS;
  const availableBlocks = useMemo(() => {
    const blocks = Array.from(new Set(rowsWithMetrics.map((row) => row.bloque).filter(Boolean))).sort(sortBlocks);
    return blocks.length ? blocks : blockOrder;
  }, [rowsWithMetrics]);

  useEffect(() => {
    if (availableBlocks.length && !availableBlocks.includes(selectedBlock)) {
      setSelectedBlock(availableBlocks[0]);
    }
  }, [availableBlocks, selectedBlock]);

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
  const showNormalizationColumns = normalizationBlocks.includes(selectedBlock);
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
  // Ponderador nivel 1 (mora tardia vs castigo) desde la tabla de metas, para los encabezados.
  const pesosNivel1 = allRows[0]?.ponderadores_nivel_1 || {};
  const pesoMoraLabel = pesosNivel1.PCT !== undefined ? `pondera ${formatPct(pesosNivel1.PCT, 0)}` : "";
  const pesoCastigoLabel = pesosNivel1.STOCK !== undefined ? `pondera ${formatPct(pesosNivel1.STOCK, 0)}` : "";

  const viewTabs = (
    <ViewTabs
      value={view}
      onChange={setView}
      options={[
        { value: "general", label: "Vista general", icon: "bi-grid" },
        { value: "ciclo", label: "Por ciclo", icon: "bi-layers" },
      ]}
    />
  );

  function renderGeneralTable() {
    return (
      <table className="pd-table">
        <thead>
          <tr>
            <th rowSpan={2}>Ejecutivo</th>
            <th className="pd-th-group-2 pd-group-start">Altas Cuantías</th>
            <th colSpan={generalMoraBlocks.length} className="pd-th-group-1 pd-group-start">
              Mora Tardía <span className="pd-th-note">{pesoMoraLabel}</span>
            </th>
            <th className="pd-th-group-2 pd-group-start">
              Castigo <span className="pd-th-note">{pesoCastigoLabel}</span>
            </th>
            <th rowSpan={2} className="pd-num pd-th-key pd-group-start">Cumplimiento Final</th>
          </tr>
          <tr>
            <th className="pd-num pd-th-sub-2 pd-group-start">C1 - C2</th>
            {generalMoraBlocks.map(({ block, label }, idx) => (
              <th key={block} className={`pd-num pd-th-sub-1${idx === 0 ? " pd-group-start" : ""}`}>{label}</th>
            ))}
            <th className="pd-num pd-th-sub-2 pd-group-start">Total F1 - F3</th>
          </tr>
        </thead>
        <tbody>
          {phoenixGrupalAlFinal(executiveRows).map((row) => (
            <tr key={row.ejecutivo}>
              <td className="pd-cell-ejecutivo">{row.ejecutivo}</td>
              <td className="pd-num pd-group-start">
                {row.bloques[altasCuantiasBlock] === undefined ? (
                  <span className="pd-cell-muted">—</span>
                ) : (
                  <span className={metricClass(row.bloques[altasCuantiasBlock])}>{formatPct(row.bloques[altasCuantiasBlock], 0)}</span>
                )}
              </td>
              {generalMoraBlocks.map(({ block }, idx) => (
                <td key={`${row.ejecutivo}-${block}`} className={`pd-num${idx === 0 ? " pd-group-start" : ""}`}>
                  {row.bloques[block] === undefined ? (
                    <span className="pd-cell-muted">—</span>
                  ) : (
                    <span className={metricClass(row.bloques[block])}>{formatPct(row.bloques[block], 0)}</span>
                  )}
                </td>
              ))}
              <td className="pd-num pd-group-start">
                {row.bloques["TOTAL F1 - F4"] === undefined ? (
                  <span className="pd-cell-muted">—</span>
                ) : (
                  <span className={metricClass(row.bloques["TOTAL F1 - F4"])}>{formatPct(row.bloques["TOTAL F1 - F4"], 0)}</span>
                )}
              </td>
              <td className="pd-num pd-group-start">
                <span className={metricClass(row.cumplimiento_operativo)}>{formatPct(row.cumplimiento_operativo, 0)}</span>
              </td>
            </tr>
          ))}
          {!executiveRows.length && <EmptyRow colSpan={generalMoraBlocks.length + 4} />}
        </tbody>
      </table>
    );
  }

  const selectedMeta = blockMeta[selectedBlock] || { title: selectedBlock, subtitle: "Detalle de bloque", icon: "bi-layers" };

  return (
    <div className="pd-page">
      <PageHeader title="Santander Consumer Tardía" subtitle="Seguimiento de metas y cumplimiento operativo por ejecutivo, ciclo y reporte." />

      <FilterBar
        actions={
          <>
            <button type="button" className="pd-btn pd-btn-ghost" onClick={clearFilters}>
              <i className="bi bi-x-circle" aria-hidden="true" /> Limpiar filtros
            </button>
            <MetasButton onClick={() => setMetasOpen(true)} />
          </>
        }
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
            {options.ejecutivos.map((value) => <option key={value} value={value}>{String(value).toUpperCase()}</option>)}
          </select>
        </Field>
      </FilterBar>

      {error && <div className="alert alert-danger">{error}</div>}

      {renderMetasDrawer()}

      {view === "general" ? (
        <div className="pd-tabbed">
          {viewTabs}
          <SectionCard exportName={exportFileName("SC-Tardia", "general", filters.periodo)} bodyClassName="" footer={<StatusLegend items={cumplimientoLegendItems} />}>
            {loading ? <LoadingState /> : <div className="pd-table-scroll">{renderGeneralTable()}</div>}
          </SectionCard>
        </div>
      ) : loading ? (
        <>
          {viewTabs}
          <div className="pd-card"><LoadingState /></div>
        </>
      ) : (
        <>
          {viewTabs}
          <div className="pd-select-grid">
            {blockOrder.map((block) => {
              const summary = blockSummary.find((item) => item.block === block) || { block, cumplimiento: 0, deuda: 0, rows: 0, status: statusOf(0) };
              const meta = blockMeta[block] || { title: block, subtitle: "Detalle", icon: "bi-layers" };
              return (
                <button key={block} type="button" className={`pd-select-card${selectedBlock === block ? " active" : ""}`} aria-pressed={selectedBlock === block} onClick={() => setSelectedBlock(block)}>
                  <div className="pd-select-card-top">
                    <span className="pd-eyebrow"><i className={`bi ${meta.icon} me-1`} aria-hidden="true" />{block}</span>
                    <span className={`pd-status pd-status-${summary.status}`}>{formatPct(summary.cumplimiento, 0)}</span>
                  </div>
                  <span className="pd-select-card-title">{meta.title}</span>
                  <span className="pd-small pd-muted">{meta.subtitle} · {formatMoneyShort(summary.deuda)} asignado</span>
                </button>
              );
            })}
          </div>

          <SectionCard
            exportName={exportFileName("SC-Tardia", selectedBlock, filters.periodo)}
            title={selectedMeta.title}
            description={`${view === "general" ? "Resumen general" : "Detalle del ciclo"} · ${selectedMeta.subtitle}`}
            bodyClassName=""
            footer={<StatusLegend items={cumplimientoLegendItems} />}
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
                  {phoenixGrupalAlFinal(selectedBlockRows).map((row, index) => (
                    <tr key={`${row.reporte}-${row.bloque}-${row.ejecutivo}-${index}`}>
                      <td className="pd-cell-ejecutivo">{row.ejecutivo}</td>
                      <td className="pd-num">{formatMoney(row.deuda_asignada)}</td>
                      <td className="pd-num">{formatMoney(row.monto_meta_cont)}</td>
                      <td className="pd-num">{formatMoney(row.contenido)}</td>
                      <td className="pd-num"><span className={metricClass(row.pct_contencion)}>{formatPct(row.pct_contencion)}</span></td>
                      {showNormalizationColumns && <td className="pd-num">{row.monto_meta_norm ? formatMoney(row.monto_meta_norm) : "-"}</td>}
                      {showNormalizationColumns && <td className="pd-num">{row.normalizado ? formatMoney(row.normalizado) : "-"}</td>}
                      {showNormalizationColumns && <td className="pd-num"><span className={metricClass(row.pct_normalizacion)}>{row.monto_meta_norm ? formatPct(row.pct_normalizacion) : "-"}</span></td>}
                      {showNormalizationColumns && <td className="pd-num"><span className={metricClass(row.cumplimiento_operativo)}>{formatPct(row.cumplimiento_operativo, 0)}</span></td>}
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

