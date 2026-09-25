import React, { useEffect, useMemo, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { downloadGmMonthlyExcel, fetchGmBucket, fetchGmCycle, fetchGmDetail, fetchGmFilters } from "../api";
import { EmptyRow, Field, FilterBar, LoadingState, PageHeader, SectionCard, StatusLegend, ViewTabs, relativeLegendItems } from "../components/productividad/ui";

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
      return "pd-status pd-status-success";
    }
    if (num >= dynamicThresholds.p33) {
      return "pd-status pd-status-warning";
    }
    return "pd-status pd-status-danger";
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
    <div className="pd-page">
      <PageHeader
        title="General Motors"
        subtitle="Seguimiento y cumplimiento de GM por bucket de mora."
        actions={
          canDownload && view !== "detalle" && (
            <button type="button" className="pd-btn pd-btn-secondary" onClick={onDownload} disabled={!filters.periodo || downloading}>
              <i className="bi bi-download" aria-hidden="true" /> {downloading ? "Descargando..." : "Descargar Excel"}
            </button>
          )
        }
      />

      <FilterBar
        actions={
          <button type="button" className="pd-btn pd-btn-ghost" onClick={clearFilters} disabled={!hasActiveFilters || loading}>
            <i className="bi bi-x-circle" aria-hidden="true" /> Limpiar filtros
          </button>
        }
        note={view === "bucket" ? "La vista bucket consolida todos los ejecutivos del periodo." : null}
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
              <input className="form-control" value={detailFilters.op} onChange={(e) => onDetailChange("op", e.target.value)} placeholder="Buscar OP" />
            </Field>
            <Field label="Bucket">
              <select className="form-select" value={detailFilters.bucket} onChange={(e) => onDetailChange("bucket", e.target.value)}>
                <option value="">Todos</option>
                {bucketOrder.map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
              </select>
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
          </>
        )}
      </FilterBar>

      {view !== "detalle" && (
        <SectionCard title="Metas y ponderadores por bucket" className="pd-card-narrow" bodyClassName="">
          <div className="pd-table-scroll">
            <table className="pd-table pd-table-plain pd-table-compact pd-table-static">
              <thead>
                <tr>
                  <th rowSpan={2}>Bucket</th>
                  <th colSpan={2} className="pd-th-group pd-group-start">Metas</th>
                  <th colSpan={2} className="pd-th-group pd-group-start">Ponderador</th>
                </tr>
                <tr>
                  <th className="pd-num pd-group-start">% contencion</th>
                  <th className="pd-num">% normalizacion</th>
                  <th className="pd-num pd-group-start">% contencion</th>
                  <th className="pd-num">% normalizacion</th>
                </tr>
              </thead>
              <tbody>
                {bucketOrder.map((bucket) => {
                  const meta = metaByBucket.get(bucket);
                  return (
                    <tr key={bucket}>
                      <td>{bucket}</td>
                      <td className="pd-num pd-group-start">{formatPct(meta?.meta_contencion_pct)}</td>
                      <td className="pd-num">{formatPct(meta?.meta_normalizacion_pct)}</td>
                      <td className="pd-num pd-group-start">{formatPct(meta?.ponderador_contencion_pct)}</td>
                      <td className="pd-num">{formatPct(meta?.ponderador_normalizacion_pct)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </SectionCard>
      )}

      {error && <div className="alert alert-danger">{error}</div>}

      <div className="pd-tabbed">
        <ViewTabs
          value={view}
          onChange={setView}
          options={[
            { value: "productividad", label: "Productividad" },
            { value: "bucket", label: "Bucket" },
            { value: "detalle", label: "Detalle" },
          ]}
        />
        <SectionCard
          bodyClassName=""
          footer={
            view !== "detalle" && (
              <>
                <StatusLegend items={relativeLegendItems} />
                <span>
                  Umbrales dinámicos: bajo &lt; {formatPct(dynamicThresholds.p33)} · esperado &lt; {formatPct(dynamicThresholds.p66)} · sobre lo esperado ≥ {formatPct(dynamicThresholds.p66)}
                </span>
              </>
            )
          }
        >
          {loading ? (
            <LoadingState />
          ) : view === "productividad" ? (
            <div className="pd-table-scroll">
              <table className="pd-table">
                <thead>
                  <tr>
                    <th>Ejecutivos</th>
                    <th>Bucket</th>
                    <th className="pd-num">Deuda Asignada</th>
                    <th className="pd-num">Saldo Contenido</th>
                    <th className="pd-num">% Contenido</th>
                    <th className="pd-num">% Normalizado</th>
                    <th className="pd-num pd-th-key">Cumplimiento de meta</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, idx) => (
                    <tr key={`${row.ejecutivo}-${row.bucket}-${idx}`}>
                      <td>{row.ejecutivo}</td>
                      <td>{row.bucket}</td>
                      <td className="pd-num">${formatMoney(row.deuda_asignada)} M</td>
                      <td className="pd-num">${formatMoney(row.saldo_contenido)} M</td>
                      <td className="pd-num">{formatPct(row.porcentaje_contencion)}</td>
                      <td className="pd-num">{formatPct(row.porcentaje_normalizado)}</td>
                      <td className="pd-num">
                        <span className={dynamicComplianceClass(row.cumplimiento_final)}>{formatPct(row.cumplimiento_final)}</span>
                      </td>
                    </tr>
                  ))}
                  {totalRow && (
                    <tr className="pd-row-total">
                      <td>{totalRow.ejecutivo}</td>
                      <td>{totalRow.bucket}</td>
                      <td className="pd-num">${formatMoney(totalRow.deuda_asignada)} M</td>
                      <td className="pd-num">${formatMoney(totalRow.saldo_contenido)} M</td>
                      <td className="pd-num">{formatPct(totalRow.porcentaje_contencion)}</td>
                      <td className="pd-num">{formatPct(totalRow.porcentaje_normalizado)}</td>
                      <td className="pd-num">
                        <span className={dynamicComplianceClass(totalRow.cumplimiento_final)}>{formatPct(totalRow.cumplimiento_final)}</span>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          ) : view === "bucket" ? (
            <div className="pd-table-scroll">
              <table className="pd-table">
                <thead>
                  <tr>
                    <th>Bucket</th>
                    <th className="pd-num">Deuda Asignada</th>
                    <th className="pd-num">Saldo Contenido</th>
                    <th className="pd-num">% Contenido</th>
                    <th className="pd-num">% Normalizado</th>
                    <th className="pd-num">Meta Cont.</th>
                    <th className="pd-num">Meta Norm.</th>
                    <th className="pd-num pd-th-key">Cumplimiento de meta</th>
                  </tr>
                </thead>
                <tbody>
                  {bucketRows.map((row, idx) => (
                    <tr key={`${row.bucket}-${idx}`} className={row.bucket === "Total general" ? "pd-row-total" : undefined}>
                      <td>{row.bucket}</td>
                      <td className="pd-num">${formatMoney(row.deuda_asignada)} M</td>
                      <td className="pd-num">${formatMoney(row.saldo_contenido)} M</td>
                      <td className="pd-num">{formatPct(row.porcentaje_contencion)}</td>
                      <td className="pd-num">{formatPct(row.porcentaje_normalizado)}</td>
                      <td className="pd-num">{row.bucket === "Total general" ? "-" : formatPct(row.meta_contencion_pct)}</td>
                      <td className="pd-num">{row.bucket === "Total general" ? "-" : formatPct(row.meta_normalizacion_pct)}</td>
                      <td className="pd-num">
                        <span className={dynamicComplianceClass(row.cumplimiento_final)}>{formatPct(row.cumplimiento_final)}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="pd-table-scroll">
              <table className="pd-table">
                <thead>
                  <tr>
                    <th>Operacion</th>
                    <th>Bucket</th>
                    <th className="pd-num">Dias Mora</th>
                    <th className="pd-num">Deuda</th>
                    <th className="pd-num">
                      <button className="pd-th-sort" type="button" onClick={toggleDetailSort} title={detailSortDir === "desc" ? "Orden descendente" : "Orden ascendente"}>
                        Peso % <i className={`bi ${detailSortDir === "desc" ? "bi-sort-down" : "bi-sort-up"}`} aria-hidden="true" />
                      </button>
                    </th>
                    <th className="pd-num">Cuota</th>
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
                      <td className="pd-num">{row.dias_de_mora}</td>
                      <td className="pd-num">${formatMoney(row.deuda)}</td>
                      <td className="pd-num">{formatPct(row.peso_bucket_pct)}</td>
                      <td className="pd-num">${formatMoney(row.cuota)}</td>
                      <td>{row.ejecutivo}</td>
                      <td>{Number(row.contenido || 0) === 1 ? "Si" : "No"}</td>
                      <td>{Number(row.normalizado || 0) === 1 ? "Si" : "No"}</td>
                      <td>{row.telefono_gestion}</td>
                    </tr>
                  ))}
                  {!sortedDetailRows.length && <EmptyRow colSpan={10} />}
                </tbody>
              </table>
            </div>
          )}
        </SectionCard>
      </div>
    </div>
  );
}
