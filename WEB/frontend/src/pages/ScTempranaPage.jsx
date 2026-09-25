import { useEffect, useMemo, useState } from "react";
import { fetchScTempranaCycle, fetchScTempranaDetail, fetchScTempranaFilters, fetchScTempranaGeneral } from "../api";
import { EmptyRow, Field, FilterBar, LoadingState, PageHeader, Pagination, SectionCard, Segmented, StatusLegend, ViewTabs, relativeLegendItems } from "../components/productividad/ui";

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
    return "pd-status pd-status-success";
  }
  if (num >= thresholds.p33) {
    return "pd-status pd-status-warning";
  }
  return "pd-status pd-status-danger";
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
    <div className="pd-page">
      <PageHeader title="SC Temprana" subtitle="Productividad y cumplimiento de cartera temprana." />

      <FilterBar
        actions={
          <button type="button" className="pd-btn pd-btn-ghost" onClick={clearFilters} disabled={!hasActiveFilters || loading}>
            <i className="bi bi-x-circle" aria-hidden="true" /> Limpiar filtros
          </button>
        }
      >
        <Field label="Periodo">
          <select className="form-select" value={filters.periodo} onChange={(e) => onChange("periodo", e.target.value)}>
            {options.periodos.map((v) => (
              <option key={v} value={v}>
                {formatPeriodLabel(v)}
              </option>
            ))}
          </select>
        </Field>
        {view !== "detalle" && (
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
        )}
        {view === "detalle" && (
          <>
            <Field label="Operacion">
              <input className="form-control" value={operationSearch} onChange={(e) => setOperationSearch(e.target.value)} placeholder="Buscar operacion" />
            </Field>
            <Field label="Contenido">
              <select className="form-select" value={detailFilters.contenido} onChange={(e) => onDetailChange("contenido", e.target.value)}>
                <option value="">Todos</option>
                <option value="1">Si</option>
                <option value="0">No</option>
              </select>
            </Field>
            <Field label="Normalizado">
              <select className="form-select" value={detailFilters.normalizado} onChange={(e) => onDetailChange("normalizado", e.target.value)}>
                <option value="">Todos</option>
                <option value="1">Si</option>
                <option value="0">No</option>
              </select>
            </Field>
            <Field label="Usuario Gestion">
              <select className="form-select" value={detailFilters.usuario_gestion} onChange={(e) => onDetailChange("usuario_gestion", e.target.value)}>
                <option value="">Todos</option>
                {options.usuarios_gestion.map((item) => (
                  <option key={item.usuario} value={item.usuario}>
                    {item.usuario}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Tramo">
              <select className="form-select" value={detailFilters.tramo} onChange={(e) => onDetailChange("tramo", e.target.value)}>
                <option value="">Todos</option>
                <option value="C1">C1</option>
                <option value="C2">C2</option>
                {hasC3 && <option value="C3">C3</option>}
              </select>
            </Field>
            <Field label="Filas">
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
            { value: "general", label: "General" },
            { value: "ejecutivos", label: "Ejecutivos" },
            { value: "detalle", label: "Detalle" },
          ]}
        />
        <SectionCard
          bodyClassName=""
          footer={
            loading ? null : view === "ejecutivos" ? (
              <StatusLegend items={relativeLegendItems} />
            ) : view === "detalle" ? (
              <Pagination
                summary={`Mostrando ${detailFrom}-${detailTo} de ${detailTotal} operaciones. Pagina ${detailPage} de ${detailTotalPages}.`}
                onPrev={() => setDetailPage((prev) => Math.max(1, prev - 1))}
                onNext={() => setDetailPage((prev) => Math.min(detailTotalPages, prev + 1))}
                prevDisabled={detailPage <= 1 || loading}
                nextDisabled={detailPage >= detailTotalPages || loading}
              />
            ) : null
          }
        >
          {loading ? (
            <LoadingState />
          ) : view === "general" ? (
            <div className="pd-state">Sin informacion disponible para vista general.</div>
          ) : view === "ejecutivos" ? (
            <>
              {hasC3 && (
                <div className="pd-card-toolbar">
                  <span className="pd-label">Tramo</span>
                  <Segmented
                    value={executiveSubview}
                    onChange={setExecutiveSubview}
                    options={[
                      { value: "c1c2", label: "C1/C2" },
                      { value: "c3", label: "C3" },
                    ]}
                  />
                </div>
              )}
              <div className="pd-table-scroll">
                {executiveSubview === "c3" ? (
                  <table className="pd-table">
                    <thead>
                      <tr>
                        <th>Ejecutiva</th>
                        <th className="pd-num">Deuda Asignada</th>
                        <th className="pd-num">Monto Cont</th>
                        <th className="pd-num">% Cont</th>
                        <th className="pd-num pd-th-key">% cumplimiento</th>
                      </tr>
                    </thead>
                    <tbody>
                      {cycleDataRows
                        .filter((row) => Number(row.c3_deuda_asignada || 0) > 0 || Number(row.c3_monto_cont || 0) > 0)
                        .map((row) => (
                          <tr key={`${row.ejecutivo}-c3`}>
                            <td>{row.ejecutivo}</td>
                            <td className="pd-num">{formatMoney(row.c3_deuda_asignada)}</td>
                            <td className="pd-num">{formatMoney(row.c3_monto_cont)}</td>
                            <td className="pd-num">{formatPct(row.c3_porc_contenido)}</td>
                            <td className="pd-num">
                              <span className={dotClassByThresholds(row.c3_porc_aporte, c3Thresholds)}>{formatPct(row.c3_porc_aporte)}</span>
                            </td>
                          </tr>
                        ))}
                      {cycleTotalRow && (
                        <tr className="pd-row-total">
                          <td>{cycleTotalRow.ejecutivo}</td>
                          <td className="pd-num">{formatMoney(cycleTotalRow.c3_deuda_asignada)}</td>
                          <td className="pd-num">{formatMoney(cycleTotalRow.c3_monto_cont)}</td>
                          <td className="pd-num">{formatPct(cycleTotalRow.c3_porc_contenido)}</td>
                          <td className="pd-num">
                            <span className="pd-status pd-status-none">{formatPct(cycleTotalRow.c3_porc_aporte)}</span>
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                ) : (
                  <table className="pd-table">
                    <thead>
                      <tr>
                        <th rowSpan={2}>Ejecutiva</th>
                        <th colSpan={4} className="pd-th-group-1 pd-group-start">
                          Tramo C1
                        </th>
                        <th colSpan={4} className="pd-th-group-2 pd-group-start">
                          Tramo C2
                        </th>
                      </tr>
                      <tr>
                        <th className="pd-num pd-th-sub-1 pd-group-start">Deuda Asignada</th>
                        <th className="pd-num pd-th-sub-1">Monto Cont</th>
                        <th className="pd-num pd-th-sub-1">% Cont</th>
                        <th className="pd-num pd-th-sub-1">% cumplimiento</th>
                        <th className="pd-num pd-th-sub-2 pd-group-start">Deuda Asignada</th>
                        <th className="pd-num pd-th-sub-2">Monto Cont</th>
                        <th className="pd-num pd-th-sub-2">% Cont</th>
                        <th className="pd-num pd-th-sub-2">% cumplimiento</th>
                      </tr>
                    </thead>
                    <tbody>
                      {cycleDataRows.map((row) => (
                        <tr key={row.ejecutivo}>
                          <td>{row.ejecutivo}</td>
                          <td className="pd-num pd-group-start">{formatMoney(row.c1_deuda_asignada)}</td>
                          <td className="pd-num">{formatMoney(row.c1_monto_cont)}</td>
                          <td className="pd-num">{formatPct(row.c1_porc_contenido)}</td>
                          <td className="pd-num">
                            <span className={dotClassByThresholds(row.c1_porc_aporte, c1Thresholds)}>{formatPct(row.c1_porc_aporte)}</span>
                          </td>
                          <td className="pd-num pd-group-start">{formatMoney(row.c2_deuda_asignada)}</td>
                          <td className="pd-num">{formatMoney(row.c2_monto_cont)}</td>
                          <td className="pd-num">{formatPct(row.c2_porc_contenido)}</td>
                          <td className="pd-num">
                            <span className={dotClassByThresholds(row.c2_porc_aporte, c2Thresholds)}>{formatPct(row.c2_porc_aporte)}</span>
                          </td>
                        </tr>
                      ))}
                      {cycleTotalRow && (
                        <tr className="pd-row-total">
                          <td>{cycleTotalRow.ejecutivo}</td>
                          <td className="pd-num pd-group-start">{formatMoney(cycleTotalRow.c1_deuda_asignada)}</td>
                          <td className="pd-num">{formatMoney(cycleTotalRow.c1_monto_cont)}</td>
                          <td className="pd-num">{formatPct(cycleTotalRow.c1_porc_contenido)}</td>
                          <td className="pd-num">
                            <span className="pd-status pd-status-none">{formatPct(cycleTotalRow.c1_porc_aporte)}</span>
                          </td>
                          <td className="pd-num pd-group-start">{formatMoney(cycleTotalRow.c2_deuda_asignada)}</td>
                          <td className="pd-num">{formatMoney(cycleTotalRow.c2_monto_cont)}</td>
                          <td className="pd-num">{formatPct(cycleTotalRow.c2_porc_contenido)}</td>
                          <td className="pd-num">
                            <span className="pd-status pd-status-none">{formatPct(cycleTotalRow.c2_porc_aporte)}</span>
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                )}
              </div>
            </>
          ) : (
            <div className="pd-table-scroll">
              <table className="pd-table">
                <thead>
                  <tr>
                    <th>Operacion</th>
                    <th className="pd-num">Deuda</th>
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
                      <td className="pd-num">{formatMoney(row.deuda)}</td>
                      <td>{row.tramo}</td>
                      <td>{yesNo(row.contenido)}</td>
                      <td>{yesNo(row.normalizado)}</td>
                      <td>{row.usuario_gestion || "SIN GESTION"}</td>
                      <td>{row.respuesta_gestion || "-"}</td>
                      <td>{String(row.gestion_fecha || "").slice(0, 10) || "-"}</td>
                      <td>{row.telefono || "-"}</td>
                    </tr>
                  ))}
                  {!detailRows.length && <EmptyRow colSpan={9} />}
                </tbody>
              </table>
            </div>
          )}
        </SectionCard>
      </div>
    </div>
  );
}
