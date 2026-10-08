import React, { useEffect, useRef, useState } from "react";
import { useAuth } from "../auth/AuthContext";

import { downloadLaAraucanaExcel, fetchLaAraucanaDetalle, fetchLaAraucanaFilters, fetchLaAraucanaNegocios, fetchLaAraucanaResumen } from "../api";
import { EmptyRow, Field, FilterBar, LoadingState, PageHeader, Pagination, SectionCard, StatusLegend, ViewTabs, aporteLegendItems, phoenixGrupalAlFinal, exportFileName } from "../components/productividad/ui";

function formatMoney(value) {
  return new Intl.NumberFormat("es-CL", { maximumFractionDigits: 0 }).format(Number(value || 0));
}

// Deuda en millones para que la tabla quepa sin scroll horizontal.
function formatMM(value) {
  return `$${new Intl.NumberFormat("es-CL", { maximumFractionDigits: 0 }).format(Number(value || 0) / 1000000)} MM`;
}

function formatRecovero(value) {
  return `$${formatMoney(value)}`;
}

function formatPct(value) {
  if (value === null || value === undefined) {
    return "";
  }
  return `${(Number(value || 0) * 100).toFixed(2)}%`;
}

const CARTERAS = [
  { key: "VIGENTE", label: "Vigente" },
  { key: "CASTIGO", label: "Castigo" },
  { key: "+365", label: "+365" },
];

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

// Una fila por ejecutivo con sus carteras como columnas.
// El aporte final es el recupero del ejecutivo en todas las carteras sobre el recupero total.
function pivotRows(rows) {
  const grouped = new Map();
  rows.forEach((row) => {
    const nombre = row.ejecutivo || "PHOENIX";
    const current = grouped.get(nombre) || { ejecutivo: nombre, carteras: {}, cumplimiento: 0 };
    current.carteras[row.tipo_cartera] = row;
    current.cumplimiento = Number(row.pct_aporte_final || 0);
    grouped.set(nombre, current);
  });
  return Array.from(grouped.values()).sort(
    (a, b) => (a.ejecutivo === "PHOENIX") - (b.ejecutivo === "PHOENIX") || a.ejecutivo.localeCompare(b.ejecutivo)
  );
}

function formatFecha(value) {
  const [year, month, day] = String(value || "").slice(0, 10).split("-");
  return day ? `${day}-${month}-${year}` : "";
}

// Los negocios se separan segun la deuda del folio.
const TRAMOS_DEUDA = [
  { key: "MENOR", label: "Deuda <= $1.000.000" },
  { key: "MAYOR", label: "Deuda > $1.000.000" },
];
const TRAMO_LABEL = Object.fromEntries(TRAMOS_DEUDA.map(({ key, label }) => [key, label]));

function emptyNegocio() {
  return { q_negocios: 0, recupero: 0 };
}

function addNegocio(target, row) {
  target.q_negocios += Number(row.q_negocios || 0);
  target.recupero += Number(row.recupero || 0);
}

// Negocios: una fila por ejecutivo con reprogramaciones y recupero por tramo de deuda.
// La fila "Total" acumula todos los ejecutivos.
function pivotNegocios(rows) {
  const nueva = (ejecutivo) => ({ ejecutivo, tramos: Object.fromEntries(TRAMOS_DEUDA.map(({ key }) => [key, emptyNegocio()])), total: emptyNegocio() });
  const grouped = new Map();
  const total = nueva("Total");
  rows.forEach((row) => {
    const current = grouped.get(row.ejecutivo) || nueva(row.ejecutivo);
    [current, total].forEach((item) => {
      if (item.tramos[row.tramo_deuda]) {
        addNegocio(item.tramos[row.tramo_deuda], row);
      }
      addNegocio(item.total, row);
    });
    grouped.set(row.ejecutivo, current);
  });
  return { rows: Array.from(grouped.values()).sort((a, b) => a.ejecutivo.localeCompare(b.ejecutivo)), total };
}

// El filtro de ejecutivo se aplica en el navegador sobre los datos del periodo ya cargados.
function porEjecutivo(rows, ejecutivo) {
  const buscado = String(ejecutivo || "").trim().toUpperCase();
  return buscado ? rows.filter((row) => String(row.ejecutivo || "").trim().toUpperCase() === buscado) : rows;
}

function totalByCartera(rows) {
  return Object.fromEntries(
    CARTERAS.map(({ key }) => {
      const items = rows.filter((row) => row.tipo_cartera === key);
      return [
        key,
        {
          deuda: items.reduce((acc, row) => acc + Number(row.deuda || 0), 0),
          recupero: items.reduce((acc, row) => acc + Number(row.recupero || 0), 0),
          pct_aporte: items.reduce((acc, row) => acc + Number(row.pct_aporte || 0), 0),
        },
      ];
    })
  );
}

export default function LaAraucanaPage() {
  const { user } = useAuth();
  const [filters, setFilters] = useState({ periodos: [], ejecutivos: [] });
  const [selected, setSelected] = useState({ periodo: "", cartera_crm: 531, ejecutivo: "" });
  const [view, setView] = useState("productividad");
  const [allRows, setAllRows] = useState([]);
  const [allNegocios, setAllNegocios] = useState({ rows: [], detalle: [], sin_gestion: null });
  const [detail, setDetail] = useState({ rows: [], total: 0, usuarios: [] });
  const [detailFilters, setDetailFilters] = useState({ buscar: "", tipo_cartera: "", usuario_gestion: "", con_pago: "" });
  const [detailSearch, setDetailSearch] = useState("");
  const [detailPage, setDetailPage] = useState(1);
  const [detailPageSize, setDetailPageSize] = useState(100);
  // Datos ya pedidos por pestana y periodo: volver a una pestana o periodo no consulta de nuevo.
  const cache = useRef(new Map());
  const [loadingFilters, setLoadingFilters] = useState(true);
  const [loading, setLoading] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState("");
  const canDownload = ["super_admin", "admin", "coordinador"].includes(user?.role || "");
  const rows = porEjecutivo(allRows, selected.ejecutivo);
  const negocios = {
    ...allNegocios,
    rows: porEjecutivo(allNegocios.rows, selected.ejecutivo),
    detalle: porEjecutivo(allNegocios.detalle, selected.ejecutivo),
  };
  const executiveRows = pivotRows(rows);
  const totalCarteras = totalByCartera(rows);
  const totalAporteFinal = executiveRows.reduce((acc, row) => acc + row.cumplimiento, 0);
  const finalValues = executiveRows.map((row) => row.cumplimiento).sort((a, b) => a - b);
  const finalThresholds = { p33: percentile(finalValues, 0.33), p66: percentile(finalValues, 0.66) };
  // Umbrales relativos del % cumplimiento dentro de cada cartera.
  const carteraThresholds = Object.fromEntries(
    CARTERAS.map(({ key }) => {
      const values = executiveRows
        .map((row) => row.carteras[key]?.pct_aporte)
        .filter((value) => value !== null && value !== undefined)
        .map(Number)
        .sort((a, b) => a - b);
      return [key, { p33: percentile(values, 0.33), p66: percentile(values, 0.66) }];
    })
  );
  const { rows: negocioRows, total: negocioTotal } = pivotNegocios(negocios.rows);
  const sinGestion = negocios.sin_gestion;
  const ejecutivoOptions = Array.from(new Set([...(filters.ejecutivos || []), "PHOENIX"]));

  useEffect(() => {
    async function loadFilters() {
      setLoadingFilters(true);
      try {
        const data = await fetchLaAraucanaFilters();
        setFilters({ periodos: data.periodos || [], ejecutivos: data.ejecutivos || [] });
        const periodo = data.periodos?.[0] || "";
        setSelected((prev) => ({ ...prev, periodo }));
      } catch (err) {
        setError(err.message);
      } finally {
        setLoadingFilters(false);
      }
    }
    loadFilters();
  }, []);

  useEffect(() => {
    if (!selected.periodo) {
      return;
    }

    async function loadPeriodFilters() {
      try {
        const data = await fetchLaAraucanaFilters(selected.periodo);
        setFilters({ periodos: data.periodos || [], ejecutivos: data.ejecutivos || [] });
        setSelected((prev) => ({
          ...prev,
          ejecutivo: prev.ejecutivo && prev.ejecutivo !== "PHOENIX" && !(data.ejecutivos || []).includes(prev.ejecutivo) ? "" : prev.ejecutivo,
        }));
      } catch (err) {
        setError(err.message);
      }
    }

    loadPeriodFilters();
  }, [selected.periodo]);

  useEffect(() => {
    if (!selected.periodo || view === "detalle") {
      return;
    }
    const periodo = selected.periodo;
    const key = `${view}|${periodo}`;
    const mostrar = (data) => {
      if (view === "negocios") {
        setAllNegocios({ rows: data.rows || [], detalle: data.detalle || [], sin_gestion: data.sin_gestion || null });
      } else {
        setAllRows(data.rows || []);
      }
    };
    setError("");
    if (cache.current.has(key)) {
      mostrar(cache.current.get(key));
      setLoading(false);
      return;
    }
    // Evita que una respuesta antigua pise la de la pestana o periodo actual.
    let cancelled = false;
    async function loadResumen() {
      setLoading(true);
      try {
        const data = view === "negocios" ? await fetchLaAraucanaNegocios({ periodo }) : await fetchLaAraucanaResumen({ periodo, cartera_crm: 531 });
        cache.current.set(key, data);
        if (!cancelled) {
          mostrar(data);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err.message);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }
    loadResumen();
    return () => {
      cancelled = true;
    };
  }, [selected.periodo, view]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDetailFilters((prev) => ({ ...prev, buscar: detailSearch.trim() }));
      setDetailPage(1);
    }, 450);
    return () => window.clearTimeout(timer);
  }, [detailSearch]);

  // El detalle se pagina y filtra en el servidor: son todos los folios asignados del mes.
  useEffect(() => {
    if (!selected.periodo || view !== "detalle") {
      return;
    }
    let cancelled = false;
    async function loadDetalle() {
      setLoading(true);
      setError("");
      try {
        const data = await fetchLaAraucanaDetalle({
          periodo: selected.periodo,
          ejecutivo: selected.ejecutivo,
          ...detailFilters,
          page: detailPage,
          page_size: detailPageSize,
        });
        if (!cancelled) {
          setDetail({ rows: data.data || [], total: Number(data.total || 0), usuarios: data.usuarios_gestion || [] });
        }
      } catch (err) {
        if (!cancelled) {
          setError(err.message);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }
    loadDetalle();
    return () => {
      cancelled = true;
    };
  }, [selected.periodo, selected.ejecutivo, detailFilters, detailPage, detailPageSize, view]);

  function onFilter(name, value) {
    setSelected((prev) => ({ ...prev, [name]: value }));
    setDetailPage(1);
  }

  function onPeriodo(value) {
    setSelected((prev) => ({ ...prev, periodo: value }));
    setDetailFilters((prev) => ({ ...prev, usuario_gestion: "" }));
    setDetailPage(1);
  }

  function onDetailFilter(name, value) {
    setDetailFilters((prev) => ({ ...prev, [name]: value }));
    setDetailPage(1);
  }

  const detailTotalPages = Math.max(1, Math.ceil(detail.total / detailPageSize));
  const detailFrom = detail.total ? (detailPage - 1) * detailPageSize + 1 : 0;
  const detailTo = detail.total ? Math.min(detailPage * detailPageSize, detail.total) : 0;

  async function onDownload() {
    if (!selected.periodo) {
      return;
    }
    setDownloading(true);
    setError("");
    try {
      const { blob, filename } = await downloadLaAraucanaExcel(selected.periodo, "");
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

  // Un ejecutivo sin datos en una cartera se muestra en cero.
  function renderCarteraCells(row, key, isTotal) {
    const data = row || { deuda: 0, recupero: 0, pct_aporte: 0 };
    return (
      <React.Fragment key={key}>
        <td className="pd-num pd-group-start">{formatMM(data.deuda)}</td>
        <td className="pd-num">{formatRecovero(data.recupero)}</td>
        <td className="pd-num">
          <span className={isTotal ? "pd-status pd-status-none" : dotClassByThresholds(data.pct_aporte, carteraThresholds[key])}>{formatPct(data.pct_aporte)}</span>
        </td>
      </React.Fragment>
    );
  }

  function renderNegocioCells(data, key) {
    return (
      <React.Fragment key={key}>
        <td className="pd-num pd-group-start">{formatMoney(data.q_negocios)}</td>
        <td className="pd-num">{formatRecovero(data.recupero)}</td>
      </React.Fragment>
    );
  }

  return (
    <div className="pd-page">
      <PageHeader
        title="Caja La Araucana"
        subtitle="Productividad Caja La Araucana por tipo de cartera."
        actions={
          canDownload && (
            <button type="button" className="pd-btn pd-btn-secondary" onClick={onDownload} disabled={!selected.periodo || downloading}>
              <i className="bi bi-download" aria-hidden="true" /> {downloading ? "Descargando..." : "Descargar Excel"}
            </button>
          )
        }
      />

      <FilterBar>
        <Field label="Periodo">
          <select className="form-select" value={selected.periodo} onChange={(e) => onPeriodo(e.target.value)} disabled={loadingFilters}>
            {!filters.periodos.length && <option value="">{loadingFilters ? "Cargando..." : "Sin meses"}</option>}
            {filters.periodos.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Ejecutivo">
          <select className="form-select" value={selected.ejecutivo} onChange={(e) => onFilter("ejecutivo", e.target.value)}>
            <option value="">Todos</option>
            {ejecutivoOptions.map((v) => (
              <option key={v} value={v}>
                {String(v).toUpperCase()}
              </option>
            ))}
          </select>
        </Field>
        {view === "detalle" && (
          <>
            <Field label="Folio / RUT">
              <input className="form-control" value={detailSearch} onChange={(e) => setDetailSearch(e.target.value)} placeholder="Buscar folio o RUT" />
            </Field>
            <Field label="Cartera">
              <select className="form-select" value={detailFilters.tipo_cartera} onChange={(e) => onDetailFilter("tipo_cartera", e.target.value)}>
                <option value="">Todas</option>
                {CARTERAS.map(({ key, label }) => (
                  <option key={key} value={key}>
                    {label}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Con pago">
              <select className="form-select" value={detailFilters.con_pago} onChange={(e) => onDetailFilter("con_pago", e.target.value)}>
                <option value="">Todos</option>
                <option value="1">Si</option>
                <option value="0">No</option>
              </select>
            </Field>
            <Field label="Usuario Gestion">
              <select className="form-select" value={detailFilters.usuario_gestion} onChange={(e) => onDetailFilter("usuario_gestion", e.target.value)}>
                <option value="">Todos</option>
                {detail.usuarios.map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
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
            { value: "productividad", label: "Productividad" },
            { value: "negocios", label: "Negocios" },
            { value: "detalle", label: "Detalle" },
          ]}
        />
      {view === "productividad" && (
      <SectionCard exportName={exportFileName("La-Araucana", selected.periodo)} bodyClassName="" footer={<StatusLegend title="Aporte" items={aporteLegendItems} />}>
        {loading ? (
          <LoadingState />
        ) : (
          <div className="pd-table-scroll">
            <table className="pd-table pd-table-compact pd-table-fit">
              <thead>
                <tr>
                  <th rowSpan={2}>Ejecutivo</th>
                  {CARTERAS.map(({ key, label }, idx) => (
                    <th key={key} colSpan={3} className={`pd-th-group-${(idx % 2) + 1} pd-group-start`}>{label}</th>
                  ))}
                  <th rowSpan={2} className="pd-num pd-th-key pd-group-start">Aporte Final</th>
                </tr>
                <tr>
                  {CARTERAS.map(({ key }, idx) =>
                    ["Deuda", "Recupero", "Cumplimiento"].map((label, subIdx) => (
                      <th key={`${key}-${label}`} className={`pd-num pd-th-sub-${(idx % 2) + 1}${subIdx === 0 ? " pd-group-start" : ""}`}>
                        {label}
                      </th>
                    ))
                  )}
                </tr>
              </thead>
              <tbody>
                {phoenixGrupalAlFinal(executiveRows).map((row) => (
                  <tr key={row.ejecutivo}>
                    <td className="pd-cell-ejecutivo">{row.ejecutivo}</td>
                    {CARTERAS.map(({ key }) => renderCarteraCells(row.carteras[key], key, false))}
                    <td className="pd-num pd-group-start">
                      <span className={dotClassByThresholds(row.cumplimiento, finalThresholds)}>{formatPct(row.cumplimiento)}</span>
                    </td>
                  </tr>
                ))}
                {!executiveRows.length && <EmptyRow colSpan={CARTERAS.length * 3 + 2} />}
                {executiveRows.length > 0 && (
                  <tr className="pd-row-total">
                    <td>Total general</td>
                    {CARTERAS.map(({ key }) => renderCarteraCells(totalCarteras[key], key, true))}
                    <td className="pd-num pd-group-start">
                      <span className="pd-status pd-status-none">{formatPct(totalAporteFinal)}</span>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>
      )}
      {view === "negocios" && (
      <SectionCard exportName={exportFileName("La-Araucana", "Negocios", selected.periodo)} bodyClassName="">
        {loading ? (
          <LoadingState />
        ) : (
          <div className="pd-table-scroll">
            <table className="pd-table pd-table-compact pd-table-fit">
              <thead>
                <tr>
                  <th rowSpan={2}>Ejecutivo</th>
                  {[...TRAMOS_DEUDA, { key: "TOTAL", label: "Total" }].map(({ key, label }, idx) => (
                    <th key={key} colSpan={2} className={`pd-th-group-${(idx % 2) + 1} pd-group-start`}>{label}</th>
                  ))}
                </tr>
                <tr>
                  {[...TRAMOS_DEUDA, { key: "TOTAL" }].map(({ key }, idx) =>
                    ["Reprogramación", "Recupero"].map((label, subIdx) => (
                      <th key={`${key}-${label}`} className={`pd-num pd-th-sub-${(idx % 2) + 1}${subIdx === 0 ? " pd-group-start" : ""}`}>
                        {label}
                      </th>
                    ))
                  )}
                </tr>
              </thead>
              <tbody>
                {phoenixGrupalAlFinal(negocioRows).map((row) => (
                  <tr key={row.ejecutivo}>
                    <td className="pd-cell-ejecutivo">{row.ejecutivo}</td>
                    {TRAMOS_DEUDA.map(({ key }) => renderNegocioCells(row.tramos[key], key))}
                    {renderNegocioCells(row.total, "TOTAL")}
                  </tr>
                ))}
                {!negocioRows.length && <EmptyRow colSpan={TRAMOS_DEUDA.length * 2 + 3} />}
                {negocioRows.length > 0 && (
                  <tr className="pd-row-total">
                    <td>Total</td>
                    {TRAMOS_DEUDA.map(({ key }) => renderNegocioCells(negocioTotal.tramos[key], key))}
                    {renderNegocioCells(negocioTotal.total, "TOTAL")}
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>
      )}
      {view === "detalle" && (
      <SectionCard
        exportName={exportFileName("La-Araucana", "Detalle", selected.periodo)}
        bodyClassName=""
        footer={
          loading ? null : (
            <Pagination
              summary={`Mostrando ${detailFrom}-${detailTo} de ${formatMoney(detail.total)} folios. Pagina ${detailPage} de ${detailTotalPages}.`}
              onPrev={() => setDetailPage((prev) => Math.max(1, prev - 1))}
              onNext={() => setDetailPage((prev) => Math.min(detailTotalPages, prev + 1))}
              prevDisabled={detailPage <= 1 || loading}
              nextDisabled={detailPage >= detailTotalPages || loading}
            />
          )
        }
      >
        {loading ? (
          <LoadingState />
        ) : (
          <div className="pd-table-scroll">
            <table className="pd-table pd-table-compact">
              <thead>
                <tr>
                  <th>Folio</th>
                  <th>RUT</th>
                  <th>Cartera</th>
                  <th className="pd-num">Deuda</th>
                  <th className="pd-num">Recupero</th>
                  <th>Ejecutivo</th>
                  <th>Usuario Gestion</th>
                  <th>Contacto</th>
                  <th>Respuesta Gestion</th>
                  <th>Gestion Fecha</th>
                  <th>Telefono</th>
                </tr>
              </thead>
              <tbody>
                {detail.rows.map((row, idx) => (
                  <tr key={`${row.folio}-${idx}`}>
                    <td>{row.folio}</td>
                    <td>{row.rut}</td>
                    <td>{row.tipo_cartera}</td>
                    <td className="pd-num">{formatRecovero(row.deuda)}</td>
                    <td className="pd-num">{formatRecovero(row.recupero)}</td>
                    <td>{row.ejecutivo || "-"}</td>
                    <td>{row.usuario_gestion || "SIN GESTION"}</td>
                    <td>{row.contacto_gestion || "-"}</td>
                    <td>{row.respuesta_gestion || "-"}</td>
                    <td>{formatFecha(row.fecha_gestion) || "-"}</td>
                    <td>{row.telefono || "-"}</td>
                  </tr>
                ))}
                {!detail.rows.length && <EmptyRow colSpan={11} />}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>
      )}
      </div>

      {view === "negocios" && !loading && (
        <SectionCard
          title="Detalle de negocios"
          description={
            "Pagos NE-REPRO del mes, asignados a la ejecutiva de la mejor gestion del RUT." +
            (sinGestion && Number(sinGestion.q_negocios) > 0 && (!selected.ejecutivo || selected.ejecutivo === "PHOENIX")
              ? ` PHOENIX incluye ${formatMoney(sinGestion.q_negocios)} negocios sin gestion en el mes (${formatRecovero(sinGestion.monto)}).`
              : "")
          }
          exportName={exportFileName("La-Araucana", "Negocios-detalle", selected.periodo)}
          bodyClassName=""
        >
          <div className="pd-table-scroll">
            <table className="pd-table pd-table-compact pd-table-plain">
              <thead>
                <tr>
                  <th>Ejecutivo</th>
                  <th>Folio</th>
                  <th>RUT</th>
                  <th>Cartera</th>
                  <th>Fecha negocio</th>
                  <th className="pd-num">Monto deuda</th>
                  <th className="pd-num">Recupero</th>
                  <th>Tramo deuda</th>
                </tr>
              </thead>
              <tbody>
                {negocios.detalle.map((row, idx) => (
                  <tr key={`${row.contrato}-${idx}`}>
                    <td className="pd-cell-ejecutivo">{row.ejecutivo}</td>
                    <td>{row.contrato}</td>
                    <td>{row.rut}</td>
                    <td>{row.tipo_cartera}</td>
                    <td>{formatFecha(row.fecha_pago)}</td>
                    <td className="pd-num">{row.deuda === null || row.deuda === undefined ? "" : formatRecovero(row.deuda)}</td>
                    <td className="pd-num">{formatRecovero(row.recupero)}</td>
                    <td>{TRAMO_LABEL[row.tramo_deuda] || ""}</td>
                  </tr>
                ))}
                {!negocios.detalle.length && <EmptyRow colSpan={8} />}
              </tbody>
            </table>
          </div>
        </SectionCard>
      )}
    </div>
  );
}
