import { Fragment, useEffect, useMemo, useState } from "react";
import { fetchSthDetail, fetchSthFilters, fetchSthGeneral, fetchSthOperationsDetail } from "../api";
import { EmptyRow, Field, FilterBar, LoadingState, PageHeader, Pagination, SectionCard, StatusLegend, ViewTabs, relativeLegendItems } from "../components/productividad/ui";

const initialFilters = {
  periodo: "",
  ejecutivo: "",
};

const initialOperationsFilters = {
  operacion: "",
  producto: "",
  ciclo: "",
  contenido: "",
};

const productLabel = {
  hipotecario: "Hipotecario",
  consumo: "Consumo",
  pyme: "Pyme",
  tarjeta: "TC",
};

function formatPct(value) {
  if (value === null || value === undefined) {
    return "-";
  }
  return `${Number(value || 0).toFixed(1)}%`;
}

function formatMoney(value) {
  return new Intl.NumberFormat("es-CL", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(Number(value || 0));
}

function formatMM(value) {
  return formatMoney(Number(value || 0) / 1000000);
}

function yesNo(value) {
  return Number(value || 0) === 1 ? "Si" : "No";
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

function dotClassByThresholds(value, thresholds) {
  const n = Number(value || 0);
  if (n >= thresholds.p66) {
    return "pd-status pd-status-success";
  }
  if (n >= thresholds.p33) {
    return "pd-status pd-status-warning";
  }
  return "pd-status pd-status-danger";
}

export default function SthPage() {
  const [view, setView] = useState("general");
  const [filters, setFilters] = useState(initialFilters);
  const [operationsFilters, setOperationsFilters] = useState(initialOperationsFilters);
  const [operationSearch, setOperationSearch] = useState("");
  const [options, setOptions] = useState({ periodos: [], ejecutivos: [], productos_detalle: [], ciclos: [] });
  const [generalRows, setGeneralRows] = useState([]);
  const [detailBlocks, setDetailBlocks] = useState([]);
  const [operationsRows, setOperationsRows] = useState([]);
  const [operationsTotal, setOperationsTotal] = useState(0);
  const [operationsPage, setOperationsPage] = useState(1);
  const [operationsPageSize, setOperationsPageSize] = useState(100);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadFilters() {
      try {
        const data = await fetchSthFilters();
        setOptions(data);
        setFilters((prev) => ({
          ...prev,
          periodo: data.periodos?.[0] || "",
        }));
      } catch (err) {
        setError(err.message);
      }
    }
    loadFilters();
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setOperationsFilters((prev) => ({ ...prev, operacion: operationSearch.trim() }));
      setOperationsPage(1);
    }, 450);

    return () => window.clearTimeout(timer);
  }, [operationSearch]);

  useEffect(() => {
    async function loadData() {
      if (!filters.periodo) {
        return;
      }
      setLoading(true);
      setError("");
      try {
        if (view === "detalle") {
          const detail = await fetchSthOperationsDetail({
            ...filters,
            ...operationsFilters,
            page: operationsPage,
            page_size: operationsPageSize,
          });
          setOperationsRows(detail.data || []);
          setOperationsTotal(Number(detail.total || 0));
        } else {
          const [general, detail] = await Promise.all([fetchSthGeneral(filters), fetchSthDetail(filters)]);
          setGeneralRows(general);
          setDetailBlocks(detail);
        }
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, [filters, operationsFilters, operationsPage, operationsPageSize, view]);

  const generalHeaders = useMemo(
    () => [
      { key: "hipotecario", label: "Cump Hip" },
      { key: "consumo", label: "Cump Cons" },
      { key: "pyme", label: "Cump Pyme" },
      { key: "tarjeta", label: "Cump TC" },
    ],
    []
  );

  const thresholdsByProduct = useMemo(() => {
    const out = {};
    detailBlocks.forEach((block) => {
      const values = [];
      (block.pivot_rows || []).forEach((row) => {
        if (String(row.ejecutivo || "").trim().toLowerCase() === "grupal") {
          return;
        }
        values.push(Number(row.cumplimiento_final || 0));
        (block.ciclos || []).forEach((ciclo) => {
          const item = row.ciclos?.[String(ciclo)];
          if (item) {
            values.push(Number(item.cumplimiento_meta || 0));
          }
        });
      });
      const sorted = values.filter((v) => Number.isFinite(v)).sort((a, b) => a - b);
      out[block.producto] = {
        p33: percentile(sorted, 0.33),
        p66: percentile(sorted, 0.66),
      };
    });
    return out;
  }, [detailBlocks]);

  const generalThresholds = useMemo(() => {
    const values = (generalRows || [])
      .filter((row) => row.ejecutivo !== "Total general")
      .filter((row) => String(row.ejecutivo || "").trim().toLowerCase() !== "grupal")
      .map((row) => Number(row.cumplimiento_final || 0))
      .filter((v) => Number.isFinite(v))
      .sort((a, b) => a - b);

    return {
      p33: percentile(values, 0.33),
      p66: percentile(values, 0.66),
    };
  }, [generalRows]);

  function productDotClass(producto, value) {
    const thresholds = thresholdsByProduct[producto] || { p33: 0, p66: 0 };
    return dotClassByThresholds(value, thresholds);
  }

  function onChange(name, value) {
    setFilters((prev) => ({ ...prev, [name]: value }));
    setOperationsPage(1);
  }

  function onOperationsChange(name, value) {
    setOperationsFilters((prev) => ({ ...prev, [name]: value }));
    setOperationsPage(1);
  }

  function clearOperationsFilters() {
    setFilters((prev) => ({ ...prev, ejecutivo: "" }));
    setOperationsFilters(initialOperationsFilters);
    setOperationSearch("");
    setOperationsPage(1);
  }

  const operationsTotalPages = Math.max(1, Math.ceil(operationsTotal / operationsPageSize));
  const operationsFrom = operationsTotal ? (operationsPage - 1) * operationsPageSize + 1 : 0;
  const operationsTo = operationsTotal ? Math.min(operationsPage * operationsPageSize, operationsTotal) : 0;
  const hasOperationsFilters = filters.ejecutivo || operationSearch || Object.values(operationsFilters).some(Boolean);

  return (
    <div className="pd-page">
      <PageHeader title="Santander Hipotecario" subtitle="KPI hipotecario y productos asociados por ejecutivo y ciclo." />

      <FilterBar
        actions={
          view === "detalle" && (
            <button type="button" className="pd-btn pd-btn-ghost" onClick={clearOperationsFilters} disabled={!hasOperationsFilters || loading}>
              <i className="bi bi-x-circle" aria-hidden="true" /> Limpiar filtros
            </button>
          )
        }
      >
        <Field label="Periodo">
          <select className="form-select" value={filters.periodo} onChange={(e) => onChange("periodo", e.target.value)}>
            {options.periodos.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Ejecutivo">
          <select className="form-select" value={filters.ejecutivo} onChange={(e) => onChange("ejecutivo", e.target.value)}>
            <option value="">Todos</option>
            {options.ejecutivos.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </Field>
        {view === "detalle" && (
          <>
            <Field label="Operacion">
              <input className="form-control" value={operationSearch} onChange={(e) => setOperationSearch(e.target.value)} placeholder="Buscar operacion" />
            </Field>
            <Field label="Producto">
              <select className="form-select" value={operationsFilters.producto} onChange={(e) => onOperationsChange("producto", e.target.value)}>
                <option value="">Todos</option>
                {options.productos_detalle.map((v) => (
                  <option key={v} value={v}>{v}</option>
                ))}
              </select>
            </Field>
            <Field label="Ciclo">
              <select className="form-select" value={operationsFilters.ciclo} onChange={(e) => onOperationsChange("ciclo", e.target.value)}>
                <option value="">Todos</option>
                {options.ciclos.map((v) => (
                  <option key={v} value={v}>{v}</option>
                ))}
              </select>
            </Field>
            <Field label="Contenido">
              <select className="form-select" value={operationsFilters.contenido} onChange={(e) => onOperationsChange("contenido", e.target.value)}>
                <option value="">Todos</option>
                <option value="1">Si</option>
                <option value="0">No</option>
              </select>
            </Field>
            <Field label="Filas">
              <select
                className="form-select"
                value={operationsPageSize}
                onChange={(e) => {
                  setOperationsPageSize(Number(e.target.value));
                  setOperationsPage(1);
                }}
              >
                <option value={100}>100</option>
                <option value={250}>250</option>
                <option value={500}>500</option>
              </select>
            </Field>
          </>
        )}
      </FilterBar>

      {error && <div className="alert alert-danger">{error}</div>}

      <div className="pd-tabbed">
        <ViewTabs
          value={view}
          onChange={setView}
          options={[
            { value: "general", label: "Vista General" },
            { value: "desglosada", label: "Vista Desglosada" },
            { value: "detalle", label: "Detalle" },
          ]}
        />
        <SectionCard
          bodyClassName=""
          footer={
            loading ? null : view === "detalle" ? (
              <Pagination
                summary={`Mostrando ${operationsFrom}-${operationsTo} de ${operationsTotal} operaciones. Pagina ${operationsPage} de ${operationsTotalPages}.`}
                onPrev={() => setOperationsPage((prev) => Math.max(1, prev - 1))}
                onNext={() => setOperationsPage((prev) => Math.min(operationsTotalPages, prev + 1))}
                prevDisabled={operationsPage <= 1 || loading}
                nextDisabled={operationsPage >= operationsTotalPages || loading}
              />
            ) : (
              <StatusLegend items={relativeLegendItems} />
            )
          }
        >
          {loading ? (
            <LoadingState />
          ) : view === "general" ? (
            <div className="pd-table-scroll">
              <table className="pd-table pd-table-compact pd-table-sticky-first">
                <thead>
                  <tr>
                    <th>Ejecutivo</th>
                    {generalHeaders.map((h) => (
                      <th key={h.key} className="pd-num">{h.label}</th>
                    ))}
                    <th>Producto Trabajado</th>
                    <th>Tramo</th>
                    <th className="pd-num pd-th-key">Cum Final</th>
                  </tr>
                </thead>
                <tbody>
                  {generalRows.map((row, idx) => (
                    <tr key={`${row.ejecutivo}-${idx}`} className={row.ejecutivo === "Total general" ? "pd-row-total" : undefined}>
                      <td>{row.ejecutivo}</td>
                      {generalHeaders.map((h) => (
                        <td key={`${row.ejecutivo}-${h.key}`} className="pd-num">{formatPct(row[h.key])}</td>
                      ))}
                      <td>{row.producto_trabajado ? productLabel[row.producto_trabajado] || row.producto_trabajado : "-"}</td>
                      <td>{row.tramo_trabajado || "-"}</td>
                      <td className="pd-num">
                        <span className={dotClassByThresholds(row.cumplimiento_final, generalThresholds)}>{formatPct(row.cumplimiento_final)}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : view === "desglosada" ? (
            <div>
              {detailBlocks.map((block) => (
                <section className="pd-subsection" key={block.producto}>
                  <div className="pd-subsection-head">
                    <h2 className="pd-section-title">{productLabel[block.producto] || block.producto}</h2>
                    <span className="pd-small pd-muted">
                      Meta: {block.totales_por_ciclo.map((tot) => `${tot.tramo} ${formatPct(tot.meta_contenido_pct)}`).join(" · ")}
                    </span>
                  </div>
                  <div className="pd-table-scroll">
                    <table className="pd-table pd-table-compact pd-table-sticky-first">
                      <thead>
                        <tr>
                          <th rowSpan={2}>Ejecutivo</th>
                          {block.ciclos.map((ciclo) => (
                            <th key={`${block.producto}-h-${ciclo}`} colSpan={4} className="pd-th-group pd-group-start">
                              {block.producto === "tarjeta" ? (Number(ciclo) === 0 ? "Ciclo 0" : "Multiciclo") : `Ciclo ${ciclo}`}
                            </th>
                          ))}
                          <th rowSpan={2} className="pd-num pd-th-key pd-group-start">Cumplimiento Final</th>
                        </tr>
                        <tr>
                          {block.ciclos.map((ciclo) => (
                            <Fragment key={`${block.producto}-sub-${ciclo}`}>
                              <th className="pd-num pd-group-start">Deuda Asignada</th>
                              <th className="pd-num">Saldo Contenido</th>
                              <th className="pd-num">% Contenido</th>
                              <th className="pd-num">Cump Meta</th>
                            </Fragment>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {block.pivot_rows.map((row) => (
                          <tr key={`${block.producto}-${row.ejecutivo}`}>
                            <td>{row.ejecutivo}</td>
                            {block.ciclos.map((ciclo) => {
                              const item = row.ciclos?.[String(ciclo)];
                              return (
                                <Fragment key={`${block.producto}-${row.ejecutivo}-cset-${ciclo}`}>
                                  <td className="pd-num pd-group-start">{item ? `$${formatMM(item.deuda_asignada)} MM` : ""}</td>
                                  <td className="pd-num">{item ? `$${formatMM(item.saldo_contenido)} MM` : ""}</td>
                                  <td className="pd-num">{item ? formatPct(item.porcentaje_contenido) : ""}</td>
                                  <td className="pd-num">
                                    {item ? <span className={productDotClass(block.producto, item.cumplimiento_meta)}>{formatPct(item.cumplimiento_meta)}</span> : ""}
                                  </td>
                                </Fragment>
                              );
                            })}
                            <td className="pd-num pd-group-start">
                              <span className={productDotClass(block.producto, row.cumplimiento_final)}>{formatPct(row.cumplimiento_final)}</span>
                            </td>
                          </tr>
                        ))}
                        <tr className="pd-row-total">
                          <td>Total general</td>
                          {block.ciclos.map((ciclo) => {
                            const tot = block.totales_por_ciclo.find((x) => x.ciclo === ciclo);
                            return (
                              <Fragment key={`${block.producto}-tot-set-${ciclo}`}>
                                <td className="pd-num pd-group-start">{tot ? `$${formatMM(tot.deuda_asignada)} MM` : ""}</td>
                                <td className="pd-num">{tot ? `$${formatMM(tot.saldo_contenido)} MM` : ""}</td>
                                <td className="pd-num">{tot ? formatPct(tot.porcentaje_contenido) : ""}</td>
                                <td className="pd-num">
                                  {tot ? <span className={productDotClass(block.producto, tot.cumplimiento_meta)}>{formatPct(tot.cumplimiento_meta)}</span> : ""}
                                </td>
                              </Fragment>
                            );
                          })}
                          <td className="pd-num pd-group-start">
                            <span className={productDotClass(block.producto, block.cumplimiento_final_bloque)}>{formatPct(block.cumplimiento_final_bloque)}</span>
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </section>
              ))}
            </div>
          ) : (
            <div className="pd-table-scroll">
              <table className="pd-table pd-table-compact">
                <thead>
                  <tr>
                    <th>Ejecutivo</th>
                    <th>Operacion</th>
                    <th>Contenido</th>
                    <th>Ciclo</th>
                    <th className="pd-num">Deuda</th>
                    <th>Producto</th>
                    <th>Usuario Gestion</th>
                    <th>Mejor Gestion</th>
                    <th>Fecha Gestion</th>
                    <th>Telefono</th>
                    <th>Fecha Compromiso</th>
                  </tr>
                </thead>
                <tbody>
                  {operationsRows.map((row, idx) => (
                    <tr key={`${row.operacion}-${idx}`}>
                      <td>{row.ejecutivo}</td>
                      <td>{row.operacion}</td>
                      <td>{yesNo(row.contenido)}</td>
                      <td>{row.ciclo ?? "-"}</td>
                      <td className="pd-num">${formatMoney(row.deuda)}</td>
                      <td>{row.producto || "-"}</td>
                      <td>{row.usuario_gestion || "SIN GESTION"}</td>
                      <td>{row.mejor_gestion || "-"}</td>
                      <td>{String(row.gestion_fecha || "").slice(0, 10) || "-"}</td>
                      <td>{row.telefono_gestion || "-"}</td>
                      <td>{String(row.fecha_compromiso || "").slice(0, 10) || "-"}</td>
                    </tr>
                  ))}
                  {!operationsRows.length && <EmptyRow colSpan={11} />}
                </tbody>
              </table>
            </div>
          )}
        </SectionCard>
      </div>
    </div>
  );
}
