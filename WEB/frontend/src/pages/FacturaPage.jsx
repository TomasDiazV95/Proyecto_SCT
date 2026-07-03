import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { fetchFacturaBitDashboard } from "../api";

function HomeIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false" className="factura-home-icon">
      <path
        d="M4 11.5 12 5l8 6.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M6.5 10.5V19h11v-8.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M10 19v-4.5h4V19"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function formatMoney(value) {
  return `$${new Intl.NumberFormat("es-CL", { maximumFractionDigits: 0 }).format(Number(value || 0))}`;
}

function formatPercent(value) {
  return `${(Number(value || 0) * 100).toFixed(1).replace(".", ",")}%`;
}

function formatPeriodoLabel(periodo) {
  const [year, month] = String(periodo || "").split("-");
  if (!year || !month) {
    return periodo || "";
  }
  const date = new Date(Number(year), Number(month) - 1, 1);
  return new Intl.DateTimeFormat("es-CL", { month: "long", year: "numeric" }).format(date);
}

const scenarioOrder = [
  ["muy_bajo_lo_esperado", "Muy bajo lo esperado"],
  ["bajo_lo_esperado", "Bajo lo esperado"],
  ["esperado", "Esperado"],
  ["sobre_lo_esperado", "Sobre lo esperado"],
];

const scenarioMeta = {
  muy_bajo_lo_esperado: { short: "Muy bajo", accent: "danger" },
  bajo_lo_esperado: { short: "Bajo", accent: "warning" },
  esperado: { short: "Esperado", accent: "primary" },
  sobre_lo_esperado: { short: "Sobre lo esperado", accent: "success" },
};

function getScenarioLabel(key) {
  return scenarioOrder.find(([scenarioKey]) => scenarioKey === key)?.[1] || "Sobre lo esperado";
}

function getScenarioValue(group, key) {
  return Number(group?.[key] || 0);
}

function getLatestPeriodo(periods = []) {
  return [...periods]
    .filter(Boolean)
    .sort((a, b) => String(b).localeCompare(String(a)))[0] || "";
}

export default function FacturaPage() {
  const [selectedScope, setSelectedScope] = useState("global");
  const [selectedPeriod, setSelectedPeriod] = useState("");
  const [selectedScenario30_90, setSelectedScenario30_90] = useState("sobre_lo_esperado");
  const [selectedScenario90Mas, setSelectedScenario90Mas] = useState("sobre_lo_esperado");
  const [dashboard, setDashboard] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadInitial() {
      setLoading(true);
      setError("");
      try {
        const data = await fetchFacturaBitDashboard("", selectedScope);
        setDashboard(data);
        setSelectedPeriod(data.periodo || getLatestPeriodo(data.available_periods));
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }
    loadInitial();
  }, []);

  useEffect(() => {
    if (!selectedPeriod) {
      return;
    }
    async function loadPeriod() {
      setLoading(true);
      setError("");
      try {
        const data = await fetchFacturaBitDashboard(selectedPeriod, selectedScope);
        setDashboard(data);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }
    loadPeriod();
  }, [selectedPeriod, selectedScope]);

  const availablePeriods = dashboard?.available_periods || [];
  const hasPeriods = availablePeriods.length > 0;
  const canRenderDashboard = hasPeriods && Boolean(selectedPeriod);
  const showNoDataState = !loading && !error && !canRenderDashboard;
  const matrix = dashboard?.matrix || {
    tramo_30_90: {},
    tramo_90_mas: {},
    castigo: {},
    simulacion_total: {},
  };
  const summary = dashboard?.summary || {
    base_30_90: 0,
    base_90_mas: 0,
    base_castigo: 0,
    castigo_simulado: 0,
    total_esperado: 0,
    total_sobre: 0,
  };
  const percentages = dashboard?.percentages || {
    tramo_30_90: {},
    tramo_90_mas: {},
    castigo: {},
  };
  const scopeSummary = dashboard?.scope_summary || {
    simulado_total: 0,
    simulado_esperado: 0,
    factura_real_total: null,
    factura_real_periodo: null,
    negocios_con_datos: 0,
    negocios_con_factura_real: 0,
  };
  const businessSummaryRows = dashboard?.business_summary_rows || [];
  const isBitScope = selectedScope === "bco_internacional";
  const isPorscheScope = selectedScope === "porsche";
  const selectedMeta30_90 = scenarioMeta[selectedScenario30_90] || scenarioMeta.sobre_lo_esperado;
  const selectedMeta90Mas = scenarioMeta[selectedScenario90Mas] || scenarioMeta.sobre_lo_esperado;
  const selectedBusinessRow = businessSummaryRows.find((row) => row.key === selectedScope) || businessSummaryRows[0] || null;

  const selectedValues = useMemo(
    () =>
      isPorscheScope
        ? {
            total: Number(selectedBusinessRow?.simulado_total || 0),
            tramo30_90: 0,
            tramo90Mas: 0,
            castigo: Number(selectedBusinessRow?.simulado_total || 0),
          }
        : {
            total:
              getScenarioValue(matrix.tramo_30_90, selectedScenario30_90) +
              getScenarioValue(matrix.tramo_90_mas, selectedScenario90Mas) +
              getScenarioValue(matrix.castigo, "sobre_lo_esperado"),
            tramo30_90: getScenarioValue(matrix.tramo_30_90, selectedScenario30_90),
            tramo90Mas: getScenarioValue(matrix.tramo_90_mas, selectedScenario90Mas),
            castigo: getScenarioValue(matrix.castigo, "sobre_lo_esperado"),
          },
    [isPorscheScope, matrix, selectedBusinessRow, selectedScenario30_90, selectedScenario90Mas],
  );

  const percentageRows = useMemo(
    () =>
      scenarioOrder.map(([key, label]) => ({
        key,
        label,
        tramo_30_90: percentages.tramo_30_90?.[key] || 0,
        tramo_90_mas: percentages.tramo_90_mas?.[key] || 0,
        castigo: percentages.castigo?.[key] || 0,
      })),
    [percentages],
  );

  const composition = useMemo(() => {
    const total = Number(selectedValues.total || 0);
    const tramo30_90 = total ? (Number(selectedValues.tramo30_90 || 0) / total) * 100 : 0;
    const tramo90Mas = total ? (Number(selectedValues.tramo90Mas || 0) / total) * 100 : 0;
    const castigo = total ? (Number(selectedValues.castigo || 0) / total) * 100 : 0;
    return { total, tramo30_90, tramo90Mas, castigo };
  }, [selectedValues]);

  const effectiveBusinessSummaryRows = useMemo(
    () =>
      businessSummaryRows.map((row) =>
        isBitScope && row.key === "bco_internacional"
          ? {
              ...row,
              simulado_total: Number(selectedValues.total || 0),
              components: {
                ...(row.components || {}),
                tramo_30_90: Number(selectedValues.tramo30_90 || 0),
                tramo_90_mas: Number(selectedValues.tramo90Mas || 0),
                castigo: Number(selectedValues.castigo || 0),
              },
            }
          : row,
      ),
    [businessSummaryRows, isBitScope, selectedValues],
  );

  const effectiveScopeSummary = useMemo(() => {
    const simuladoTotal = effectiveBusinessSummaryRows.reduce((acc, row) => acc + Number(row.simulado_total || 0), 0);
    const negociosConFacturaReal = effectiveBusinessSummaryRows.filter((row) => row.has_real_invoice).length;
    return {
      ...scopeSummary,
      simulado_total: simuladoTotal,
      negocios_con_factura_real: negociosConFacturaReal,
      negocios_con_datos: effectiveBusinessSummaryRows.length,
    };
  }, [effectiveBusinessSummaryRows, scopeSummary]);

  const donutStyle = useMemo(
    () => ({
      background: `conic-gradient(
        #1456d8 0% ${composition.tramo30_90}%,
        #7747d0 ${composition.tramo30_90}% ${composition.tramo30_90 + composition.tramo90Mas}%,
        #ff9800 ${composition.tramo30_90 + composition.tramo90Mas}% 100%
      )`,
    }),
    [composition],
  );

  const scopeTitle =
    selectedScope === "bco_internacional" ? "Banco Internacional" : selectedScope === "porsche" ? "Porsche" : "Global";
  const scopeSubtitle =
    selectedScope === "bco_internacional"
      ? "Vista del negocio Banco Internacional"
      : selectedScope === "porsche"
        ? "Simulado desde total_pagos_excel * 0.04 y control de facturas ya cargadas."
        : `Resumen consolidado de negocios disponibles: ${effectiveScopeSummary.negocios_con_datos || 0}`;
  const realInvoiceTotal = selectedBusinessRow?.factura_real_total ?? null;
  const differenceTotal = selectedBusinessRow?.diferencia_total ?? null;
  const differencePct = selectedBusinessRow?.diferencia_pct ?? null;
  const compareStatus = selectedBusinessRow?.has_real_invoice ? "Con factura" : "Solo simulado";
  const porscheDifferenceLabel = differenceTotal == null ? "-" : formatMoney(differenceTotal);

  return (
    <div className="factura-page">
      <div className="factura-dashboard-shell">
        <main className="factura-main">
          <div className="factura-scope-shell">
            <div className="factura-business-switcher">
              <Link to="/" className="factura-scope-home factura-scope-home-inline" aria-label="Volver al Home">
                <HomeIcon />
              </Link>
              <button
                type="button"
                className={`factura-business-tab ${selectedScope === "global" ? "is-active" : ""}`}
                onClick={() => setSelectedScope("global")}
              >
                Global
              </button>
              <button
                type="button"
                className={`factura-business-tab ${selectedScope === "bco_internacional" ? "is-active" : ""}`}
                onClick={() => setSelectedScope("bco_internacional")}
              >
                Bco Internacional
              </button>
              <button
                type="button"
                className={`factura-business-tab ${selectedScope === "porsche" ? "is-active" : ""}`}
                onClick={() => setSelectedScope("porsche")}
              >
                Porsche
              </button>
            </div>
          </div>

          <div className="factura-topbar">
            <div>
              <h1>{scopeTitle}</h1>
              <p className="factura-topbar-subtitle">{scopeSubtitle}</p>
            </div>

            <div className="factura-topbar-controls">
              <div className="factura-period-inline">
                <label className="form-label mb-1">Periodo</label>
                <select
                  className="form-select"
                  value={selectedPeriod}
                  onChange={(e) => setSelectedPeriod(e.target.value)}
                  disabled={!availablePeriods.length || loading}
                >
                  {availablePeriods.map((period) => (
                    <option key={period} value={period}>
                      {formatPeriodoLabel(period)}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          {error && <div className="alert alert-danger">{error}</div>}

          {showNoDataState && (
            <section className="factura-no-data-panel">
              <div className="factura-no-data-card">
                <div className="factura-no-data-title">Sin datos para factura</div>
                <div className="factura-no-data-copy">
                  No hay periodos disponibles desde <strong>2026-06</strong>. Revisa que las fuentes de factura tengan datos
                  cargados con un <code>periodo</code> o <code>mes_proceso</code> valido.
                </div>
              </div>
            </section>
          )}

          {canRenderDashboard && (
            <>
              {selectedScope === "global" && (
                <section className="factura-global-summary-panel">
                  <div className="factura-panel-header">
                    <div>
                      <h2>Resumen global de negocios</h2>
                      <p>Consolidado de simulado y factura real por negocio para Banco Internacional y Porsche.</p>
                    </div>
                  </div>

                  <div className="factura-global-summary-cards">
                    <article className="factura-global-stat-card">
                      <span>Simulado total</span>
                      <strong>{formatMoney(effectiveScopeSummary.simulado_total)}</strong>
                    </article>
                    <article className="factura-global-stat-card">
                      <span>Factura real total</span>
                      <strong>{effectiveScopeSummary.factura_real_total == null ? "-" : formatMoney(effectiveScopeSummary.factura_real_total)}</strong>
                    </article>
                    <article className="factura-global-stat-card">
                      <span>Negocios con factura real</span>
                      <strong>{effectiveScopeSummary.negocios_con_factura_real}</strong>
                    </article>
                  </div>

                  <div className="table-responsive">
                    <table className="table factura-rules-table mb-0">
                      <thead>
                        <tr>
                          <th>Negocio</th>
                          <th>Simulado</th>
                          <th>Factura real</th>
                          <th>Estado</th>
                        </tr>
                      </thead>
                      <tbody>
                        {effectiveBusinessSummaryRows.map((row) => (
                          <tr key={row.key}>
                            <th>{row.label}</th>
                            <td>{formatMoney(row.simulado_total)}</td>
                            <td>{row.factura_real_total == null ? "-" : formatMoney(row.factura_real_total)}</td>
                            <td>{row.has_real_invoice ? "Con factura" : "Solo simulado"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              )}

              {selectedScope !== "global" && (
                <>
                  <section className="factura-kpi-grid">
                    <article className="factura-hero-card factura-kpi-primary">
                      <div className="factura-hero-card-label">{isPorscheScope ? "Simulado Porsche (4%)" : "Monto a facturar hoy"}</div>
                      <div className="factura-hero-card-value">{formatMoney(selectedValues.total)}</div>
                    </article>
                    <article className="factura-mini-card factura-kpi-secondary">
                      <div className="factura-mini-card-label">{isPorscheScope ? "Factura cargada" : "Tramo 30-90"}</div>
                      <div className="factura-mini-card-value">
                        {isPorscheScope ? (realInvoiceTotal == null ? "-" : formatMoney(realInvoiceTotal)) : formatMoney(selectedValues.tramo30_90)}
                      </div>
                      {!isPorscheScope && (
                        <select
                          className={`form-select factura-mini-card-select is-${selectedMeta30_90.accent}`}
                          value={selectedScenario30_90}
                          onChange={(e) => setSelectedScenario30_90(e.target.value)}
                        >
                          {scenarioOrder.map(([key, label]) => (
                            <option key={key} value={key}>
                              {label}
                            </option>
                          ))}
                        </select>
                      )}
                    </article>
                    <article className="factura-mini-card factura-kpi-secondary">
                      <div className="factura-mini-card-label">{isPorscheScope ? "Estado" : "Tramo 90+"}</div>
                      <div className="factura-mini-card-value">{isPorscheScope ? compareStatus : formatMoney(selectedValues.tramo90Mas)}</div>
                      {!isPorscheScope && (
                        <select
                          className={`form-select factura-mini-card-select is-${selectedMeta90Mas.accent}`}
                          value={selectedScenario90Mas}
                          onChange={(e) => setSelectedScenario90Mas(e.target.value)}
                        >
                          {scenarioOrder.map(([key, label]) => (
                            <option key={key} value={key}>
                              {label}
                            </option>
                          ))}
                        </select>
                      )}
                    </article>
                    <article className="factura-mini-card factura-kpi-secondary">
                      <div className="factura-mini-card-label">{isPorscheScope ? "Diferencia" : "Castigo"}</div>
                      <div className="factura-mini-card-value">{isPorscheScope ? porscheDifferenceLabel : formatMoney(selectedValues.castigo)}</div>
                    </article>
                  </section>

                  <section className="factura-content-grid">
                    {!isPorscheScope && (
                      <div className="factura-panel factura-panel-wide">
                        <div className="factura-panel-header">
                          <div>
                            <h2>Simulacion de factura por escenario</h2>
                            <p>Montos calculados sobre gasto de cobranza por tramo.</p>
                          </div>
                          {loading && <span className="factura-inline-status">Actualizando...</span>}
                        </div>

                        <div className="table-responsive">
                          <table className="table factura-sim-table mb-0">
                            <thead>
                              <tr>
                                <th>Tramo</th>
                                {scenarioOrder.map(([key, label]) => (
                                  <th key={key}>
                                    <span className="factura-table-scenario-button">{label}</span>
                                  </th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              <tr>
                                <th>30-90</th>
                                {scenarioOrder.map(([key]) => (
                                  <td key={key}>{formatMoney(matrix.tramo_30_90?.[key])}</td>
                                ))}
                              </tr>
                              <tr>
                                <th>90+</th>
                                {scenarioOrder.map(([key]) => (
                                  <td key={key}>{formatMoney(matrix.tramo_90_mas?.[key])}</td>
                                ))}
                              </tr>
                              <tr>
                                <th>Castigo</th>
                                {scenarioOrder.map(([key]) => (
                                  <td key={key}>{formatMoney(matrix.castigo?.[key])}</td>
                                ))}
                              </tr>
                              <tr className="factura-sim-total-row">
                                <th>Total facturable</th>
                                {scenarioOrder.map(([key]) => (
                                  <td key={key}>{formatMoney(matrix.simulacion_total?.[key])}</td>
                                ))}
                              </tr>
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}

                    <div className="factura-panel factura-panel-side">
                      <div className="factura-panel-header">
                        <div>
                          <h2>Simulacion vs factura</h2>
                        </div>
                      </div>

                      <div className="factura-compare-card">
                        <div className="factura-compare-split">
                          <div>
                            <div className="factura-compare-label">Monto simulado</div>
                            <div className="factura-compare-value">{formatMoney(selectedValues.total)}</div>
                          </div>
                          <div className="factura-compare-versus">VS</div>
                          <div>
                            <div className="factura-compare-label">Factura real</div>
                            <div className={`factura-compare-value ${realInvoiceTotal == null ? "is-muted" : ""}`}>
                              {realInvoiceTotal == null ? "-" : formatMoney(realInvoiceTotal)}
                            </div>
                            <div className={`factura-compare-caption ${selectedBusinessRow?.has_real_invoice ? "is-success" : "is-warning"}`}>
                              {selectedBusinessRow?.has_real_invoice ? "Factura cargada" : "Aun no disponible"}
                            </div>
                          </div>
                        </div>
                      </div>

                      <div className="factura-status-list">
                        <div className="factura-status-row">
                          <span>Diferencia</span>
                          <strong>{differenceTotal == null ? "-" : formatMoney(differenceTotal)}</strong>
                        </div>
                        <div className="factura-status-row">
                          <span>Diferencia %</span>
                          <strong>{differencePct == null ? "-" : formatPercent(differencePct)}</strong>
                        </div>
                        <div className="factura-status-row">
                          <span>Estado</span>
                          <strong className="factura-status-badge">{compareStatus}</strong>
                        </div>
                      </div>

                      <div className="factura-panel-footnote">
                        {isPorscheScope
                          ? "Los registros con origen factura se consideran como factura ya cargada para el periodo."
                          : "La factura real se cargara a principio del proximo mes y se comparara automaticamente."}
                      </div>
                    </div>
                  </section>

                  {!isPorscheScope && (
                    <section className="factura-bottom-grid">
                      <div className="factura-panel">
                        <div className="factura-panel-header">
                          <div>
                            <h2>Composicion del monto facturable</h2>
                          </div>
                        </div>

                        <div className="factura-composition-grid">
                          <div className="factura-donut-shell">
                            <div className="factura-donut" style={donutStyle}>
                              <div className="factura-donut-hole">
                                <span>Total</span>
                                <strong>{formatMoney(composition.total)}</strong>
                              </div>
                            </div>
                          </div>

                          <div className="factura-composition-legend">
                            <div className="factura-composition-item">
                              <div className="factura-composition-label">
                                <span className="factura-dot is-blue" />
                                30-90 dias
                              </div>
                              <div className="factura-composition-values">
                                <strong>{formatMoney(selectedValues.tramo30_90)}</strong>
                                <span>{formatPercent(composition.tramo30_90 / 100)}</span>
                              </div>
                            </div>

                            <div className="factura-composition-item">
                              <div className="factura-composition-label">
                                <span className="factura-dot is-purple" />
                                90+ dias
                              </div>
                              <div className="factura-composition-values">
                                <strong>{formatMoney(selectedValues.tramo90Mas)}</strong>
                                <span>{formatPercent(composition.tramo90Mas / 100)}</span>
                              </div>
                            </div>

                            <div className="factura-composition-item">
                              <div className="factura-composition-label">
                                <span className="factura-dot is-orange" />
                                Castigo
                              </div>
                              <div className="factura-composition-values">
                                <strong>{formatMoney(selectedValues.castigo)}</strong>
                                <span>{formatPercent(composition.castigo / 100)}</span>
                              </div>
                            </div>
                          </div>
                        </div>

                        <div className="factura-panel-footnote">
                          La composicion visual usa exactamente los montos simulados que ves en las cards superiores.
                        </div>
                      </div>

                      <div className="factura-panel">
                        <div className="factura-panel-header">
                          <div>
                            <h2>Parametros de calculo</h2>
                          </div>
                        </div>

                        <div className="table-responsive">
                          <table className="table factura-rules-table mb-0">
                            <thead>
                              <tr>
                                <th>Clasificacion</th>
                                <th>30-90</th>
                                <th>90+</th>
                                <th>Castigo</th>
                              </tr>
                            </thead>
                            <tbody>
                              {percentageRows.map((row) => (
                                <tr key={row.key}>
                                  <th>{row.label}</th>
                                  <td>{formatPercent(row.tramo_30_90)}</td>
                                  <td>{formatPercent(row.tramo_90_mas)}</td>
                                  <td>{formatPercent(row.castigo)}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>

                        <div className="factura-panel-footnote">
                          Los porcentajes se aplican sobre el gasto de cobranza por tramo.
                        </div>
                      </div>
                    </section>
                  )}
                </>
              )}
            </>
          )}
        </main>
      </div>
    </div>
  );
}
