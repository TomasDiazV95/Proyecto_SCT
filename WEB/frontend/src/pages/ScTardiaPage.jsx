import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { fetchCycle, fetchFilters, fetchGeneral } from "../api";

const initialFilters = {
  periodo: "",
  zona: "",
  ejecutivo: "",
};

const blockOrder = ["C3", "SUSCEPTIBLE CV", "C5", "C6", "PRE CASTIGO", "F1 - F2", "F3", "F4", "TOTAL F1 - F4"];
const generalDisplayBlocks = ["C3", "SUSCEPTIBLE CV", "C5", "C6", "PRE CASTIGO", "TOTAL F1 - F4"];
const generalComplianceBlocks = ["C3", "SUSCEPTIBLE CV", "C5", "C6", "PRE CASTIGO"];
const stcAlertBlocks = ["C3", "SUSCEPTIBLE CV", "C5", "C6", "PRE CASTIGO"];
const castigoAlertBlocks = ["F1 - F2", "F3"];

const blockMeta = {
  C3: { title: "C3", subtitle: "Contencion y normalizacion", icon: "bi-bullseye" },
  "SUSCEPTIBLE CV": { title: "Susceptible CV", subtitle: "Contencion convenio", icon: "bi-shield-check" },
  C5: { title: "C5", subtitle: "Contencion tramo 90-119", icon: "bi-layers" },
  C6: { title: "C6", subtitle: "Salidas convenio", icon: "bi-arrow-up-right-circle" },
  "PRE CASTIGO": { title: "Pre Castigo", subtitle: "Contencion susceptible castigo", icon: "bi-exclamation-diamond" },
  "F1 - F2": { title: "F1 - F2", subtitle: "Recupero castigo", icon: "bi-cash-coin" },
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
  return `metric-chip metric-${status}`;
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

function initials(name) {
  return String(name || "?")
    .split(" ")
    .filter(Boolean)
    .map((part) => part[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

function sortBlocks(a, b) {
  const ai = blockOrder.indexOf(a);
  const bi = blockOrder.indexOf(b);
  return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi) || a.localeCompare(b);
}

function buildReportAlerts(rows, allowedBlocks) {
  const filteredRows = rows.filter((row) => allowedBlocks.includes(row.bloque));
  const byBlock = allowedBlocks
    .map((block) => {
      const blockRows = filteredRows.filter((row) => row.bloque === block);
      if (!blockRows.length) return null;
      const cumplimiento = blockRows.reduce((acc, row) => acc + row.cumplimiento_operativo, 0) / blockRows.length;
      return { block, cumplimiento };
    })
    .filter(Boolean);

  const byExec = new Map();
  filteredRows.forEach((row) => {
    const current = byExec.get(row.ejecutivo) || { ejecutivo: row.ejecutivo, total: 0, count: 0 };
    current.total += row.cumplimiento_operativo;
    current.count += 1;
    byExec.set(row.ejecutivo, current);
  });

  const executives = Array.from(byExec.values()).map((item) => ({
    ejecutivo: item.ejecutivo,
    cumplimiento: item.count ? item.total / item.count : 0,
  }));

  return {
    lowBlock: [...byBlock].sort((a, b) => a.cumplimiento - b.cumplimiento)[0] || null,
    lowExec: [...executives].sort((a, b) => a.cumplimiento - b.cumplimiento)[0] || null,
    bestBlock: [...byBlock].sort((a, b) => b.cumplimiento - a.cumplimiento)[0] || null,
  };
}

export default function ScTardiaPage() {
  const [view, setView] = useState("general");
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
        const data = view === "general" ? await fetchGeneral(filters) : await fetchCycle(filters);
        setRows(data || []);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, [filters, view]);

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

  const executiveRows = useMemo(() => {
    const grouped = new Map();
    rowsWithMetrics.forEach((row) => {
        const key = row.ejecutivo;
        const current = grouped.get(key) || {
          ejecutivo: row.ejecutivo,
          casos_asignados: 0,
          bloques: {},
          bloques_activos: new Set(),
          ponderadores_nivel_1: { PTC: 0, STOCK: 0 },
        };
        current.casos_asignados += num(row.cantidad_casos);
        current.bloques[row.bloque] = row.cumplimiento_operativo;
        (row.bloques_activos || []).forEach((block) => current.bloques_activos.add(block));
        current.ponderadores_nivel_1 = row.ponderadores_nivel_1 || current.ponderadores_nivel_1;
        grouped.set(key, current);
      });

    return Array.from(grouped.values())
      .map((item) => {
        const activeMoraBlocks = generalComplianceBlocks.filter((block) => item.bloques_activos.has(block));
        const hasMoraTardia = activeMoraBlocks.length > 0;
        const hasCastigo = item.bloques_activos.has("TOTAL F1 - F4");
        const moraCumplimiento = hasMoraTardia
          ? activeMoraBlocks.reduce((acc, block) => acc + num(item.bloques[block]), 0) / activeMoraBlocks.length
          : 0;
        const castigoCumplimiento = num(item.bloques["TOTAL F1 - F4"]);
        const ptcWeight = num(item.ponderadores_nivel_1?.PTC) / 100;
        const stockWeight = num(item.ponderadores_nivel_1?.STOCK) / 100;
        let cumplimiento = 0;

        if (hasMoraTardia && hasCastigo) {
          cumplimiento = (moraCumplimiento * ptcWeight) + (castigoCumplimiento * stockWeight);
        } else if (hasMoraTardia) {
          cumplimiento = moraCumplimiento;
        } else if (hasCastigo) {
          cumplimiento = castigoCumplimiento;
        }

        return {
          ...item,
          bloques_activos: activeMoraBlocks,
          cumplimiento_mora_tardia: moraCumplimiento,
          cumplimiento_castigo: castigoCumplimiento,
          cumplimiento_operativo: capPct(cumplimiento),
        };
      })
      .filter((item) => statusFilters[statusOf(item.cumplimiento_operativo)])
      .sort((a, b) => b.cumplimiento_operativo - a.cumplimiento_operativo);
  }, [rowsWithMetrics, statusFilters]);

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

  const totals = useMemo(() => {
    const base = rowsWithMetrics.filter((row) => row.reporte !== "CASTIGO CONSOLIDADO");
    const deuda = base.reduce((acc, row) => acc + num(row.deuda_asignada), 0);
    const casos = base.reduce((acc, row) => acc + num(row.cantidad_casos), 0);
    const ponderado = base.reduce((acc, row) => acc + row.cumplimiento_operativo * num(row.deuda_asignada), 0);
    const cumplimiento = deuda ? ponderado / deuda : 0;
    const sobreMeta = executiveRows.filter((row) => row.cumplimiento_operativo >= 100).length;
    const alerta = [...blockSummary].sort((a, b) => a.cumplimiento - b.cumplimiento)[0];
    return { deuda, casos, cumplimiento, sobreMeta, alerta };
  }, [blockSummary, executiveRows, rowsWithMetrics]);

  const selectedBlockRows = (view === "ciclo" ? rowsWithMetrics : visibleMetricRows).filter((row) => row.bloque === selectedBlock);
  const showNormalizationColumns = selectedBlock === "C3";
  const selectedMeta = blockMeta[selectedBlock] || { title: selectedBlock, subtitle: "Detalle de bloque", icon: "bi-layers" };

  const alerts = useMemo(() => {
    return {
      moraTardia: buildReportAlerts(rowsWithMetrics.filter((row) => row.reporte === "STC"), stcAlertBlocks),
      castigo: buildReportAlerts(rowsWithMetrics.filter((row) => row.reporte === "CASTIGO"), castigoAlertBlocks),
    };
  }, [rowsWithMetrics]);

  return (
    <div className="sc-tardia-page">
      <nav className="navbar bg-white py-3 sc-navbar">
        <div className="container-fluid sc-page-shell px-3 px-lg-4">
          <div className="d-flex align-items-center gap-3">
            <div className="sc-brand-mark"><i className="bi bi-speedometer2" /></div>
            <div>
              <div className="fw-bold">Productividad Ejecutivos</div>
              <div className="small text-secondary">Seguimiento de metas y cumplimiento SC Tardia</div>
              <Link to="/productividad" className="small text-decoration-none">Volver al Home</Link>
            </div>
          </div>
          <span className="badge text-bg-light border px-3 py-2"><i className="bi bi-calendar3 me-1" /> {filters.periodo || "Sin fecha"}</span>
        </div>
      </nav>

      <main className="container-fluid sc-page-shell px-3 px-lg-4 py-4">
        <div className="row g-4">
          <aside className="col-12 col-xl-3">
            <div className="card sc-soft-card sc-filter-card">
              <div className="card-body p-4">
                <div className="d-flex justify-content-between align-items-center mb-3">
                  <h2 className="h6 mb-0 fw-bold"><i className="bi bi-funnel me-2" />Filtros</h2>
                  <button className="btn btn-link btn-sm text-decoration-none p-0" onClick={clearFilters}>Limpiar</button>
                </div>

                <label className="form-label small fw-semibold">Fecha consulta</label>
                <select className="form-select mb-3" value={filters.periodo} onChange={(e) => onChange("periodo", e.target.value)}>
                  {options.periodos.map((value) => <option key={value} value={value}>{value}</option>)}
                </select>

                <label className="form-label small fw-semibold">Zona</label>
                <select className="form-select mb-3" value={filters.zona} onChange={(e) => onChange("zona", e.target.value)}>
                  <option value="">Todas las zonas</option>
                  {options.zonas.map((value) => <option key={value} value={value}>{value}</option>)}
                </select>

                <label className="form-label small fw-semibold">Ejecutivo</label>
                <select className="form-select mb-3" value={filters.ejecutivo} onChange={(e) => onChange("ejecutivo", e.target.value)}>
                  <option value="">Todos los ejecutivos</option>
                  {options.ejecutivos.map((value) => <option key={value} value={value}>{value}</option>)}
                </select>

                <label className="form-label small fw-semibold">Estado de cumplimiento</label>
                <div className="d-flex flex-wrap gap-2 mb-4">
                  {[
                    ["success", "Sobre meta", "success"],
                    ["warning", "En riesgo", "warning"],
                    ["danger", "Bajo meta", "danger"],
                    ["neutral", "Sin avance", "secondary"],
                  ].map(([key, label, color]) => (
                    <button
                      key={key}
                      type="button"
                      className={`btn btn-sm btn-${statusFilters[key] ? color : `outline-${color}`}`}
                      onClick={() => setStatusFilters((prev) => ({ ...prev, [key]: !prev[key] }))}
                    >
                      {label}
                    </button>
                  ))}
                </div>

                <div className="small text-secondary">
                  La fecha seleccionada se usa como fecha de consulta de la sabana y define el mes de metas.
                </div>
              </div>
            </div>
          </aside>

          <section className="col-12 col-xl-9">
            <div className="d-flex flex-column flex-lg-row justify-content-between align-items-lg-center gap-3 mb-4">
              <div>
                <h1 className="h3 sc-section-title mb-1">Resumen de cumplimiento</h1>
                <p className="text-secondary mb-0">Lectura operativa por ejecutivo, ciclo y reporte.</p>
              </div>
              <div className="nav nav-pills bg-body-secondary p-1 rounded-4">
                <button className={`nav-link ${view === "general" ? "active" : ""}`} onClick={() => setView("general")}><i className="bi bi-grid me-1" />Vista general</button>
                <button className={`nav-link ${view === "ciclo" ? "active" : ""}`} onClick={() => setView("ciclo")}><i className="bi bi-layers me-1" />Por ciclo</button>
              </div>
            </div>

            {error && <div className="alert alert-danger">{error}</div>}

            {loading ? (
              <div className="card sc-soft-card"><div className="card-body text-center py-5">Cargando...</div></div>
            ) : view === "general" ? (
              <>
                <div className="row g-3 mb-4">
                  <div className="col-12 col-md-6 col-xxl-3"><KpiCard icon="bi-bullseye" color="primary" label="Cumplimiento operativo" value={formatPct(totals.cumplimiento)} caption="Temporal hasta definir formula final" /></div>
                  <div className="col-12 col-md-6 col-xxl-3"><KpiCard icon="bi-folder-check" color="info" label="Casos activos" value={totals.casos.toLocaleString("es-CL")} caption="Operaciones consideradas en la fecha" /></div>
                  <div className="col-12 col-md-6 col-xxl-3"><KpiCard icon="bi-people" color="success" label="Ejecutivos sobre meta" value={`${totals.sobreMeta}/${executiveRows.length}`} caption="Segun cumplimiento operativo" /></div>
                  <div className="col-12 col-md-6 col-xxl-3"><KpiCard icon="bi-exclamation-triangle" color="danger" label="Bloque con mayor alerta" value={totals.alerta?.block || "-"} caption={totals.alerta ? formatPct(totals.alerta.cumplimiento) : "Sin datos"} /></div>
                </div>

                <div className="card sc-soft-card mb-4">
                  <div className="card-body p-4">
                    <div className="d-flex flex-column flex-md-row justify-content-between gap-2 mb-3">
                      <div><h3 className="h5 fw-bold mb-1">Ranking de ejecutivos</h3><div className="small text-secondary">Ordenado por cumplimiento operativo ponderado por deuda.</div></div>
                      <div className="d-flex gap-3 small align-items-center flex-wrap"><Legend color="success" text="Sobre meta" /><Legend color="warning" text="En riesgo" /><Legend color="danger" text="Bajo meta" /></div>
                    </div>
                    <div className="table-responsive">
                      <table className="table sc-table-modern align-middle mb-0">
                        <thead><tr><th>Ejecutivo</th><th>Casos</th>{generalDisplayBlocks.map((block) => <th key={block}>{block}</th>)}<th>Cumplimiento</th></tr></thead>
                        <tbody>
                          {executiveRows.map((row, index) => (
                            <tr key={`${row.ejecutivo}-${row.zona}`}>
                              <td><div className="d-flex align-items-center gap-2"><div className="sc-avatar">{initials(row.ejecutivo)}</div><div><div className="fw-semibold">{row.ejecutivo}</div><div className="small text-secondary">#{index + 1} ranking</div></div></div></td>
                              <td>{row.casos_asignados.toLocaleString("es-CL")}</td>
                              {generalDisplayBlocks.map((block) => <td key={`${row.ejecutivo}-${block}`}><span className={metricClass(row.bloques[block])}>{formatPct(row.bloques[block] || 0, 0)}</span></td>)}
                              <td><div className="fw-bold fs-6">{formatPct(row.cumplimiento_operativo)}</div><div className="progress sc-progress-thin mt-1"><div className="progress-bar" style={{ width: `${Math.min(row.cumplimiento_operativo, 130) / 1.3}%` }} /></div></td>
                            </tr>
                          ))}
                          {!executiveRows.length && <EmptyRow colSpan={9} />}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>

                <div className="row g-4">
                  <div className="col-12 col-lg-7">
                    <div className="card sc-soft-card h-100"><div className="card-body p-4"><h3 className="h5 fw-bold">Cumplimiento por ciclo</h3><p className="small text-secondary">Comparacion de contenido contra meta monetaria por ciclo.</p><div className="mt-4">{blockSummary.map((item) => <CycleBar key={item.block} item={item} />)}</div></div></div>
                  </div>
                  <div className="col-12 col-lg-5">
                    <div className="card sc-soft-card h-100"><div className="card-body p-4"><h3 className="h5 fw-bold">Alertas de gestion</h3><p className="small text-secondary">Puntos que requieren revision prioritaria.</p>
                      <AlertSection title="Mora Tardia" alerts={alerts.moraTardia} />
                      <AlertSection title="Castigo" alerts={alerts.castigo} />
                    </div></div>
                  </div>
                </div>
              </>
            ) : (
              <>
                <div className="row g-3 mb-4">
                  {blockOrder.map((block) => {
                    const summary = blockSummary.find((item) => item.block === block) || { block, cumplimiento: 0, deuda: 0, rows: 0, status: "neutral" };
                    const meta = blockMeta[block] || { title: block, subtitle: "Detalle", icon: "bi-layers" };
                    return (
                      <div className="col-12 col-md-6 col-xxl-4" key={block}>
                        <button type="button" className={`sc-cycle-card bg-white p-4 text-start w-100 ${selectedBlock === block ? "active" : ""}`} onClick={() => setSelectedBlock(block)}>
                          <div className="d-flex justify-content-between align-items-start gap-2"><div><div className="sc-cycle-label"><i className={`bi ${meta.icon} me-1`} />{block}</div><div className="fw-bold mt-1">{meta.title}</div><div className="small text-secondary mt-1">{meta.subtitle}</div></div><span className={`metric-chip metric-${summary.status}`}>{formatPct(summary.cumplimiento)}</span></div>
                          <div className="small text-secondary mt-3">{formatMoneyShort(summary.deuda)} asignado</div>
                        </button>
                      </div>
                    );
                  })}
                </div>

                <div className="card sc-soft-card">
                  <div className="card-body p-4">
                    <div className="d-flex flex-column flex-lg-row justify-content-between align-items-lg-center gap-3 mb-4">
                      <div><div className="sc-cycle-label">Detalle del ciclo</div><h3 className="h4 fw-bold mb-1">{selectedMeta.title}</h3><div className="text-secondary">{selectedMeta.subtitle}</div></div>
                      <span className="badge rounded-pill text-bg-light border px-3 py-2">Fecha consulta: {filters.periodo}</span>
                    </div>
                    <div className="table-responsive">
                      <table className="table sc-table-modern mb-0">
                        <thead>
                          <tr>
                            <th>Ejecutivo</th>
                            <th>Deuda asignada</th>
                            <th>Meta cont.</th>
                            <th>Contenido</th>
                            <th>% Cont.</th>
                            {showNormalizationColumns && <th>Meta norm.</th>}
                            {showNormalizationColumns && <th>Normalizado</th>}
                            {showNormalizationColumns && <th>% Norm.</th>}
                            {showNormalizationColumns && <th>Cumplimiento</th>}
                            <th>Casos</th>
                          </tr>
                        </thead>
                        <tbody>
                          {selectedBlockRows.map((row, index) => (
                            <tr key={`${row.reporte}-${row.bloque}-${row.ejecutivo}-${index}`}>
                              <td className="fw-semibold">{row.ejecutivo}</td>
                              <td>{formatMoney(row.deuda_asignada)}</td>
                              <td>{formatMoney(row.monto_meta_cont)}</td>
                              <td>{formatMoney(row.contenido)}</td>
                              <td><span className={metricClass(row.pct_contencion)}>{formatPct(row.pct_contencion)}</span></td>
                              {showNormalizationColumns && <td>{row.monto_meta_norm ? formatMoney(row.monto_meta_norm) : "-"}</td>}
                              {showNormalizationColumns && <td>{row.normalizado ? formatMoney(row.normalizado) : "-"}</td>}
                              {showNormalizationColumns && <td><span className={metricClass(row.pct_normalizacion)}>{row.monto_meta_norm ? formatPct(row.pct_normalizacion) : "-"}</span></td>}
                              {showNormalizationColumns && <td><span className={metricClass(row.cumplimiento_operativo)}>{formatPct(row.cumplimiento_operativo)}</span></td>}
                              <td>{num(row.cantidad_casos).toLocaleString("es-CL")}</td>
                            </tr>
                          ))}
                          {!selectedBlockRows.length && <EmptyRow colSpan={showNormalizationColumns ? 10 : 6} />}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              </>
            )}
          </section>
        </div>
      </main>
    </div>
  );
}

function KpiCard({ icon, color, label, value, caption }) {
  return (
    <div className="card sc-soft-card sc-kpi-card h-100">
      <div className="card-body p-4">
        <div className="d-flex justify-content-between gap-3">
          <div><div className="sc-kpi-caption">{label}</div><div className="h3 fw-bold mt-2 mb-1">{value}</div></div>
          <div className={`sc-kpi-icon bg-${color}-subtle text-${color}`}><i className={`bi ${icon}`} /></div>
        </div>
        <div className="small text-secondary mt-2">{caption}</div>
      </div>
    </div>
  );
}

function Legend({ color, text }) {
  return <span><span className={`sc-legend-dot bg-${color} me-1`} />{text}</span>;
}

function CycleBar({ item }) {
  const color = item.status === "success" ? "bg-success" : item.status === "warning" ? "bg-warning" : item.status === "neutral" ? "bg-secondary" : "bg-danger";
  return (
    <div className="mb-4">
      <div className="d-flex justify-content-between mb-2"><span className="fw-semibold">{item.block}</span><span className="fw-bold">{formatPct(item.cumplimiento)}</span></div>
      <div className="progress" style={{ height: 10 }}><div className={`progress-bar ${color}`} style={{ width: `${Math.min(item.cumplimiento, 100)}%` }} /></div>
      <div className="small text-secondary mt-1">Meta: {formatMoneyShort(item.meta)} · Contenido: {formatMoneyShort(item.contenido)}</div>
    </div>
  );
}

function AlertItem({ color, icon, title, text }) {
  return (
    <div className="list-group-item px-0 py-3 border-0">
      <div className="d-flex gap-3"><div className={`sc-kpi-icon bg-${color}-subtle text-${color}`}><i className={`bi ${icon}`} /></div><div><div className="fw-semibold">{title}</div><div className="small text-secondary">{text}</div></div></div>
    </div>
  );
}

function AlertSection({ title, alerts }) {
  return (
    <div className="mt-3">
      <div className="small fw-bold text-uppercase text-secondary mb-1">{title}</div>
      <div className="list-group list-group-flush">
        <AlertItem color="danger" icon="bi-exclamation-circle" title={`${alerts.lowBlock?.block || "Sin bloque"} bajo seguimiento`} text={alerts.lowBlock ? `Cumplimiento operativo ${formatPct(alerts.lowBlock.cumplimiento)}.` : "Sin datos disponibles."} />
        <AlertItem color="warning" icon="bi-person-x" title={`${alerts.lowExec?.ejecutivo || "Sin ejecutivo"}`} text={alerts.lowExec ? `Cierre operativo ${formatPct(alerts.lowExec.cumplimiento)}.` : "Sin datos disponibles."} />
        <AlertItem color="success" icon="bi-trophy" title={`${alerts.bestBlock?.block || "Sin bloque"} lidera`} text={alerts.bestBlock ? `Mejor bloque con ${formatPct(alerts.bestBlock.cumplimiento)}.` : "Sin datos disponibles."} />
      </div>
    </div>
  );
}

function EmptyRow({ colSpan }) {
  return <tr><td colSpan={colSpan} className="text-center text-secondary py-4">Sin datos para los filtros seleccionados.</td></tr>;
}
