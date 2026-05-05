import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { fetchGmBucket, fetchGmCycle, fetchGmFilters } from "../api";

const initialFilters = {
  periodo: "",
  ejecutivo: "",
};

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
  const [view, setView] = useState("detalle");
  const [filters, setFilters] = useState(initialFilters);
  const [options, setOptions] = useState({ periodos: [], ejecutivos: [] });
  const [rows, setRows] = useState([]);
  const [bucketRows, setBucketRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

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
        const [cycleData, bucketData] = await Promise.all([
          fetchGmCycle(filters),
          fetchGmBucket({ periodo: filters.periodo }),
        ]);
        setRows(cycleData);
        setBucketRows(bucketData);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }

    loadData();
  }, [filters]);

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

  return (
    <div className="container-fluid py-4 app-shell gm-page">
      <div className="d-flex justify-content-between align-items-center mb-3">
        <div>
          <h1 className="h3 m-0">GM - Productividad</h1>
          <Link to="/" className="small text-decoration-none">
            Volver al Home
          </Link>
        </div>
        <div className="btn-group">
          <button className={`btn btn-${view === "detalle" ? "primary" : "outline-primary"}`} onClick={() => setView("detalle")}>
            Vista Detalle
          </button>
          <button className={`btn btn-${view === "bucket" ? "primary" : "outline-primary"}`} onClick={() => setView("bucket")}>
            Vista Bucket
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
            {view === "bucket" && <div className="col-12 col-md-4 small text-muted d-flex align-items-end">La vista bucket consolida todos los ejecutivos del periodo.</div>}
          </div>
        </div>
      </div>

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

      {error && <div className="alert alert-danger">{error}</div>}

      <div className="card shadow-sm">
        <div className="card-body table-responsive">
          {loading ? (
            <div className="text-center py-4">Cargando...</div>
          ) : view === "detalle" ? (
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
          ) : (
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
          )}
        </div>
      </div>
      <div className="mt-1 small text-muted">
        Umbrales dinamicos: Rojo &lt; {formatPct(dynamicThresholds.p33)} | Amarillo &gt;= {formatPct(dynamicThresholds.p33)} y &lt; {formatPct(dynamicThresholds.p66)} | Verde &gt;= {formatPct(dynamicThresholds.p66)}
      </div>
    </div>
  );
}
