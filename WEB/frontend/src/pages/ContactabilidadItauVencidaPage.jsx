import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  downloadContactabilidadItauDetalle,
  fetchContactabilidadItauDashboard,
  fetchContactabilidadItauFilters,
} from "../api";
import { saveDownload } from "../utils/download";

const PAGE_SIZE = 10;

const EMPTY_FILTERS = {
  periodo: "",
  segmento: [],
  canal: [],
  fase_cliente: [],
  glosa_tipo_cartera: [],
  producto: [],
  tipo_campana: [],
  detalle_marca: [],
  estado_contencion: [],
  estado_contacto: [],
};

function number(value, digits = 0) {
  return new Intl.NumberFormat("es-CL", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  }).format(Number(value || 0));
}

function pct(value) {
  return `${number(Number(value || 0) * 100, 1)}%`;
}

function dateLabel(value) {
  return value
    ? new Intl.DateTimeFormat("es-CL").format(new Date(`${value}T00:00:00`))
    : "N/D";
}

// El backend clasifica cada cliente con la prioridad Titular > Tercero > Sin Contacto.
// Aquí sólo se acorta la etiqueta para la tabla.
function contactoLabel(value) {
  if (!value) return "-";
  return value.replace(/^Contacto\s+/i, "");
}

function periodLabel(value) {
  if (!value) return "N/D";
  const label = new Intl.DateTimeFormat("es-CL", { month: "long", year: "numeric" })
    .format(new Date(`${value}-01T00:00:00`));
  return label.charAt(0).toUpperCase() + label.slice(1);
}

function MultiSelect({ label, value, options = [], onChange }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);
  const summary = value.length === 0
    ? "Todos"
    : value.length <= 2
      ? value.join(", ")
      : `${value.length} seleccionados`;
  const menuOptions = ["Todos", ...options.filter((option) => option !== "Todos")];

  useEffect(() => {
    function closeOnOutside(event) {
      if (rootRef.current && !rootRef.current.contains(event.target)) setOpen(false);
    }
    function closeOnEscape(event) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", closeOnOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOnOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, []);

  function toggle(option) {
    if (option === "Todos") {
      onChange([]);
      return;
    }
    onChange(value.includes(option)
      ? value.filter((item) => item !== option)
      : [...value, option]);
  }

  return (
    <div className="contact-filter-field" ref={rootRef}>
      <label className="contact-filter-label">{label}</label>
      <div className={`contact-dropdown ${open ? "is-open" : ""}`}>
        <button
          type="button"
          className="contact-dropdown-trigger"
          onClick={() => setOpen((current) => !current)}
          onKeyDown={(event) => {
            if (event.key === "ArrowDown") {
              event.preventDefault();
              setOpen(true);
            }
          }}
          aria-haspopup="menu"
          aria-expanded={open}
        >
          <span className={value.length ? "is-selected" : "is-placeholder"}>{summary}</span>
          <span className="contact-dropdown-chevron">⌄</span>
        </button>
        {open && (
          <div className="contact-dropdown-menu" role="menu">
            <div className="contact-dropdown-head">
              <span>{value.length ? `${value.length} seleccionados` : "Seleccionar valores"}</span>
              {value.length > 0 && (
                <button type="button" onClick={() => onChange([])}>Limpiar</button>
              )}
            </div>
            <div className="contact-dropdown-options">
              {menuOptions.map((option) => (
                <label className={`contact-option ${option === "Todos" ? "is-all" : ""}`} key={option}>
                  <input
                    type="checkbox"
                    checked={option === "Todos" ? value.length === 0 : value.includes(option)}
                    onChange={() => toggle(option)}
                  />
                  <span>{option}</span>
                </label>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Kpi({ label, value, subtitle, accent = "" }) {
  return (
    <div className="col-12 col-sm-6 col-xl-3">
      <div className={`card contact-kpi h-100 ${accent}`}>
        <div className="card-body">
          <div className="contact-kpi-label">{label}</div>
          <div className="contact-kpi-value">{value}</div>
          {subtitle && <div className="contact-kpi-subtitle">{subtitle}</div>}
        </div>
      </div>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <section className="card contact-section">
      <div className="card-body">
        <div className="contact-section-heading"><h2>{title}</h2></div>
        {children}
      </div>
    </section>
  );
}

function Empty({ text = "No existen datos para los filtros seleccionados." }) {
  return <div className="contact-empty">{text}</div>;
}

function LoadingDashboard() {
  return (
    <div className="contact-loading" aria-live="polite" aria-label="Cargando información">
      <div className="row g-3 mb-3">
        {Array.from({ length: 8 }).map((_, index) => (
          <div className="col-12 col-sm-6 col-xl-3" key={index}>
            <div className="contact-skeleton-card">
              <span className="contact-skeleton-line contact-skeleton-label" />
              <span className="contact-skeleton-line contact-skeleton-value" />
              <span className="contact-skeleton-line contact-skeleton-note" />
            </div>
          </div>
        ))}
      </div>
      <div className="contact-skeleton-panel"><span className="contact-skeleton-line contact-skeleton-title" /><span className="contact-skeleton-block" /></div>
      <div className="contact-skeleton-panel"><span className="contact-skeleton-line contact-skeleton-title" /><span className="contact-skeleton-block" /></div>
    </div>
  );
}

function ComparativeChart({ data }) {
  const [activo, setActivo] = useState(null);
  const rows = data?.rows || [];
  const actual = data?.periodo_actual;
  const anterior = data?.periodo_anterior;

  if (!rows.length) return <Empty />;

  const width = 900;
  const height = 300;
  const chartLeft = 56;
  const chartRight = 878;
  const chartTop = 20;
  const chartBottom = 238;
  const colorActual = "#f28c28";
  const colorAnterior = "#3678c8";

  const valores = rows.flatMap((row) => [row.actual?.porcentaje_titular, row.anterior?.porcentaje_titular])
    .filter((value) => value !== null && value !== undefined);
  // Escala ajustada al dato: con maximos cercanos al 12% una escala fija 0-100% dejaria
  // las dos lineas pegadas al eje y el grafico no serviria para comparar.
  const maxValor = Math.max(...valores, 0.01);
  const tope = Math.min(1, Math.ceil(maxValor * 100 / 5) * 5 / 100 + 0.01);
  const paso = rows.length > 1 ? (chartRight - chartLeft) / (rows.length - 1) : 0;
  const xForIndex = (index) => (rows.length > 1 ? chartLeft + index * paso : (chartLeft + chartRight) / 2);
  const yForValue = (value) => chartBottom - (Number(value) / tope) * (chartBottom - chartTop);

  function linePath(key) {
    let path = "";
    let conectado = false;
    rows.forEach((row, index) => {
      const punto = row[key];
      if (!punto) {
        conectado = false;
        return;
      }
      path += `${conectado ? "L" : "M"}${xForIndex(index)},${yForValue(punto.porcentaje_titular)} `;
      conectado = true;
    });
    return path.trim();
  }

  const gridValues = [0, 0.25, 0.5, 0.75, 1].map((f) => Number((f * tope).toFixed(4)));
  const etiquetasX = rows.filter((_, index) => index === 0 || index === rows.length - 1 || index % 3 === 0);
  const filaActiva = activo === null ? null : rows[activo];

  return (
    <div className="contact-chart-wrap">
      <div className="contact-chart-legend" aria-label="Períodos comparados">
        {actual && (
          <span className="contact-chart-legend-item">
            <span className="contact-chart-legend-dot" style={{ backgroundColor: colorActual }} />
            {actual.etiqueta}
          </span>
        )}
        {anterior && (
          <span className="contact-chart-legend-item">
            <span className="contact-chart-legend-dot" style={{ backgroundColor: colorAnterior }} />
            {anterior.etiqueta}
          </span>
        )}
      </div>

      <div className="contact-chart-canvas">
        <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Evolución diaria del porcentaje de contacto titular comparada con el mes anterior" className="contact-chart">
          {gridValues.map((value) => {
            const y = yForValue(value);
            return (
              <g key={value}>
                <line x1={chartLeft} y1={y} x2={chartRight} y2={y} className="contact-chart-grid-line" />
                <text x={chartLeft - 8} y={y + 4} textAnchor="end" className="contact-chart-axis-label">{pct(value)}</text>
              </g>
            );
          })}

          {etiquetasX.map((row) => (
            <text key={row.dias_habiles_cierre} x={xForIndex(rows.indexOf(row))} y={chartBottom + 24} textAnchor="middle" className="contact-chart-label">
              {row.dias_habiles_cierre}
            </text>
          ))}

          {filaActiva && (
            <line x1={xForIndex(activo)} y1={chartTop} x2={xForIndex(activo)} y2={chartBottom} className="contact-chart-cursor" />
          )}

          {[["anterior", colorAnterior], ["actual", colorActual]].map(([key, color]) => (
            <g key={key}>
              <path d={linePath(key)} fill="none" stroke={color} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
              {rows.map((row, index) => row[key] && (
                <circle
                  key={`${key}-${row.dias_habiles_cierre}`}
                  cx={xForIndex(index)}
                  cy={yForValue(row[key].porcentaje_titular)}
                  r={activo === index ? 5 : 3}
                  fill={color}
                />
              ))}
            </g>
          ))}

          {rows.map((row, index) => (
            <rect
              key={`hit-${row.dias_habiles_cierre}`}
              x={xForIndex(index) - paso / 2}
              y={chartTop}
              width={Math.max(paso, 6)}
              height={chartBottom - chartTop}
              fill="transparent"
              onMouseEnter={() => setActivo(index)}
              onMouseLeave={() => setActivo(null)}
            />
          ))}
        </svg>

        {filaActiva && (
          <div
            className={`contact-chart-tooltip ${activo > rows.length / 2 ? "is-left" : ""}`}
            style={{ left: `${(xForIndex(activo) / width) * 100}%` }}
          >
            <div className="contact-tooltip-head">
              {filaActiva.dias_habiles_cierre === 0
                ? "Cierre · último día hábil"
                : `${Math.abs(filaActiva.dias_habiles_cierre)} días hábiles al cierre`}
            </div>
            {actual && (
              <div className="contact-tooltip-row">
                <span>
                  <span className="contact-chart-legend-dot" style={{ backgroundColor: colorActual }} />
                  {filaActiva.actual ? dateLabel(filaActiva.actual.fecha) : actual.etiqueta}
                </span>
                <strong>{filaActiva.actual ? pct(filaActiva.actual.porcentaje_titular) : "sin dato"}</strong>
              </div>
            )}
            {anterior && (
              <div className="contact-tooltip-row">
                <span>
                  <span className="contact-chart-legend-dot" style={{ backgroundColor: colorAnterior }} />
                  {filaActiva.anterior ? dateLabel(filaActiva.anterior.fecha) : anterior.etiqueta}
                </span>
                <strong>{filaActiva.anterior ? pct(filaActiva.anterior.porcentaje_titular) : "sin dato"}</strong>
              </div>
            )}
            {filaActiva.diferencia_pp !== null && filaActiva.diferencia_pp !== undefined && (
              <div className="contact-tooltip-diff">
                <span>Diferencia</span>
                <strong className={filaActiva.diferencia_pp >= 0 ? "is-up" : "is-down"}>
                  {filaActiva.diferencia_pp >= 0 ? "+" : ""}{number(filaActiva.diferencia_pp, 1)} pp
                </strong>
              </div>
            )}
          </div>
        )}
      </div>
      <div className="contact-chart-axis-caption">Días hábiles al cierre</div>
    </div>
  );
}

export default function ContactabilidadItauVencidaPage() {
  const [options, setOptions] = useState({
    periodos: [], segmentos: [], canales: [],
    fases_cliente: [], glosas_tipo_cartera: [], sub_productos: [],
    tipos_campana: [], detalles_marca: [],
    estados_contencion: [], estados_contacto: [],
  });
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [data, setData] = useState({ periodo: "", fecha_contencion: "", resumen: null, estado: null, tubo: null, evolucion: null, detalle: null });
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [filtersLoading, setFiltersLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    setFiltersLoading(true);
    fetchContactabilidadItauFilters("", { signal: controller.signal }).then((body) => {
      if (controller.signal.aborted) return;
      setOptions({
        ...body,
        periodos: body.periodos || [],
        segmentos: body.segmentos || [],
        canales: body.canales || [],
        fases_cliente: body.fases_cliente || [],
        glosas_tipo_cartera: body.glosas_tipo_cartera || [],
        sub_productos: body.sub_productos || body.productos || [],
        tipos_campana: body.tipos_campana || [],
        detalles_marca: body.detalles_marca || [],
        estados_contencion: body.estados_contencion || [],
        estados_contacto: body.estados_contacto || [],
      });
      setFilters((prev) => ({ ...prev, periodo: body.periodo || body.periodos?.[0] || "" }));
    }).catch((err) => {
      if (!controller.signal.aborted) setError(err.message || "No se pudieron cargar los filtros");
    }).finally(() => {
      if (!controller.signal.aborted) setFiltersLoading(false);
    });
    return () => controller.abort();
  }, []);

  const requestFilters = useMemo(
    () => ({ ...filters, search, page, page_size: PAGE_SIZE, sort_by: "rut", sort_direction: "asc" }),
    [filters, search, page]
  );

  useEffect(() => {
    if (!filters.periodo) return undefined;
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      try {
        const body = await fetchContactabilidadItauDashboard(requestFilters, { signal: controller.signal });
        if (controller.signal.aborted) return;
        setData({
          periodo: body.periodo,
          fecha_contencion: body.fecha_contencion,
          resumen: body.resumen,
          estado: body.estado || body.estado_contacto,
          tubo: body.tubo,
          evolucion: body.evolucion,
          detalle: body.detalle,
        });
      } catch (err) {
        if (!controller.signal.aborted) setError(err.message || "No fue posible cargar la información de contactabilidad");
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }, 300);
    setLoading(true);
    setError("");
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [requestFilters, filters.periodo]);

  function updateFilter(name, value) {
    setPage(1);
    setFilters((prev) => ({ ...prev, [name]: value }));
  }

  async function exportDetalle() {
    setExporting(true);
    try {
      const file = await downloadContactabilidadItauDetalle(requestFilters);
      saveDownload(file.blob, file.filename);
    } catch (err) {
      setError(err.message || "No fue posible exportar el detalle");
    } finally {
      setExporting(false);
    }
  }

  function clearFilters() {
    setPage(1);
    setSearch("");
    setFilters({ ...EMPTY_FILTERS, periodo: options.periodo || options.periodos?.[0] || "" });
  }

  const summary = data.resumen || {};
  // El backend resuelve qué carga de contención corresponde al período; el frontend sólo la muestra.
  const contencionDate = data.fecha_contencion || summary.fecha_contencion || "";
  const activePeriod = data.periodo || summary.periodo || filters.periodo;
  const detail = data.detalle || { rows: [], total: 0 };
  const tubeRows = data.tubo?.rows || [];
  const evolucion = data.evolucion || null;

  return (
    <main className="container-fluid contact-page">
      <div className="contact-topbar">
        <div className="contact-heading">
          <Link to="/contactabilidad" className="contact-back-link">← Volver a Contactabilidad</Link>
          <div className="contact-title-row">
            <div>
              <h1>Contactabilidad Itaú Vencida</h1>
              {contencionDate && <p className="contact-subtitle">Resultado período <strong>{periodLabel(activePeriod)}</strong> · Contención al <strong>{dateLabel(contencionDate)}</strong></p>}
            </div>
          </div>
        </div>
      </div>

      <section className="contact-filter-panel">
        <div className="contact-filter-heading">
          <div><span className="contact-eyebrow">Configuración de vista</span><h2>Filtros de consulta</h2></div>
          <button type="button" className="contact-clear-button" onClick={clearFilters}>↻ Limpiar filtros</button>
        </div>
        {filtersLoading ? <div className="contact-filter-loading">Cargando filtros...</div> : <div className="contact-filter-grid">
          <div className="contact-filter-field"><label className="contact-filter-label">Período</label><select className="contact-date-select" value={filters.periodo} onChange={(event) => updateFilter("periodo", event.target.value)}>{options.periodos.map((value) => <option key={value} value={value}>{periodLabel(value)}</option>)}</select></div>
          <MultiSelect label="Segmento" value={filters.segmento} options={options.segmentos} onChange={(value) => updateFilter("segmento", value)} />
          <MultiSelect label="Canal" value={filters.canal} options={options.canales} onChange={(value) => updateFilter("canal", value)} />
          <MultiSelect label="Fase Cliente" value={filters.fase_cliente} options={options.fases_cliente} onChange={(value) => updateFilter("fase_cliente", value)} />
          <MultiSelect label="Producto" value={filters.glosa_tipo_cartera} options={options.glosas_tipo_cartera} onChange={(value) => updateFilter("glosa_tipo_cartera", value)} />
          <MultiSelect label="Sub Producto" value={filters.producto} options={options.sub_productos} onChange={(value) => updateFilter("producto", value)} />
          <MultiSelect label="Tipo Campaña" value={filters.tipo_campana} options={options.tipos_campana} onChange={(value) => updateFilter("tipo_campana", value)} />
          <MultiSelect label="Detalle Marca" value={filters.detalle_marca} options={options.detalles_marca} onChange={(value) => updateFilter("detalle_marca", value)} />
          <MultiSelect label="Estado Contención" value={filters.estado_contencion} options={options.estados_contencion} onChange={(value) => updateFilter("estado_contencion", value)} />
          <MultiSelect label="Estado Contacto" value={filters.estado_contacto} options={options.estados_contacto} onChange={(value) => updateFilter("estado_contacto", value)} />
        </div>}
        <div className="contact-filter-footer"><span>Los cambios se aplican automáticamente</span><span className="contact-filter-hint">Los menús permiten seleccionar varios valores</span></div>
      </section>

      {error && <div className="alert alert-danger contact-alert d-flex justify-content-between align-items-center">{error}<button className="btn btn-sm btn-outline-danger" onClick={() => setFilters((prev) => ({ ...prev }))}>Reintentar</button></div>}
      {loading && <LoadingDashboard />}

      {!loading && <>
        <div className="row g-3 contact-kpi-grid">
          <Kpi label="Total Gestiones" value={number(summary.total_gestiones)} subtitle="Call + Terreno" accent="is-primary" />
          <Kpi label="Total Casos" value={number(summary.total_clientes)} subtitle="RUT de contención" />
          <Kpi label="Intensidad Promedio" value={number(summary.recurrencia, 1)} subtitle={`gestiones por RUT`} />
          <Kpi label="% Gestionado" value={pct(summary.porcentaje_gestionado)} subtitle={`${number(summary.clientes_gestionados)} clientes`} />
          <Kpi label="% Contacto Titular" value={pct(summary.porcentaje_contacto_titular)} subtitle={`${number(summary.contacto_titular)} clientes`} />
          <Kpi label="% Contacto Tercero" value={pct(summary.porcentaje_contacto_tercero)} subtitle={`${number(summary.contacto_tercero)} clientes`} />
          <Kpi label="% Sin Contacto" value={pct(summary.porcentaje_sin_contacto)} subtitle={`${number(summary.sin_contacto)} clientes`} />
          <Kpi label="Sin Gestión" value={number(summary.sin_gestion)} subtitle={`${pct(summary.porcentaje_sin_gestion)} del total`} />
        </div>
        <Section title="Tubo de Contactabilidad"><div className="table-responsive"><table className="table contact-table align-middle mb-0"><thead><tr><th>Gestor</th><th>Total Casos</th><th>Contacto Titular</th><th>% Titular</th><th>Casos con Promesa</th><th>% Promesa</th><th>Promesas Cumplidas</th><th>% Promesa Cumplida</th></tr></thead><tbody>{tubeRows.length ? tubeRows.map((row) => <tr key={row.gestor}><td><span className="contact-table-gestor">{row.gestor}</span></td><td>{number(row.casos_asignados)}</td><td>{number(row.casos_contacto_titular)}</td><td>{pct(row.porcentaje_contacto_titular)}</td><td>{number(row.casos_promesa)}</td><td>{pct(row.porcentaje_promesa)}</td><td>{number(row.promesas_cumplidas)}</td><td>{pct(row.porcentaje_promesa_cumplida)}</td></tr>) : <tr><td colSpan="8"><Empty /></td></tr>}</tbody></table></div></Section>
        <Section title="Evolución diaria · % Contacto Titular vs mes anterior"><ComparativeChart data={evolucion} /></Section>
        <Section title="Detalle de clientes y gestiones"><div className="contact-detail-toolbar"><input className="form-control contact-search" placeholder="Buscar por RUT u operación" value={search} onChange={(event) => { setPage(1); setSearch(event.target.value); }} /><button className="contact-secondary-button" onClick={() => { setSearch(""); setPage(1); }}>Limpiar búsqueda</button><button className="contact-secondary-button contact-export-button" type="button" onClick={exportDetalle} disabled={exporting || !detail.total}>{exporting ? "Descargando..." : "⭳ Descargar Excel"}</button></div><div className="table-responsive"><table className="table contact-table align-middle mb-2"><thead><tr><th>RUT</th><th>Operación</th><th>Última Gestión</th><th>Tipo Gestión</th><th>Gestión</th><th>Contuvo</th><th>Fecha Promesa</th></tr></thead><tbody>{detail.rows.length ? detail.rows.map((row) => <tr key={`${row.rut}-${row.operacion}`}><td>{row.rut}</td><td>{row.operacion || "-"}</td><td>{dateLabel(row.ultima_gestion)}</td><td>{row.tipo_gestion || "-"}</td><td>{contactoLabel(row.estado_contacto)}</td><td><span className={`contact-flag ${row.contuvo === "SI" ? "is-yes" : "is-no"}`}>{row.contuvo || "NO"}</span></td><td>{dateLabel(row.fecha_promesa)}</td></tr>) : <tr><td colSpan="7"><Empty /></td></tr>}</tbody></table></div><div className="contact-pagination"><span>{number(detail.total)} registros · mostrando {detail.rows.length}</span><div><button className="contact-secondary-button" disabled={page <= 1} onClick={() => setPage((value) => value - 1)}>Anterior</button><span>Página {page}</span><button className="contact-secondary-button" disabled={page * PAGE_SIZE >= detail.total} onClick={() => setPage((value) => value + 1)}>Siguiente</button></div></div></Section>
      </>}
    </main>
  );
}
