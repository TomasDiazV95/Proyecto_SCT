import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  fetchContactabilidadItauDashboard,
  fetchContactabilidadItauFilters,
} from "../api";

const EMPTY_FILTERS = {
  fecha_proceso: "",
  segmento: [],
  canal: [],
  fase_cliente: [],
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

function MultiSelect({ label, value, options, onChange }) {
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

function DailyChart({ rows }) {
  if (!rows.length) return <Empty />;
  const max = Math.max(...rows.map((row) => Number(row.total_gestiones || 0)), 1);
  const width = 900;
  const height = 230;
  const step = width / rows.length;
  return (
    <div className="contact-chart-wrap">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Evolución diaria de gestiones" className="contact-chart">
        <line x1="30" y1="190" x2="880" y2="190" stroke="#d8e1ec" />
        {rows.map((row, index) => {
          const barHeight = (Number(row.total_gestiones || 0) / max) * 150;
          const x = 40 + index * step;
          const barWidth = Math.max(4, step - 8);
          return (
            <g key={row.fecha}>
              <rect x={x} y={190 - barHeight} width={barWidth} height={barHeight} rx="3" fill="#f28c28" />
              <text x={x + barWidth / 2} y="210" textAnchor="middle" className="contact-chart-label">{row.fecha?.slice(8)}</text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

export default function ContactabilidadItauVencidaPage() {
  const [options, setOptions] = useState({
    fechas_proceso: [], segmentos: [], canales: [], gestores: ["PHOENIX"],
    fases_cliente: [], productos: [], tipos_campana: [], detalles_marca: [],
    estados_contencion: [], estados_contacto: [],
  });
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [data, setData] = useState({ resumen: null, estado: null, tubo: null, evolucion: null, detalle: null });
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [filtersLoading, setFiltersLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    setFiltersLoading(true);
    fetchContactabilidadItauFilters("", { signal: controller.signal }).then((body) => {
      if (controller.signal.aborted) return;
      setOptions(body);
      setFilters((prev) => ({ ...prev, fecha_proceso: body.fecha_proceso || body.fechas_proceso?.[0] || "" }));
    }).catch((err) => {
      if (!controller.signal.aborted) setError(err.message || "No se pudieron cargar los filtros");
    }).finally(() => {
      if (!controller.signal.aborted) setFiltersLoading(false);
    });
    return () => controller.abort();
  }, []);

  const requestFilters = useMemo(
    () => ({ ...filters, search, page, page_size: 50, sort_by: "rut", sort_direction: "asc", gestor: "PHOENIX" }),
    [filters, search, page]
  );

  useEffect(() => {
    if (!filters.fecha_proceso) return undefined;
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      try {
        const body = await fetchContactabilidadItauDashboard(requestFilters, { signal: controller.signal });
        if (controller.signal.aborted) return;
        setData({
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
  }, [requestFilters, filters.fecha_proceso]);

  function updateFilter(name, value) {
    setPage(1);
    setFilters((prev) => ({ ...prev, [name]: value }));
  }

  function clearFilters() {
    setPage(1);
    setSearch("");
    setFilters({ ...EMPTY_FILTERS, fecha_proceso: options.fecha_proceso || options.fechas_proceso?.[0] || "" });
  }

  const summary = data.resumen || {};
  const detail = data.detalle || { rows: [], total: 0 };
  const stateRows = data.estado?.rows || [];
  const tubeRows = data.tubo?.rows || [];
  const evolutionRows = data.evolucion?.rows || [];

  return (
    <main className="container-fluid contact-page">
      <div className="contact-topbar">
        <div className="contact-heading">
          <Link to="/contactabilidad" className="contact-back-link">← Volver a Contactabilidad</Link>
          <div className="contact-title-row">
            <div>
              <h1>Contactabilidad Itaú Vencida</h1>
              <p>Resultado al día <strong>{dateLabel(filters.fecha_proceso)}</strong> <span>· Cartera CRM 523 · Gestor PHOENIX</span></p>
            </div>
            <span className="badge contact-badge">Itaú Vencida</span>
          </div>
        </div>
      </div>

      <section className="contact-filter-panel">
        <div className="contact-filter-heading">
          <div><span className="contact-eyebrow">Configuración de vista</span><h2>Filtros de consulta</h2></div>
          <button type="button" className="contact-clear-button" onClick={clearFilters}>↻ Limpiar filtros</button>
        </div>
        {filtersLoading ? <div className="contact-filter-loading">Cargando filtros...</div> : <div className="contact-filter-grid">
          <div className="contact-filter-field"><label className="contact-filter-label">Fecha de Proceso</label><select className="contact-date-select" value={filters.fecha_proceso} onChange={(event) => updateFilter("fecha_proceso", event.target.value)}>{options.fechas_proceso.map((value) => <option key={value} value={value}>{dateLabel(value)}</option>)}</select></div>
          <div className="contact-filter-field"><label className="contact-filter-label">Gestor</label><div className="contact-readonly-field"><span className="contact-status-dot" />PHOENIX<span className="contact-readonly-label">Fijo</span></div></div>
          <MultiSelect label="Segmento" value={filters.segmento} options={options.segmentos} onChange={(value) => updateFilter("segmento", value)} />
          <MultiSelect label="Canal" value={filters.canal} options={options.canales} onChange={(value) => updateFilter("canal", value)} />
          <MultiSelect label="Fase Cliente" value={filters.fase_cliente} options={options.fases_cliente} onChange={(value) => updateFilter("fase_cliente", value)} />
          <MultiSelect label="Producto" value={filters.producto} options={options.productos} onChange={(value) => updateFilter("producto", value)} />
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
          <Kpi label="Total Clientes" value={number(summary.total_clientes)} subtitle="RUT asignados" />
          <Kpi label="Recurrencia Promedio" value={number(summary.recurrencia, 1)} subtitle="Gestiones por cliente" />
          <Kpi label="% Gestionado" value={pct(summary.porcentaje_gestionado)} subtitle={`${number(summary.clientes_gestionados)} clientes`} />
          <Kpi label="% Contacto Titular" value={pct(summary.porcentaje_contacto_titular)} subtitle={`${number(summary.contacto_titular)} clientes`} />
          <Kpi label="% Contacto Tercero" value={pct(summary.contacto_tercero / (summary.total_clientes || 1))} subtitle={`${number(summary.contacto_tercero)} clientes`} />
          <Kpi label="% Otras Gestiones" value={pct(summary.otras_gestiones / (summary.total_clientes || 1))} subtitle={`${number(summary.otras_gestiones)} clientes`} />
          <Kpi label="Sin Gestión" value={number(summary.sin_gestion)} subtitle="Clientes únicos" />
        </div>
        <Section title="Estado Contacto Cliente por Gestor"><div className="table-responsive"><table className="table contact-table align-middle mb-0"><thead><tr><th>Gestor</th><th className="text-end">Total general</th><th className="text-end">%</th><th className="text-end">Contacto Titular</th><th className="text-end">%</th><th className="text-end">Contacto Tercero</th><th className="text-end">%</th><th className="text-end">Gestión Call-Terreno</th><th className="text-end">%</th><th className="text-end">Otra Gestión</th><th className="text-end">%</th></tr></thead><tbody>{stateRows.length ? <tr><td><span className="contact-table-gestor">PHOENIX</span></td><td className="text-end">{number(summary.total_clientes)}</td><td className="text-end">100%</td><td className="text-end">{number(summary.contacto_titular)}</td><td className="text-end">{pct(summary.contacto_titular / (summary.total_clientes || 1))}</td><td className="text-end">{number(summary.contacto_tercero)}</td><td className="text-end">{pct(summary.contacto_tercero / (summary.total_clientes || 1))}</td><td className="text-end">{number(summary.clientes_call_terreno)}</td><td className="text-end">{pct(summary.clientes_call_terreno / (summary.total_clientes || 1))}</td><td className="text-end">{number(summary.otras_gestiones)}</td><td className="text-end">{pct(summary.otras_gestiones / (summary.total_clientes || 1))}</td></tr> : <tr><td colSpan="11"><Empty /></td></tr>}</tbody></table></div></Section>
        <Section title="Tubo de Contactabilidad por Gestor"><div className="table-responsive"><table className="table contact-table align-middle mb-0"><thead><tr><th>Gestor</th><th>Recurrencia</th><th>Casos Asignados</th><th>Casos con Gestión</th><th>% Gestionado</th><th>Contacto Titular</th><th>% Titular</th></tr></thead><tbody>{tubeRows.length ? tubeRows.map((row) => <tr key={row.gestor}><td><span className="contact-table-gestor">{row.gestor}</span></td><td>{number(row.recurrencia, 1)}</td><td>{number(row.casos_asignados)}</td><td>{number(row.casos_con_gestion)}</td><td>{pct(row.porcentaje_gestionado)}</td><td>{number(row.casos_contacto_titular)}</td><td>{pct(row.porcentaje_contacto_titular)}</td></tr>) : <tr><td colSpan="7"><Empty /></td></tr>}</tbody></table></div></Section>
        <Section title="Evolución diaria"><DailyChart rows={evolutionRows} /></Section>
        <Section title="Detalle de clientes y gestiones"><div className="contact-detail-toolbar"><input className="form-control contact-search" placeholder="Buscar por RUT u operación" value={search} onChange={(event) => { setPage(1); setSearch(event.target.value); }} /><button className="contact-secondary-button" onClick={() => { setSearch(""); setPage(1); }}>Limpiar búsqueda</button></div><div className="table-responsive"><table className="table contact-table align-middle mb-2"><thead><tr><th>RUT</th><th>Operación</th><th>Gestor</th><th>Gestiones Call-Terreno</th><th>Última Gestión</th><th>Estado Contacto</th></tr></thead><tbody>{detail.rows.length ? detail.rows.map((row) => <tr key={`${row.rut}-${row.operacion}`}><td>{row.rut}</td><td>{row.operacion || "-"}</td><td>{row.gestor}</td><td>{number(row.cantidad_gestiones)}</td><td>{row.ultima_gestion ? new Date(row.ultima_gestion).toLocaleString("es-CL") : "-"}</td><td>{row.estado_contacto}</td></tr>) : <tr><td colSpan="6"><Empty /></td></tr>}</tbody></table></div><div className="contact-pagination"><span>{number(detail.total)} registros</span><div><button className="contact-secondary-button" disabled={page <= 1} onClick={() => setPage((value) => value - 1)}>Anterior</button><span>Página {page}</span><button className="contact-secondary-button" disabled={page * 50 >= detail.total} onClick={() => setPage((value) => value + 1)}>Siguiente</button></div></div></Section>
      </>}
    </main>
  );
}
