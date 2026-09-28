import { Fragment, useEffect, useMemo, useState } from "react";
import { fetchSthDetail, fetchSthFilters, fetchSthGeneral, fetchSthMetas, fetchSthOperationsDetail } from "../api";
import { EmptyRow, Field, FilterBar, LoadingState, MetasBlock, MetasButton, MetasDrawer, PageHeader, Pagination, SectionCard, StatusLegend, ViewTabs, cumplimientoClass, cumplimientoLegendItems, phoenixGrupalAlFinal, exportFileName } from "../components/productividad/ui";

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

// El periodo se muestra como yyyy-mm; el valor que va al backend no cambia.
function formatPeriodo(value) {
  return String(value || "").slice(0, 7);
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
  const [metasOpen, setMetasOpen] = useState(false);
  const [metas, setMetas] = useState([]);

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

  // Al cambiar el periodo, el filtro de ejecutivo solo ofrece los carterizados ese mes.
  useEffect(() => {
    if (!filters.periodo) {
      return;
    }
    fetchSthFilters(filters.periodo)
      .then((data) => {
        const disponibles = data.ejecutivos || [];
        setOptions((prev) => ({ ...prev, ejecutivos: disponibles }));
        setFilters((prev) => (prev.ejecutivo && !disponibles.includes(prev.ejecutivo) ? { ...prev, ejecutivo: "" } : prev));
      })
      .catch((err) => setError(err.message));
  }, [filters.periodo]);

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

  // La vista general no muestra la fila "Total general" que envia el backend.
  const generalDataRows = useMemo(() => generalRows.filter((row) => row.ejecutivo !== "Total general"), [generalRows]);

    // Las metas se cargan al abrir el panel, para el periodo seleccionado.
  useEffect(() => {
    if (!metasOpen || !filters.periodo) {
      return;
    }
    fetchSthMetas(filters)
      .then(setMetas)
      .catch((err) => setError(err.message));
  }, [metasOpen, filters.periodo]);

  function renderMetasDrawer() {
    const productos = Array.from(new Set(metas.map((meta) => meta.producto)));
    return (
      <MetasDrawer open={metasOpen} onClose={() => setMetasOpen(false)} subtitle={`Vigentes para ${formatPeriodo(filters.periodo) || "N/D"}`}>
        {productos.length ? (
          <div className="iv-drawer-grid">
            {productos.map((producto, idx) => (
              <MetasBlock key={producto} title={producto} accent={idx % 2 === 0 ? "consumo" : "hipot"}>
                <table className="pd-table pd-table-plain pd-table-compact pd-table-static">
                  <thead>
                    <tr>
                      <th>Tramo</th>
                      <th className="pd-num">Meta</th>
                      <th className="pd-num">Pondera</th>
                    </tr>
                  </thead>
                  <tbody>
                    {metas
                      .filter((meta) => meta.producto === producto)
                      .map((meta) => (
                        <tr key={`${producto}-${meta.tramo}`}>
                          <td>{meta.tramo}</td>
                          <td className="pd-num pd-cell-strong">{formatPct(meta.meta_contenido_pct)}</td>
                          <td className="pd-num">{formatPct(meta.ponderador_nivel_1_pct)}</td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </MetasBlock>
            ))}
          </div>
        ) : (
          <div className="alert alert-light border">No hay metas cargadas para este mes.</div>
        )}
      </MetasDrawer>
    );
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
          <>
            {view === "detalle" && (
              <button type="button" className="pd-btn pd-btn-ghost" onClick={clearOperationsFilters} disabled={!hasOperationsFilters || loading}>
                <i className="bi bi-x-circle" aria-hidden="true" /> Limpiar filtros
              </button>
            )}
            <MetasButton onClick={() => setMetasOpen(true)} />
          </>
        }
      >
        <Field label="Periodo">
          <select className="form-select" value={filters.periodo} onChange={(e) => onChange("periodo", e.target.value)}>
            {options.periodos.map((v) => (
              <option key={v} value={v}>
                {formatPeriodo(v)}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Ejecutivo">
          <select className="form-select" value={filters.ejecutivo} onChange={(e) => onChange("ejecutivo", e.target.value)}>
            <option value="">Todos</option>
            {options.ejecutivos.map((v) => (
              <option key={v} value={v}>
                {String(v).toUpperCase()}
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

      {renderMetasDrawer()}

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
          exportName={exportFileName("STH", view, formatPeriodo(filters.periodo))}
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
              <StatusLegend items={cumplimientoLegendItems} />
            )
          }
        >
          {loading ? (
            <LoadingState />
          ) : view === "general" ? (
            <div className="pd-table-scroll">
              <table className="pd-table">
                <thead>
                  <tr>
                    <th rowSpan={2}>Ejecutivo</th>
                    <th colSpan={generalHeaders.length} className="pd-th-group-1 pd-group-start">Cumplimiento por producto</th>
                    <th colSpan={2} className="pd-th-group-2 pd-group-start">Producto trabajado</th>
                    <th rowSpan={2} className="pd-num pd-th-key pd-group-start">Cumplimiento Final</th>
                  </tr>
                  <tr>
                    {generalHeaders.map((h, idx) => (
                      <th key={h.key} className={`pd-num pd-th-sub-1${idx === 0 ? " pd-group-start" : ""}`}>{productLabel[h.key]}</th>
                    ))}
                    <th className="pd-th-sub-2 pd-group-start">Producto</th>
                    <th className="pd-th-sub-2">Tramo</th>
                  </tr>
                </thead>
                <tbody>
                  {phoenixGrupalAlFinal(generalDataRows).map((row, idx) => {
                    return (
                      <tr key={`${row.ejecutivo}-${idx}`}>
                        <td className="pd-cell-ejecutivo">{row.ejecutivo}</td>
                        {generalHeaders.map((h, hIdx) => (
                          <td key={`${row.ejecutivo}-${h.key}`} className={`pd-num${hIdx === 0 ? " pd-group-start" : ""}`}>
                            {row[h.key] === null || row[h.key] === undefined ? (
                              <span className="pd-cell-muted">—</span>
                            ) : (
                              <span className={cumplimientoClass(row[h.key])}>{formatPct(row[h.key])}</span>
                            )}
                          </td>
                        ))}
                        <td className="pd-group-start">{row.producto_trabajado ? productLabel[row.producto_trabajado] || row.producto_trabajado : "-"}</td>
                        <td>{row.tramo_trabajado || "-"}</td>
                        <td className="pd-num pd-group-start">
                          <span className={cumplimientoClass(row.cumplimiento_final)}>{formatPct(row.cumplimiento_final)}</span>
                        </td>
                      </tr>
                    );
                  })}
                  {!generalDataRows.length && <EmptyRow colSpan={generalHeaders.length + 4} />}
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
                    <table className="pd-table pd-table-compact pd-table-fit">
                      <thead>
                        <tr>
                          <th rowSpan={2}>Ejecutivo</th>
                          {block.ciclos.map((ciclo, cIdx) => (
                            <th key={`${block.producto}-h-${ciclo}`} colSpan={3} className={`pd-th-group-${(cIdx % 2) + 1} pd-group-start`}>
                              {block.producto === "tarjeta" ? (Number(ciclo) === 0 ? "Ciclo 0" : "Multiciclo") : `Ciclo ${ciclo}`}
                            </th>
                          ))}
                          <th rowSpan={2} className="pd-num pd-th-key pd-group-start">Cumplimiento Final</th>
                        </tr>
                        <tr>
                          {block.ciclos.map((ciclo, cIdx) => (
                            <Fragment key={`${block.producto}-sub-${ciclo}`}>
                              <th className={`pd-num pd-th-sub-${(cIdx % 2) + 1} pd-group-start`}>Deuda Asignada</th>
                              <th className={`pd-num pd-th-sub-${(cIdx % 2) + 1}`}>% Contenido</th>
                              <th className={`pd-num pd-th-sub-${(cIdx % 2) + 1}`}>Cump Meta</th>
                            </Fragment>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {phoenixGrupalAlFinal(block.pivot_rows).map((row) => (
                          <tr key={`${block.producto}-${row.ejecutivo}`}>
                            <td className="pd-cell-ejecutivo">{row.ejecutivo}</td>
                            {block.ciclos.map((ciclo) => {
                              const item = row.ciclos?.[String(ciclo)];
                              return (
                                <Fragment key={`${block.producto}-${row.ejecutivo}-cset-${ciclo}`}>
                                  <td className="pd-num pd-group-start">{item ? `$${formatMM(item.deuda_asignada)} MM` : ""}</td>
                                  <td className="pd-num">
                                    {item ? formatPct(item.porcentaje_contenido) : ""}
                                    {item && <span className="pd-cell-sub">${formatMM(item.saldo_contenido)} MM cont.</span>}
                                  </td>
                                  <td className="pd-num">
                                    {item ? <span className={cumplimientoClass(item.cumplimiento_meta)}>{formatPct(item.cumplimiento_meta)}</span> : ""}
                                  </td>
                                </Fragment>
                              );
                            })}
                            <td className="pd-num pd-group-start">
                              <span className={cumplimientoClass(row.cumplimiento_final)}>{formatPct(row.cumplimiento_final)}</span>
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
                                <td className="pd-num">
                                  {tot ? formatPct(tot.porcentaje_contenido) : ""}
                                  {tot && <span className="pd-cell-sub">${formatMM(tot.saldo_contenido)} MM cont.</span>}
                                </td>
                                <td className="pd-num">
                                  {tot ? <span className={cumplimientoClass(tot.cumplimiento_meta)}>{formatPct(tot.cumplimiento_meta)}</span> : ""}
                                </td>
                              </Fragment>
                            );
                          })}
                          <td className="pd-num pd-group-start">
                            <span className={cumplimientoClass(block.cumplimiento_final_bloque)}>{formatPct(block.cumplimiento_final_bloque)}</span>
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
                      <td className="pd-cell-ejecutivo">{row.ejecutivo}</td>
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
