import { Fragment, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { fetchSthDetail, fetchSthFilters, fetchSthGeneral, fetchSthOperationsDetail } from "../api";

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
    return "gm-dot gm-dot-ok";
  }
  if (n >= thresholds.p33) {
    return "gm-dot gm-dot-warn";
  }
  return "gm-dot gm-dot-bad";
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
    <div className="container-fluid py-4 app-shell sth-page">
      <div className="d-flex justify-content-between align-items-center mb-3">
        <div>
          <h1 className="h3 m-0">STH - KPI Hipotecario</h1>
          <Link to="/productividad" className="small text-decoration-none">
            Volver al Home
          </Link>
        </div>
        <div className="btn-group">
          <button className={`btn btn-${view === "general" ? "warning" : "outline-warning"}`} onClick={() => setView("general")}>
            Vista General
          </button>
          <button className={`btn btn-${view === "desglosada" ? "warning" : "outline-warning"}`} onClick={() => setView("desglosada")}>
            Vista Desglosada
          </button>
          <button className={`btn btn-${view === "detalle" ? "warning" : "outline-warning"}`} onClick={() => setView("detalle")}>
            Detalle
          </button>
        </div>
      </div>

      <div className="card shadow-sm mb-3">
        <div className="card-body">
          <div className="row g-2">
            <div className="col-12 col-md-2">
              <label className="form-label">Periodo</label>
              <select className="form-select" value={filters.periodo} onChange={(e) => onChange("periodo", e.target.value)}>
                {options.periodos.map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
              </select>
            </div>
            <div className="col-12 col-md-3">
              <label className="form-label">Ejecutivo</label>
              <select className="form-select" value={filters.ejecutivo} onChange={(e) => onChange("ejecutivo", e.target.value)}>
                <option value="">Todos</option>
                {options.ejecutivos.map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
              </select>
            </div>
            {view === "detalle" && (
              <>
                <div className="col-12 col-md-2">
                  <label className="form-label">Operacion</label>
                  <input className="form-control" value={operationSearch} onChange={(e) => setOperationSearch(e.target.value)} placeholder="Buscar operacion" />
                </div>
                <div className="col-12 col-md-2">
                  <label className="form-label">Producto</label>
                  <select className="form-select" value={operationsFilters.producto} onChange={(e) => onOperationsChange("producto", e.target.value)}>
                    <option value="">Todos</option>
                    {options.productos_detalle.map((v) => (
                      <option key={v} value={v}>{v}</option>
                    ))}
                  </select>
                </div>
                <div className="col-12 col-md-2">
                  <label className="form-label">Ciclo</label>
                  <select className="form-select" value={operationsFilters.ciclo} onChange={(e) => onOperationsChange("ciclo", e.target.value)}>
                    <option value="">Todos</option>
                    {options.ciclos.map((v) => (
                      <option key={v} value={v}>{v}</option>
                    ))}
                  </select>
                </div>
                <div className="col-12 col-md-2">
                  <label className="form-label">Contenido</label>
                  <select className="form-select" value={operationsFilters.contenido} onChange={(e) => onOperationsChange("contenido", e.target.value)}>
                    <option value="">Todos</option>
                    <option value="1">Si</option>
                    <option value="0">No</option>
                  </select>
                </div>
                <div className="col-12 col-md-2">
                  <label className="form-label">Filas</label>
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
                </div>
                <div className="col-12 col-md-auto d-flex align-items-end">
                  <button className="btn btn-outline-secondary w-100" onClick={clearOperationsFilters} disabled={!hasOperationsFilters || loading}>
                    Limpiar filtros
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      {error && <div className="alert alert-danger">{error}</div>}

      <div className="card shadow-sm">
        <div className="card-body table-responsive sth-table-shell">
          {loading ? (
            <div className="text-center py-4">Cargando...</div>
          ) : view === "general" ? (
            <table className="table table-striped table-hover align-middle sth-general-table sth-compact-table">
              <thead>
                <tr>
                  <th>Ejecutivo</th>
                  {generalHeaders.map((h) => (
                    <th key={h.key}>{h.label}</th>
                  ))}
                  <th>Producto Trabajado</th>
                  <th>Tramo</th>
                  <th>Cum Final</th>
                </tr>
              </thead>
              <tbody>
                {generalRows.map((row, idx) => (
                  <tr key={`${row.ejecutivo}-${idx}`} className={row.ejecutivo === "Total general" ? "table-primary fw-semibold" : ""}>
                    <td>{row.ejecutivo}</td>
                    {generalHeaders.map((h) => (
                      <td key={`${row.ejecutivo}-${h.key}`}>{formatPct(row[h.key])}</td>
                    ))}
                    <td>{row.producto_trabajado ? productLabel[row.producto_trabajado] || row.producto_trabajado : "-"}</td>
                    <td>{row.tramo_trabajado || "-"}</td>
                    <td className="fw-semibold">
                      <span className={dotClassByThresholds(row.cumplimiento_final, generalThresholds)} /> {formatPct(row.cumplimiento_final)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : view === "desglosada" ? (
            <div className="sth-detail-wrap">
              {detailBlocks.map((block) => (
                <div className="mb-4" key={block.producto}>
                  <div className="sth-section-title">{productLabel[block.producto] || block.producto}</div>
                  <div className="small text-muted mb-1">
                    Meta: {block.totales_por_ciclo.map((tot) => `${tot.tramo} ${formatPct(tot.meta_contenido_pct)}`).join(" | ")}
                  </div>
                  <table className="table table-striped table-hover align-middle sth-detail-table sth-compact-table">
                    <thead>
                      <tr>
                        <th rowSpan={2}>Ejecutivo</th>
                        {block.ciclos.map((ciclo) => (
                          <th key={`${block.producto}-h-${ciclo}`} colSpan={4} className="text-center">
                            {block.producto === "tarjeta" ? (Number(ciclo) === 0 ? "Ciclo 0" : "Multiciclo") : `Ciclo ${ciclo}`}
                          </th>
                        ))}
                        <th rowSpan={2}>Cumplimiento Final</th>
                      </tr>
                      <tr>
                        {block.ciclos.map((ciclo) => (
                          <Fragment key={`${block.producto}-sub-${ciclo}`}>
                            <th>Deuda Asignada</th>
                            <th>Saldo Contenido</th>
                            <th>% Contenido</th>
                            <th>Cump Meta</th>
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
                                <td>{item ? `$${formatMM(item.deuda_asignada)} MM` : ""}</td>
                                <td>{item ? `$${formatMM(item.saldo_contenido)} MM` : ""}</td>
                                <td>{item ? formatPct(item.porcentaje_contenido) : ""}</td>
                                <td className="fw-semibold">
                                  {item ? (
                                    <>
                                      <span className={productDotClass(block.producto, item.cumplimiento_meta)} /> {formatPct(item.cumplimiento_meta)}
                                    </>
                                  ) : (
                                    ""
                                  )}
                                </td>
                              </Fragment>
                            );
                          })}
                          <td className="fw-semibold">
                            <span className={productDotClass(block.producto, row.cumplimiento_final)} /> {formatPct(row.cumplimiento_final)}
                          </td>
                        </tr>
                      ))}
                      <tr className="table-primary fw-semibold">
                        <td>Total general</td>
                        {block.ciclos.map((ciclo) => {
                          const tot = block.totales_por_ciclo.find((x) => x.ciclo === ciclo);
                          return (
                            <Fragment key={`${block.producto}-tot-set-${ciclo}`}>
                              <td>{tot ? `$${formatMM(tot.deuda_asignada)} MM` : ""}</td>
                              <td>{tot ? `$${formatMM(tot.saldo_contenido)} MM` : ""}</td>
                              <td>{tot ? formatPct(tot.porcentaje_contenido) : ""}</td>
                              <td>
                                {tot ? (
                                  <>
                                    <span className={productDotClass(block.producto, tot.cumplimiento_meta)} /> {formatPct(tot.cumplimiento_meta)}
                                  </>
                                ) : (
                                  ""
                                )}
                              </td>
                            </Fragment>
                          );
                        })}
                        <td>
                          <span className={productDotClass(block.producto, block.cumplimiento_final_bloque)} /> {formatPct(block.cumplimiento_final_bloque)}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              ))}
            </div>
          ) : (
            <>
              <table className="table table-striped table-hover align-middle sth-detail-table sth-compact-table">
                <thead>
                  <tr>
                    <th>Ejecutivo</th>
                    <th>Operacion</th>
                    <th>Contenido</th>
                    <th>Ciclo</th>
                    <th>Deuda</th>
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
                      <td>${formatMoney(row.deuda)}</td>
                      <td>{row.producto || "-"}</td>
                      <td>{row.usuario_gestion || "SIN GESTION"}</td>
                      <td>{row.mejor_gestion || "-"}</td>
                      <td>{String(row.gestion_fecha || "").slice(0, 10) || "-"}</td>
                      <td>{row.telefono_gestion || "-"}</td>
                      <td>{String(row.fecha_compromiso || "").slice(0, 10) || "-"}</td>
                    </tr>
                  ))}
                  {!operationsRows.length && (
                    <tr>
                      <td colSpan={11} className="text-center text-muted py-4">
                        Sin datos para los filtros seleccionados.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
              <div className="d-flex flex-column flex-md-row gap-2 justify-content-between align-items-md-center mt-2">
                <div className="small text-muted">
                  Mostrando {operationsFrom}-{operationsTo} de {operationsTotal} operaciones. Pagina {operationsPage} de {operationsTotalPages}.
                </div>
                <div className="btn-group">
                  <button className="btn btn-outline-warning" onClick={() => setOperationsPage((prev) => Math.max(1, prev - 1))} disabled={operationsPage <= 1 || loading}>
                    Anterior
                  </button>
                  <button className="btn btn-outline-warning" onClick={() => setOperationsPage((prev) => Math.min(operationsTotalPages, prev + 1))} disabled={operationsPage >= operationsTotalPages || loading}>
                    Siguiente
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
