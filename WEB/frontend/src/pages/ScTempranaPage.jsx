import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { fetchScTempranaCycle, fetchScTempranaDetail, fetchScTempranaFilters, fetchScTempranaGeneral } from "../api";

const initialFilters = {
  periodo: "",
  ejecutivo: "",
};

const initialDetailFilters = {
  operacion: "",
  contenido: "",
  normalizado: "",
  usuario_gestion: "",
  tramo: "",
};

function formatPct(value) {
  return `${Number(value || 0).toFixed(2)}%`;
}

function formatMoney(value) {
  return `$${new Intl.NumberFormat("es-CL", { minimumFractionDigits: 0, maximumFractionDigits: 0 }).format(Number(value || 0))}`;
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
  const num = Number(value || 0);
  if (num >= thresholds.p66) {
    return "gm-dot gm-dot-ok";
  }
  if (num >= thresholds.p33) {
    return "gm-dot gm-dot-warn";
  }
  return "gm-dot gm-dot-bad";
}

function formatPeriodLabel(value) {
  const text = String(value || "").trim();
  if (!text) {
    return "";
  }

  if (/^\d{8}$/.test(text)) {
    return `${text.slice(0, 4)}-${text.slice(4, 6)}-${text.slice(6, 8)}`;
  }

  if (/^\d{6}$/.test(text)) {
    return `${text.slice(0, 4)}-${text.slice(4, 6)}`;
  }

  if (text.includes("-")) {
    const parts = text.split("-");
    if (parts.length >= 3) {
      const [year, month, day] = parts;
      return `${year}-${month}-${day}`;
    }
  }

  return text;
}

export default function ScTempranaPage() {
  const [view, setView] = useState("ejecutivos");
  const [executiveSubview, setExecutiveSubview] = useState("c1c2");
  const [filters, setFilters] = useState(initialFilters);
  const [detailFilters, setDetailFilters] = useState(initialDetailFilters);
  const [options, setOptions] = useState({ periodos: [], ejecutivos: [], usuarios_gestion: [] });
  const [generalRows, setGeneralRows] = useState([]);
  const [cycleRows, setCycleRows] = useState([]);
  const [detailRows, setDetailRows] = useState([]);
  const [detailTotal, setDetailTotal] = useState(0);
  const [detailPage, setDetailPage] = useState(1);
  const [detailPageSize, setDetailPageSize] = useState(100);
  const [operationSearch, setOperationSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const hasActiveFilters =
  filters.ejecutivo ||
  operationSearch ||
  detailFilters.operacion ||
  detailFilters.contenido ||
  detailFilters.normalizado ||
  detailFilters.usuario_gestion ||
  detailFilters.tramo;
  
  function clearFilters() {
    setFilters((prev) => ({
      ...prev,
      ejecutivo: "",
    }));
    setDetailFilters(initialDetailFilters);
    setOperationSearch("");
    setDetailPage(1);
  }

  useEffect(() => {
    async function loadFilters() {
      try {
        const data = await fetchScTempranaFilters();
        setOptions({
          periodos: data.periodos || [],
          ejecutivos: data.ejecutivos || [],
          usuarios_gestion: data.usuarios_gestion || [],
        });
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
      setDetailFilters((prev) => ({ ...prev, operacion: operationSearch.trim() }));
      setDetailPage(1);
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
          const detail = await fetchScTempranaDetail({ ...filters, ...detailFilters, page: detailPage, page_size: detailPageSize });
          setDetailRows(detail.data || []);
          setDetailTotal(Number(detail.total || 0));
        } else {
          const [general, cycle] = await Promise.all([fetchScTempranaGeneral(filters), fetchScTempranaCycle(filters)]);
          setGeneralRows(general);
          setCycleRows(cycle);
        }
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, [filters, detailFilters, detailPage, detailPageSize, view]);

  function onChange(name, value) {
    setFilters((prev) => ({ ...prev, [name]: value }));
    setDetailPage(1);
  }

  function onDetailChange(name, value) {
    setDetailFilters((prev) => ({ ...prev, [name]: value }));
    setDetailPage(1);
  }

  const cycleDataRows = useMemo(() => cycleRows.filter((row) => row.ejecutivo !== "Total"), [cycleRows]);
  const cycleTotalRow = useMemo(() => cycleRows.find((row) => row.ejecutivo === "Total") || null, [cycleRows]);
  const c3TotalCases = Number(cycleTotalRow?.c3_casos_base || 0);
  const hasC3 = c3TotalCases > 350;

  useEffect(() => {
    if (!hasC3 && executiveSubview === "c3") {
      setExecutiveSubview("c1c2");
    }
  }, [hasC3, executiveSubview]);

  const c1Thresholds = useMemo(() => {
    const values = cycleDataRows
      .map((row) => Number(row.c1_porc_aporte || 0))
      .filter((v) => Number.isFinite(v))
      .sort((a, b) => a - b);
    return {
      p33: percentile(values, 0.33),
      p66: percentile(values, 0.66),
    };
  }, [cycleDataRows]);

  const c2Thresholds = useMemo(() => {
    const values = cycleDataRows
      .map((row) => Number(row.c2_porc_aporte || 0))
      .filter((v) => Number.isFinite(v))
      .sort((a, b) => a - b);
    return {
      p33: percentile(values, 0.33),
      p66: percentile(values, 0.66),
    };
  }, [cycleDataRows]);

  const c3Thresholds = useMemo(() => {
    const values = cycleDataRows
      .filter((row) => Number(row.c3_deuda_asignada || 0) > 0 || Number(row.c3_monto_cont || 0) > 0)
      .map((row) => Number(row.c3_porc_aporte || 0))
      .filter((v) => Number.isFinite(v))
      .sort((a, b) => a - b);
    return {
      p33: percentile(values, 0.33),
      p66: percentile(values, 0.66),
    };
  }, [cycleDataRows]);

  const detailTotalPages = Math.max(1, Math.ceil(detailTotal / detailPageSize));
  const detailFrom = detailTotal ? (detailPage - 1) * detailPageSize + 1 : 0;
  const detailTo = detailTotal ? Math.min(detailPage * detailPageSize, detailTotal) : 0;

  return (
    <div className="container-fluid py-4 app-shell">
      <div className="d-flex justify-content-between align-items-center mb-3">
        <div>
          <h1 className="h3 m-0">SC Temprana - Productividad</h1>
          <Link to="/productividad" className="small text-decoration-none">
            Volver al Home
          </Link>
        </div>
        <div className="btn-group">
          <button className={`btn btn-${view === "general" ? "primary" : "outline-primary"}`} onClick={() => setView("general")}>
            General
          </button>
          <button className={`btn btn-${view === "ejecutivos" ? "primary" : "outline-primary"}`} onClick={() => setView("ejecutivos")}>
            Ejecutivos
          </button>
          <button className={`btn btn-${view === "detalle" ? "primary" : "outline-primary"}`} onClick={() => setView("detalle")}>
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
                    {formatPeriodLabel(v)}
                  </option>
                ))}
              </select>
            </div>
            {view !== "detalle" && (
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
            )}
            {view === "detalle" && (
              <>
                <div className="col-12 col-md-2">
                  <label className="form-label">Operacion</label>
                  <input className="form-control" value={operationSearch} onChange={(e) => setOperationSearch(e.target.value)} placeholder="Buscar operacion" />
                </div>
                <div className="col-12 col-md-2">
                  <label className="form-label">Contenido</label>
                  <select className="form-select" value={detailFilters.contenido} onChange={(e) => onDetailChange("contenido", e.target.value)}>
                    <option value="">Todos</option>
                    <option value="1">Si</option>
                    <option value="0">No</option>
                  </select>
                </div>
                <div className="col-12 col-md-2">
                  <label className="form-label">Normalizado</label>
                  <select className="form-select" value={detailFilters.normalizado} onChange={(e) => onDetailChange("normalizado", e.target.value)}>
                    <option value="">Todos</option>
                    <option value="1">Si</option>
                    <option value="0">No</option>
                  </select>
                </div>
                <div className="col-12 col-md-2">
                  <label className="form-label">Usuario Gestion</label>
                  <select className="form-select" value={detailFilters.usuario_gestion} onChange={(e) => onDetailChange("usuario_gestion", e.target.value)}>
                    <option value="">Todos</option>
                    {options.usuarios_gestion.map((item) => (
                      <option key={item.usuario} value={item.usuario}>
                        {item.usuario}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="col-12 col-md-2">
                  <label className="form-label">Tramo</label>
                  <select className="form-select" value={detailFilters.tramo} onChange={(e) => onDetailChange("tramo", e.target.value)}>
                    <option value="">Todos</option>
                    <option value="C1">C1</option>
                    <option value="C2">C2</option>
                    {hasC3 && <option value="C3">C3</option>}
                  </select>
                </div>
                <div className="col-12 col-md-2">
                  <label className="form-label">Filas</label>
                  <select
                    className="form-select"
                    value={detailPageSize}
                    onChange={(e) => {
                      setDetailPageSize(Number(e.target.value));
                      setDetailPage(1);
                    }}
                  >
                    <option value={100}>100</option>
                    <option value={250}>250</option>
                    <option value={500}>500</option>
                  </select>
                </div>
              </>
            )}
            <div className="col-12 col-md-auto d-flex align-items-end">
              <button className="btn btn-outline-secondary w-100" onClick={clearFilters} disabled={!hasActiveFilters || loading}>
                Limpiar filtros
              </button>
            </div>
          </div>
        </div>
      </div>

      {error && <div className="alert alert-danger">{error}</div>}

      <div className="card shadow-sm">
        <div className="card-body table-responsive">
          {loading ? (
            <div className="text-center py-4">Cargando...</div>
          ) : view === "general" ? (
            <div className="text-center py-4 text-muted">Sin informacion disponible para vista general.</div>
          ) : view === "ejecutivos" ? (
            <>
              {hasC3 && (
                <div className="btn-group mb-3">
                  <button className={`btn btn-sm btn-${executiveSubview === "c1c2" ? "primary" : "outline-primary"}`} onClick={() => setExecutiveSubview("c1c2")}>
                    C1/C2
                  </button>
                  <button className={`btn btn-sm btn-${executiveSubview === "c3" ? "primary" : "outline-primary"}`} onClick={() => setExecutiveSubview("c3")}>
                    C3
                  </button>
                </div>
              )}
              {executiveSubview === "c3" ? (
                <table className="table table-striped table-hover align-middle">
                  <thead>
                    <tr>
                      <th>Ejecutiva</th>
                      <th>Deuda Asignada</th>
                      <th>Monto Cont</th>
                      <th>% Cont</th>
                      <th>% cumplimiento</th>
                    </tr>
                  </thead>
                  <tbody>
                    {cycleDataRows
                      .filter((row) => Number(row.c3_deuda_asignada || 0) > 0 || Number(row.c3_monto_cont || 0) > 0)
                      .map((row) => (
                        <tr key={`${row.ejecutivo}-c3`}>
                          <td>{row.ejecutivo}</td>
                          <td>{formatMoney(row.c3_deuda_asignada)}</td>
                          <td>{formatMoney(row.c3_monto_cont)}</td>
                          <td>{formatPct(row.c3_porc_contenido)}</td>
                          <td className="fw-semibold">
                            <span className={dotClassByThresholds(row.c3_porc_aporte, c3Thresholds)} /> {formatPct(row.c3_porc_aporte)}
                          </td>
                        </tr>
                      ))}
                    {cycleTotalRow && (
                      <tr className="table-primary fw-semibold">
                        <td>{cycleTotalRow.ejecutivo}</td>
                        <td>{formatMoney(cycleTotalRow.c3_deuda_asignada)}</td>
                        <td>{formatMoney(cycleTotalRow.c3_monto_cont)}</td>
                        <td>{formatPct(cycleTotalRow.c3_porc_contenido)}</td>
                        <td>{formatPct(cycleTotalRow.c3_porc_aporte)}</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              ) : (
                <table className="table table-striped table-hover align-middle">
              <thead>
                <tr>
                  <th rowSpan={2}>Ejecutiva</th>
                  <th colSpan={4} className="text-center">
                    Tramo C1
                  </th>
                  <th colSpan={4} className="text-center">
                    Tramo C2
                  </th>
                </tr>
                <tr>
                  <th>Deuda Asignada</th>
                  <th>Monto Cont</th>
                  <th>% Cont</th>
                  <th>% cumplimiento</th>
                  <th>Deuda Asignada</th>
                  <th>Monto Cont</th>
                  <th>% Cont</th>
                  <th>% cumplimiento</th>
                </tr>
              </thead>
              <tbody>
                {cycleDataRows.map((row) => (
                  <tr key={row.ejecutivo}>
                    <td>{row.ejecutivo}</td>
                    <td>{formatMoney(row.c1_deuda_asignada)}</td>
                    <td>{formatMoney(row.c1_monto_cont)}</td>
                    <td>{formatPct(row.c1_porc_contenido)}</td>
                    <td className="fw-semibold">
                      <span className={dotClassByThresholds(row.c1_porc_aporte, c1Thresholds)} /> {formatPct(row.c1_porc_aporte)}
                    </td>
                    <td>{formatMoney(row.c2_deuda_asignada)}</td>
                    <td>{formatMoney(row.c2_monto_cont)}</td>
                    <td>{formatPct(row.c2_porc_contenido)}</td>
                    <td className="fw-semibold">
                      <span className={dotClassByThresholds(row.c2_porc_aporte, c2Thresholds)} /> {formatPct(row.c2_porc_aporte)}
                    </td>
                  </tr>
                ))}
                {cycleTotalRow && (
                  <tr className="table-primary fw-semibold">
                    <td>{cycleTotalRow.ejecutivo}</td>
                    <td>{formatMoney(cycleTotalRow.c1_deuda_asignada)}</td>
                    <td>{formatMoney(cycleTotalRow.c1_monto_cont)}</td>
                    <td>{formatPct(cycleTotalRow.c1_porc_contenido)}</td>
                    <td>{formatPct(cycleTotalRow.c1_porc_aporte)}</td>
                    <td>{formatMoney(cycleTotalRow.c2_deuda_asignada)}</td>
                    <td>{formatMoney(cycleTotalRow.c2_monto_cont)}</td>
                    <td>{formatPct(cycleTotalRow.c2_porc_contenido)}</td>
                    <td>{formatPct(cycleTotalRow.c2_porc_aporte)}</td>
                  </tr>
                )}
              </tbody>
            </table>
              )}
            </>
          ) : (
            <>
              <table className="table table-striped table-hover align-middle">
                <thead>
                  <tr>
                    <th>Operacion</th>
                    <th>Deuda</th>
                    <th>Tramo</th>
                    <th>Contenido</th>
                    <th>Normalizado</th>
                    <th>Usuario Gestion</th>
                    <th>Respuesta Gestion</th>
                    <th>Gestion Fecha</th>
                    <th>Telefono</th>
                  </tr>
                </thead>
                <tbody>
                  {detailRows.map((row, idx) => (
                    <tr key={`${row.operacion}-${idx}`}>
                      <td>{row.operacion}</td>
                      <td>{formatMoney(row.deuda)}</td>
                      <td>{row.tramo}</td>
                      <td>{yesNo(row.contenido)}</td>
                      <td>{yesNo(row.normalizado)}</td>
                      <td>{row.usuario_gestion || "SIN GESTION"}</td>
                      <td>{row.respuesta_gestion || "-"}</td>
                      <td>{String(row.gestion_fecha || "").slice(0, 10) || "-"}</td>
                      <td>{row.telefono || "-"}</td>
                    </tr>
                  ))}
                  {!detailRows.length && (
                    <tr>
                      <td colSpan={9} className="text-center text-muted py-4">
                        Sin datos para los filtros seleccionados.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
              <div className="d-flex flex-column flex-md-row gap-2 justify-content-between align-items-md-center mt-2">
                <div className="small text-muted">
                  Mostrando {detailFrom}-{detailTo} de {detailTotal} operaciones. Pagina {detailPage} de {detailTotalPages}.
                </div>
                <div className="btn-group">
                  <button className="btn btn-outline-primary" onClick={() => setDetailPage((prev) => Math.max(1, prev - 1))} disabled={detailPage <= 1 || loading}>
                    Anterior
                  </button>
                  <button className="btn btn-outline-primary" onClick={() => setDetailPage((prev) => Math.min(detailTotalPages, prev + 1))} disabled={detailPage >= detailTotalPages || loading}>
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
