import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { downloadGmMonthlyExcel, fetchGmBucket, fetchGmCycle, fetchGmDetail, fetchGmFilters } from "../api";

const initialFilters = {
  periodo: "",
  ejecutivo: "",
};
const initialDetailFilters = { op: "", bucket: "", contenido: "", normalizado: "" };

const bucketOrder = ["6 a 30", "31 a 60", "61 a 90", "91 a 150"];

function formatPct(value) {
  return `${Number(value || 0).toFixed(2)}%`;
}

function formatMoney(value) {
  return new Intl.NumberFormat("es-CL", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(Number(value || 0));
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

export default function GmPage() {
  const { user } = useAuth();
  const [view, setView] = useState("productividad");
  const [filters, setFilters] = useState(initialFilters);
  const [detailFilters, setDetailFilters] = useState(initialDetailFilters);
  const [options, setOptions] = useState({ periodos: [], ejecutivos: [] });
  const [rows, setRows] = useState([]);
  const [bucketRows, setBucketRows] = useState([]);
  const [detailRows, setDetailRows] = useState([]);
  const [detailSortDir, setDetailSortDir] = useState("desc");
  const [loading, setLoading] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState("");
  const canDownload = ["super_admin", "admin", "coordinador"].includes(user?.role || "");
  const hasActiveFilters =
    filters.ejecutivo ||
    detailFilters.op ||
    detailFilters.contenido ||
    detailFilters.normalizado ||
    detailFilters.bucket;
  
  function clearFilters() {
    setFilters((prev) => ({
      ...prev,
      ejecutivo: "",
    }));
    setDetailFilters(initialDetailFilters);
  }

  useEffect(() => {
    async function loadFilters() {
      try {
        const data = await fetchGmFilters();
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
    async function loadData() {
      if (!filters.periodo) {
        return;
      }

      setLoading(true);
      setError("");
      try {
        if (view === "detalle") {
          const detailData = await fetchGmDetail({ ...filters, ...detailFilters });
          setDetailRows(detailData);
        } else {
          const [cycleData, bucketData] = await Promise.all([
            fetchGmCycle(filters),
            fetchGmBucket({ periodo: filters.periodo }),
          ]);
          setRows(cycleData);
          setBucketRows(bucketData);
        }
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }

    loadData();
  }, [filters, detailFilters, view]);

  const metaByBucket = useMemo(() => {
    const map = new Map();
    rows.forEach((row) => {
      if (!map.has(row.bucket)) {
        map.set(row.bucket, row);
      }
    });
    return map;
  }, [rows]);

  const totalRow = useMemo(() => {
    if (!rows.length) {
      return null;
    }

    const deuda = rows.reduce((acc, row) => acc + Number(row.deuda_asignada || 0), 0);
    const saldoContenido = rows.reduce((acc, row) => acc + Number(row.saldo_contenido || 0), 0);
    const saldoNormalizado = rows.reduce((acc, row) => acc + Number(row.saldo_normalizado || 0), 0);
    const ponderado = rows.reduce((acc, row) => acc + Number(row.cumplimiento_final || 0) * Number(row.deuda_asignada || 0), 0);

    return {
      ejecutivo: "Total general",
      bucket: "Todos",
      deuda_asignada: deuda,
      saldo_contenido: saldoContenido,
      porcentaje_contencion: deuda ? (saldoContenido / deuda) * 100 : 0,
      porcentaje_normalizado: deuda ? (saldoNormalizado / deuda) * 100 : 0,
      cumplimiento_final: deuda ? ponderado / deuda : 0,
    };
  }, [rows]);

  const dynamicThresholds = useMemo(() => {
    const sourceRows = view === "bucket" ? bucketRows.filter((row) => row.bucket !== "Total general") : rows;
    const dynamicValues = sourceRows
      .map((row) => Number(row.cumplimiento_final || 0))
      .filter((value) => Number.isFinite(value))
      .sort((a, b) => a - b);

    if (!dynamicValues.length) {
      return { p33: 0, p66: 0 };
    }

    return {
      p33: percentile(dynamicValues, 0.33),
      p66: percentile(dynamicValues, 0.66),
    };
  }, [rows, bucketRows, view]);

  function dynamicComplianceClass(value) {
    const num = Number(value || 0);
    if (num >= dynamicThresholds.p66) {
      return "gm-dot gm-dot-ok";
    }
    if (num >= dynamicThresholds.p33) {
      return "gm-dot gm-dot-warn";
    }
    return "gm-dot gm-dot-bad";
  }

  function onChange(name, value) {
    setFilters((prev) => ({ ...prev, [name]: value }));
  }

  function onDetailChange(name, value) {
    setDetailFilters((prev) => ({ ...prev, [name]: value }));
  }

  const sortedDetailRows = useMemo(() => {
    return [...detailRows].sort((a, b) => {
      const av = Number(a.peso_bucket_pct || 0);
      const bv = Number(b.peso_bucket_pct || 0);
      return detailSortDir === "asc" ? av - bv : bv - av;
    });
  }, [detailRows, detailSortDir]);

  function toggleDetailSort() {
    setDetailSortDir((prev) => (prev === "desc" ? "asc" : "desc"));
  }

  async function onDownload() {
    if (!filters.periodo) {
      return;
    }

    setDownloading(true);
    setError("");
    try {
      const { blob, filename } = await downloadGmMonthlyExcel(filters.periodo);
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      setError(err.message || "No se pudo descargar el Excel");
    } finally {
      setDownloading(false);
    }
  }

  return (
    <div className="container-fluid py-4 app-shell gm-page">
      <div className="d-flex justify-content-between align-items-center mb-3">
        <div>
          <h1 className="h3 m-0">GM - Productividad</h1>
          <Link to="/productividad" className="small text-decoration-none">
            Volver al Home
          </Link>
        </div>
        <div className="btn-group">
          <button className={`btn btn-${view === "productividad" ? "primary" : "outline-primary"}`} onClick={() => setView("productividad")}>
            Productividad
          </button>
          <button className={`btn btn-${view === "bucket" ? "primary" : "outline-primary"}`} onClick={() => setView("bucket")}>
            Bucket
          </button>
          <button className={`btn btn-${view === "detalle" ? "primary" : "outline-primary"}`} onClick={() => setView("detalle")}>
            Detalle
          </button>
          {canDownload && (
            <button className="btn btn-success" onClick={onDownload} disabled={!filters.periodo || downloading}>
              {downloading ? "Descargando..." : "Descargar Excel"}
            </button>
          )}
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
                  <input className="form-control" value={detailFilters.op} onChange={(e) => onDetailChange("op", e.target.value)} placeholder="Buscar OP" />
                </div>
                <div className="col-12 col-md-2">
                  <label className="form-label">Bucket</label>
                  <select className="form-select" value={detailFilters.bucket} onChange={(e) => onDetailChange("bucket", e.target.value)}>
                    <option value="">Todos</option>
                    {bucketOrder.map((v) => (
                      <option key={v} value={v}>
                        {v}
                      </option>
                    ))}
                  </select>
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
              </>
            )}
            {view === "bucket" && <div className="col-12 col-md-4 small text-muted d-flex align-items-end">La vista bucket consolida todos los ejecutivos del periodo.</div>}
            <div className="col-12 col-md-auto d-flex align-items-end">
              <button className="btn btn-outline-secondary w-100" onClick={clearFilters} disabled={!hasActiveFilters || loading}>
                Limpiar filtros
              </button>
            </div>            
          </div>
        </div>
      </div>

      {view !== "detalle" && (
        <div className="card shadow-sm mb-3 gm-meta-card">
          <div className="card-body table-responsive p-0">
            <table className="table mb-0 gm-meta-table">
              <thead>
                <tr>
                  <th rowSpan={2}>Bucket</th>
                  <th colSpan={2}>Metas</th>
                  <th colSpan={2}>Ponderador</th>
                </tr>
                <tr>
                  <th>% contencion</th>
                  <th>% normalizacion</th>
                  <th>% contencion</th>
                  <th>% normalizacion</th>
                </tr>
              </thead>
              <tbody>
                {bucketOrder.map((bucket) => {
                  const meta = metaByBucket.get(bucket);
                  return (
                    <tr key={bucket}>
                      <td>{bucket}</td>
                      <td>{formatPct(meta?.meta_contencion_pct)}</td>
                      <td>{formatPct(meta?.meta_normalizacion_pct)}</td>
                      <td>{formatPct(meta?.ponderador_contencion_pct)}</td>
                      <td>{formatPct(meta?.ponderador_normalizacion_pct)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {error && <div className="alert alert-danger">{error}</div>}

      <div className="card shadow-sm">
        <div className="card-body table-responsive">
          {loading ? (
            <div className="text-center py-4">Cargando...</div>
          ) : view === "productividad" ? (
            <table className="table table-striped table-hover align-middle gm-data-table">
              <thead>
                <tr>
                  <th>Ejecutivos</th>
                  <th>Bucket</th>
                  <th>Deuda Asignada</th>
                  <th>Saldo Contenido</th>
                  <th>% Contenido</th>
                  <th>% Normalizado</th>
                  <th>Cumplimiento de meta</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, idx) => (
                  <tr key={`${row.ejecutivo}-${row.bucket}-${idx}`}>
                    <td>{row.ejecutivo}</td>
                    <td>{row.bucket}</td>
                    <td>${formatMoney(row.deuda_asignada)} M</td>
                    <td>${formatMoney(row.saldo_contenido)} M</td>
                    <td>{formatPct(row.porcentaje_contencion)}</td>
                    <td>{formatPct(row.porcentaje_normalizado)}</td>
                    <td className="fw-semibold">
                      <span className={dynamicComplianceClass(row.cumplimiento_final)} /> {formatPct(row.cumplimiento_final)}
                    </td>
                  </tr>
                ))}
                {totalRow && (
                  <tr className="table-primary fw-semibold">
                    <td>{totalRow.ejecutivo}</td>
                    <td>{totalRow.bucket}</td>
                    <td>${formatMoney(totalRow.deuda_asignada)} M</td>
                    <td>${formatMoney(totalRow.saldo_contenido)} M</td>
                    <td>{formatPct(totalRow.porcentaje_contencion)}</td>
                    <td>{formatPct(totalRow.porcentaje_normalizado)}</td>
                    <td>
                      <span className={dynamicComplianceClass(totalRow.cumplimiento_final)} /> {formatPct(totalRow.cumplimiento_final)}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          ) : view === "bucket" ? (
            <table className="table table-striped table-hover align-middle gm-data-table">
              <thead>
                <tr>
                  <th>Bucket</th>
                  <th>Deuda Asignada</th>
                  <th>Saldo Contenido</th>
                  <th>% Contenido</th>
                  <th>% Normalizado</th>
                  <th>Meta Cont.</th>
                  <th>Meta Norm.</th>
                  <th>Cumplimiento de meta</th>
                </tr>
              </thead>
              <tbody>
                {bucketRows.map((row, idx) => (
                  <tr key={`${row.bucket}-${idx}`} className={row.bucket === "Total general" ? "table-primary fw-semibold" : ""}>
                    <td>{row.bucket}</td>
                    <td>${formatMoney(row.deuda_asignada)} M</td>
                    <td>${formatMoney(row.saldo_contenido)} M</td>
                    <td>{formatPct(row.porcentaje_contencion)}</td>
                    <td>{formatPct(row.porcentaje_normalizado)}</td>
                    <td>{row.bucket === "Total general" ? "-" : formatPct(row.meta_contencion_pct)}</td>
                    <td>{row.bucket === "Total general" ? "-" : formatPct(row.meta_normalizacion_pct)}</td>
                    <td className="fw-semibold">
                      <span className={dynamicComplianceClass(row.cumplimiento_final)} /> {formatPct(row.cumplimiento_final)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <table className="table table-striped table-hover align-middle gm-data-table">
              <thead>
                <tr>
                  <th>Operacion</th>
                  <th>Bucket</th>
                  <th>Dias Mora</th>
                  <th>Deuda</th>
                  <th>
                    <button className="btn btn-link btn-sm p-0 text-white fw-semibold text-decoration-none" type="button" onClick={toggleDetailSort}>
                      Peso % {detailSortDir === "desc" ? "DESC" : "ASC"}
                    </button>
                  </th>
                  <th>Cuota</th>
                  <th>Ejecutivo</th>
                  <th>Contenido</th>
                  <th>Normalizado</th>
                  <th>Telefono Gestion</th>
                </tr>
              </thead>
              <tbody>
                {sortedDetailRows.map((row, idx) => (
                  <tr key={`${row.op}-${idx}`}>
                    <td>{row.op}</td>
                    <td>{row.bucket}</td>
                    <td>{row.dias_de_mora}</td>
                    <td>${formatMoney(row.deuda)}</td>
                    <td>{formatPct(row.peso_bucket_pct)}</td>
                    <td>${formatMoney(row.cuota)}</td>
                    <td>{row.ejecutivo}</td>
                    <td>{Number(row.contenido || 0) === 1 ? "Si" : "No"}</td>
                    <td>{Number(row.normalizado || 0) === 1 ? "Si" : "No"}</td>
                    <td>{row.telefono_gestion}</td>
                  </tr>
                ))}
                {!sortedDetailRows.length && (
                  <tr>
                    <td colSpan={10} className="text-center text-muted py-4">
                      Sin datos para los filtros seleccionados.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          )}
        </div>
      </div>
      {view !== "detalle" && (
        <div className="mt-1 small text-muted">
          Umbrales dinamicos: Rojo &lt; {formatPct(dynamicThresholds.p33)} | Amarillo &gt;= {formatPct(dynamicThresholds.p33)} y &lt; {formatPct(dynamicThresholds.p66)} | Verde &gt;= {formatPct(dynamicThresholds.p66)}
        </div>
      )}
    </div>
  );
}
