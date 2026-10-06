import React, { useEffect, useMemo, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { downloadGmMonthlyExcel, fetchGmBucket, fetchGmCycle, fetchGmDetail, fetchGmFilters } from "../api";
import { EmptyRow, Field, FilterBar, LoadingState, MetasBlock, MetasButton, MetasDrawer, PageHeader, SectionCard, Segmented, StatusLegend, ViewTabs, cumplimientoClass, cumplimientoLegendItems, phoenixGrupalAlFinal, exportFileName } from "../components/productividad/ui";

const initialFilters = {
  periodo: "",
  ejecutivo: "",
};
const initialDetailFilters = { op: "", bucket: "", contenido: "", normalizado: "" };

const bucketOrder = ["6 a 30", "31 a 60", "61 a 90", "91 a 150"];

function formatPct(value) {
  return `${Number(value || 0).toFixed(2)}%`;
}


// Los cumplimientos de meta se muestran sin decimales.
function formatCumpl(value) {
  return `${Number(value || 0).toFixed(0)}%`;
}

function formatMoney(value) {
  return new Intl.NumberFormat("es-CL", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(Number(value || 0));
}

// El periodo se muestra como yyyy-mm; el valor que va al backend no cambia.
function formatPeriodo(value) {
  return String(value || "").slice(0, 7);
}

export default function GmPage() {
  const { user } = useAuth();
  const [view, setView] = useState("productividad");
  const [bucketTab, setBucketTab] = useState(bucketOrder[0]);
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
  const [metasOpen, setMetasOpen] = useState(false);
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

  // Al cambiar el periodo, el filtro de ejecutivo solo ofrece los carterizados ese mes.
  useEffect(() => {
    if (!filters.periodo) {
      return;
    }
    fetchGmFilters(filters.periodo)
      .then((data) => {
        const disponibles = data.ejecutivos || [];
        setOptions((prev) => ({ ...prev, ejecutivos: disponibles }));
        setFilters((prev) => (prev.ejecutivo && !disponibles.includes(prev.ejecutivo) ? { ...prev, ejecutivo: "" } : prev));
      })
      .catch((err) => setError(err.message));
  }, [filters.periodo]);

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

  // Las metas salen de la vista bucket (todo el periodo), asi no dependen del filtro de ejecutivo.
  const metaByBucket = useMemo(() => {
    const map = new Map();
    bucketRows.forEach((row) => {
      if (!map.has(row.bucket)) {
        map.set(row.bucket, row);
      }
    });
    return map;
  }, [bucketRows]);

  // Vista productividad: una pestaña por bucket, con las filas de los ejecutivos de ese bucket.
  const bucketTabRows = useMemo(() => rows.filter((row) => row.bucket === bucketTab), [rows, bucketTab]);

  const bucketTotalRow = useMemo(() => {
    if (!bucketTabRows.length) {
      return null;
    }
    const deuda = bucketTabRows.reduce((acc, row) => acc + Number(row.deuda_asignada || 0), 0);
    const saldoContenido = bucketTabRows.reduce((acc, row) => acc + Number(row.saldo_contenido || 0), 0);
    const saldoNormalizado = bucketTabRows.reduce((acc, row) => acc + Number(row.saldo_normalizado || 0), 0);
    const ponderado = bucketTabRows.reduce((acc, row) => acc + Number(row.cumplimiento_final || 0) * Number(row.deuda_asignada || 0), 0);
    return {
      ejecutivo: "Total general",
      deuda_asignada: deuda,
      saldo_contenido: saldoContenido,
      porcentaje_contencion: deuda ? (saldoContenido / deuda) * 100 : 0,
      porcentaje_normalizado: deuda ? (saldoNormalizado / deuda) * 100 : 0,
      cumplimiento_final: deuda ? ponderado / deuda : 0,
    };
  }, [bucketTabRows]);

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

  function renderProductividadTable() {
    const groupClass = (bucketOrder.indexOf(bucketTab) % 2) + 1;
    const subHeaders = ["Deuda Asignada", "Saldo Contenido", "% Contenido", "% Normalizado", "Cumplimiento de meta"];
    return (
      <>
        <div className="pd-card-toolbar">
          <span className="pd-label">Bucket</span>
          <Segmented value={bucketTab} onChange={setBucketTab} options={bucketOrder.map((bucket) => ({ value: bucket, label: bucket }))} />
        </div>
        <div className="pd-table-scroll">
          <table className="pd-table">
            <thead>
              <tr>
                <th rowSpan={2}>Ejecutivo</th>
                <th colSpan={subHeaders.length} className={`pd-th-group-${groupClass} pd-group-start`}>
                  Bucket {bucketTab}
                </th>
              </tr>
              <tr>
                {subHeaders.map((label, idx) => (
                  <th key={label} className={`pd-num pd-th-sub-${groupClass}${idx === 0 ? " pd-group-start" : ""}`}>{label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {phoenixGrupalAlFinal(bucketTabRows).map((row, idx) => (
                <tr key={`${row.ejecutivo}-${idx}`}>
                  <td className="pd-cell-ejecutivo">{row.ejecutivo}</td>
                  <td className="pd-num pd-group-start">${formatMoney(row.deuda_asignada)} M</td>
                  <td className="pd-num">${formatMoney(row.saldo_contenido)} M</td>
                  <td className="pd-num">{formatPct(row.porcentaje_contencion)}</td>
                  <td className="pd-num">{formatPct(row.porcentaje_normalizado)}</td>
                  <td className="pd-num">
                    <span className={cumplimientoClass(row.cumplimiento_final)}>{formatCumpl(row.cumplimiento_final)}</span>
                  </td>
                </tr>
              ))}
              {!bucketTabRows.length && <EmptyRow colSpan={subHeaders.length + 1} text="Sin cartera en este bucket para los filtros seleccionados." />}
              {bucketTotalRow && (
                <tr className="pd-row-total">
                  <td>{bucketTotalRow.ejecutivo}</td>
                  <td className="pd-num pd-group-start">${formatMoney(bucketTotalRow.deuda_asignada)} M</td>
                  <td className="pd-num">${formatMoney(bucketTotalRow.saldo_contenido)} M</td>
                  <td className="pd-num">{formatPct(bucketTotalRow.porcentaje_contencion)}</td>
                  <td className="pd-num">{formatPct(bucketTotalRow.porcentaje_normalizado)}</td>
                  <td className="pd-num">
                    <span className="pd-status pd-status-none">{formatCumpl(bucketTotalRow.cumplimiento_final)}</span>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </>
    );
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
          <>
            <button type="button" className="pd-btn pd-btn-ghost" onClick={clearFilters} disabled={!hasActiveFilters || loading}>
              <i className="bi bi-x-circle" aria-hidden="true" /> Limpiar filtros
            </button>
            {view !== "detalle" && <MetasButton onClick={() => setMetasOpen(true)} />}
          </>
        }
        note={view === "bucket" ? "La vista bucket consolida todos los ejecutivos del periodo." : null}
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

      {error && <div className="alert alert-danger">{error}</div>}

      <MetasDrawer open={metasOpen} onClose={() => setMetasOpen(false)} subtitle={`Vigentes para ${formatPeriodo(filters.periodo) || "N/D"}`}>
        {metaByBucket.size ? (
          <div className="iv-drawer-grid iv-drawer-grid-single">
            {bucketOrder.map((bucket, idx) => {
              const meta = metaByBucket.get(bucket);
              return (
                <MetasBlock key={bucket} title={`Bucket ${bucket}`} accent={idx % 2 === 0 ? "consumo" : "hipot"}>
                  <table className="pd-table pd-table-plain pd-table-compact pd-table-static">
                    <thead>
                      <tr>
                        <th>Variable</th>
                        <th className="pd-num">Meta</th>
                        <th className="pd-num">Pondera</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr>
                        <td>Contención</td>
                        <td className="pd-num pd-cell-strong">{formatPct(meta?.meta_contencion_pct)}</td>
                        <td className="pd-num">{formatPct(meta?.ponderador_contencion_pct)}</td>
                      </tr>
                      <tr>
                        <td>Normalización</td>
                        <td className="pd-num pd-cell-strong">{formatPct(meta?.meta_normalizacion_pct)}</td>
                        <td className="pd-num">{formatPct(meta?.ponderador_normalizacion_pct)}</td>
                      </tr>
                    </tbody>
                  </table>
                </MetasBlock>
              );
            })}
          </div>
        ) : (
          <div className="alert alert-light border">No hay metas cargadas para este mes.</div>
        )}
      </MetasDrawer>

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
          exportName={exportFileName("GM", view === "productividad" ? `bucket ${bucketTab}` : view, formatPeriodo(filters.periodo))}
          bodyClassName=""
          footer={
            view !== "detalle" && (
              <StatusLegend items={cumplimientoLegendItems} />
            )
          }
        >
          {loading ? (
            <LoadingState />
          ) : view === "productividad" ? (
            renderProductividadTable()
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
                        <span className={cumplimientoClass(row.cumplimiento_final)}>{formatCumpl(row.cumplimiento_final)}</span>
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
                      <td className="pd-cell-ejecutivo">{row.ejecutivo}</td>
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
