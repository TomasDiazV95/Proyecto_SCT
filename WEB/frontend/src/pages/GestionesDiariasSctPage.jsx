import { useEffect, useRef, useState } from "react";

import { fetchGestionesDiariasSctDetail, fetchGestionesDiariasSctFilters, fetchGestionesDiariasSctSummary } from "../api";
import {
  EmptyRow,
  Field,
  FilterBar,
  LoadingState,
  PageHeader,
  Pagination,
  SectionCard,
  ViewTabs,
  exportFileName,
  phoenixGrupalAlFinal,
} from "../components/productividad/ui";

const BREADCRUMB = [
  { label: "Inicio", to: "/" },
  { label: "Panel Administrativo", to: "/administrativas" },
];

function formatNumber(value) {
  return new Intl.NumberFormat("es-CL").format(Number(value || 0));
}

const initialSharedFilters = {
  fecha_desde: "",
  fecha_hasta: "",
};

const initialDetailFilters = {
  ejecutivo: "",
  contacto: "",
  accion: "",
  canal: "",
  estado: "",
  tramo_mora: "",
  zona: "",
};

const initialSummaryFilters = {
  ejecutivos: [],
  contacto: "",
  canal: "",
  tramo_mora: "",
  zona: "",
};

function normalizeOptions(data) {
  return {
    fecha_min: data.fecha_min || "",
    fecha_max: data.fecha_max || "",
    ejecutivos: data.ejecutivos || [],
    contactos: data.contactos || [],
    acciones: data.acciones || [],
    canales: data.canales || [],
    estados: data.estados || [],
    tramos_mora: data.tramos_mora || [],
    zonas: data.zonas || [],
  };
}

function display(value) {
  return value === null || value === undefined || value === "" ? "-" : value;
}

function formatGestionDate(value) {
  const text = String(value || "").trim();
  if (!text) {
    return "-";
  }
  const match = text.match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}:\d{2}:\d{2})/);
  if (match) {
    return `${match[3]}-${match[2]}-${match[1]} ${match[4]}`;
  }
  return text.replace(/\.\d+$/, "");
}

export default function GestionesDiariasSctPage() {
  const [view, setView] = useState("resumen");
  const [sharedFilters, setSharedFilters] = useState(initialSharedFilters);
  const [detailFilters, setDetailFilters] = useState(initialDetailFilters);
  const [summaryFilters, setSummaryFilters] = useState(initialSummaryFilters);
  const [options, setOptions] = useState({ fecha_min: "", fecha_max: "", ejecutivos: [], contactos: [], acciones: [], canales: [], estados: [], tramos_mora: [], zonas: [] });
  const [rows, setRows] = useState([]);
  const [contactoColumns, setContactoColumns] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(100);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [executiveDropdownOpen, setExecutiveDropdownOpen] = useState(false);
  const [executiveSearch, setExecutiveSearch] = useState("");
  const executiveDropdownRef = useRef(null);

  useEffect(() => {
    if (!executiveDropdownOpen) {
      return undefined;
    }
    function handlePointerDown(event) {
      if (executiveDropdownRef.current && !executiveDropdownRef.current.contains(event.target)) {
        setExecutiveDropdownOpen(false);
      }
    }
    function handleKeyDown(event) {
      if (event.key === "Escape") {
        setExecutiveDropdownOpen(false);
      }
    }
    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("touchstart", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("touchstart", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [executiveDropdownOpen]);

  useEffect(() => {
    async function loadFilters() {
      try {
        const data = await fetchGestionesDiariasSctFilters();
        setOptions(normalizeOptions(data));
        setSharedFilters((prev) => ({
          ...prev,
          fecha_desde: data.fecha_max || "",
          fecha_hasta: data.fecha_max || "",
        }));
      } catch (err) {
        setError(err.message);
      }
    }
    loadFilters();
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function loadDependentFilters() {
      try {
        const activeFilters = view === "resumen" ? { ...sharedFilters, ...summaryFilters } : { ...sharedFilters, ...detailFilters };
        const data = await fetchGestionesDiariasSctFilters(activeFilters);
        if (cancelled) {
          return;
        }
        const nextOptions = normalizeOptions(data);
        setOptions(nextOptions);
        const setter = view === "resumen" ? setSummaryFilters : setDetailFilters;
        setter((prev) => {
          const next = { ...prev };
          const checks = view === "resumen" ? [
            ["ejecutivos", "ejecutivos"],
            ["contacto", "contactos"],
            ["canal", "canales"],
            ["tramo_mora", "tramos_mora"],
            ["zona", "zonas"],
          ] : [
            ["ejecutivo", "ejecutivos"],
            ["contacto", "contactos"],
            ["accion", "acciones"],
            ["canal", "canales"],
            ["estado", "estados"],
            ["tramo_mora", "tramos_mora"],
            ["zona", "zonas"],
          ];
          let changed = false;
          checks.forEach(([filterKey, optionKey]) => {
            if (Array.isArray(next[filterKey])) {
              const validValues = next[filterKey].filter((value) => nextOptions[optionKey].includes(value));
              if (validValues.length !== next[filterKey].length) {
                next[filterKey] = validValues;
                changed = true;
              }
            } else if (next[filterKey] && !nextOptions[optionKey].includes(next[filterKey])) {
              next[filterKey] = "";
              changed = true;
            }
          });
          return changed ? next : prev;
        });
      } catch (err) {
        if (!cancelled) {
          setError(err.message);
        }
      }
    }
    loadDependentFilters();
    return () => {
      cancelled = true;
    };
  }, [sharedFilters, detailFilters, summaryFilters, view]);

  useEffect(() => {
    async function loadData() {
      setLoading(true);
        setError("");
        try {
          const loader = view === "resumen" ? fetchGestionesDiariasSctSummary : fetchGestionesDiariasSctDetail;
        const activeFilters = view === "resumen" ? { ...sharedFilters, ...summaryFilters } : { ...sharedFilters, ...detailFilters };
        const detail = await loader({ ...activeFilters, page, page_size: pageSize });
        setRows(detail.data || []);
        setContactoColumns(view === "resumen" ? detail.contacto_columns || [] : []);
        setTotal(Number(detail.total || 0));
      } catch (err) {
        setRows([]);
        setContactoColumns([]);
        setTotal(0);
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, [sharedFilters, detailFilters, summaryFilters, page, pageSize, view]);

  function onFilter(name, value) {
    if (name === "fecha_desde" || name === "fecha_hasta") {
      setSharedFilters((prev) => ({ ...prev, [name]: value }));
    } else if (view === "resumen") {
      setSummaryFilters((prev) => ({ ...prev, [name]: value }));
    } else {
      setDetailFilters((prev) => ({ ...prev, [name]: value }));
    }
    setPage(1);
  }

  function toggleSummaryExecutive(value) {
    setSummaryFilters((prev) => {
      const selected = prev.ejecutivos.includes(value);
      return {
        ...prev,
        ejecutivos: selected ? prev.ejecutivos.filter((item) => item !== value) : [...prev.ejecutivos, value],
      };
    });
    setPage(1);
  }

  function clearSummaryExecutives() {
    setSummaryFilters((prev) => ({ ...prev, ejecutivos: [] }));
    setPage(1);
  }

  function selectVisibleExecutives(values) {
    setSummaryFilters((prev) => ({ ...prev, ejecutivos: Array.from(new Set([...prev.ejecutivos, ...values])) }));
    setPage(1);
  }

  function clearFilters() {
    setSharedFilters(initialSharedFilters);
    if (view === "resumen") {
      setSummaryFilters(initialSummaryFilters);
    } else {
      setDetailFilters(initialDetailFilters);
    }
    setPage(1);
  }

  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const from = total ? (page - 1) * pageSize + 1 : 0;
  const to = total ? Math.min(page * pageSize, total) : 0;
  const viewFilters = view === "resumen" ? summaryFilters : detailFilters;
  const filteredExecutives = options.ejecutivos.filter((value) => value.toLowerCase().includes(executiveSearch.trim().toLowerCase()));
  const executiveButtonText = summaryFilters.ejecutivos.length === 0
    ? "Todos los ejecutivos"
    : summaryFilters.ejecutivos.length === 1
      ? "1 ejecutivo seleccionado"
      : `${summaryFilters.ejecutivos.length} ejecutivos seleccionados`;

  function changeView(next) {
    if (next === view) {
      return;
    }
    setRows([]);
    setContactoColumns([]);
    setTotal(0);
    setView(next);
    setPage(1);
  }

  const summaryRows = phoenixGrupalAlFinal(rows, (row) => row.cobrador_actual);
  const detailColumns = ["Fecha gestión", "RUT", "DV", "Operación", "Tramo mora", "Cobrador", "Contacto", "Estado", "Fecha compromiso", "Comentario", "Acción", "Canal", "Zona"];
  const summaryColSpan = contactoColumns.length + 2;

  return (
    <div className="pd-page">
      <PageHeader
        title="Gestiones Diarias SCT"
        subtitle="Gestiones diarias de Santander Consumer Terreno: resumen por cobrador y detalle de cada gestión."
        breadcrumb={BREADCRUMB}
      />

      <FilterBar
        actions={
          <button type="button" className="pd-btn pd-btn-ghost" onClick={clearFilters}>
            <i className="bi bi-x-circle" aria-hidden="true" /> Limpiar filtros
          </button>
        }
      >
        <Field label="Fecha desde">
          <input className="form-control" type="date" value={sharedFilters.fecha_desde} min={options.fecha_min || undefined} max={options.fecha_max || undefined} onChange={(e) => onFilter("fecha_desde", e.target.value)} />
        </Field>
        <Field label="Fecha hasta">
          <input className="form-control" type="date" value={sharedFilters.fecha_hasta} min={options.fecha_min || undefined} max={options.fecha_max || undefined} onChange={(e) => onFilter("fecha_hasta", e.target.value)} />
        </Field>
        {view === "resumen" ? (
          <div className="pd-field">
            <span className="pd-label" id="sct-ejecutivos-label">Ejecutivos</span>
            <div className="position-relative" ref={executiveDropdownRef}>
              <button
                type="button"
                className="form-select text-start text-truncate"
                aria-labelledby="sct-ejecutivos-label"
                aria-expanded={executiveDropdownOpen}
                onClick={() => setExecutiveDropdownOpen((prev) => !prev)}
              >
                {executiveButtonText}
              </button>
              {executiveDropdownOpen && (
                <div className="pd-multi-panel">
                  <input className="form-control" value={executiveSearch} onChange={(e) => setExecutiveSearch(e.target.value)} placeholder="Buscar ejecutivo" />
                  <div className="pd-multi-actions">
                    <button type="button" className="pd-btn pd-btn-secondary pd-btn-sm" onClick={() => selectVisibleExecutives(filteredExecutives)} disabled={!filteredExecutives.length}>
                      Seleccionar visibles
                    </button>
                    <button type="button" className="pd-btn pd-btn-ghost pd-btn-sm" onClick={clearSummaryExecutives} disabled={!summaryFilters.ejecutivos.length}>
                      Quitar selección
                    </button>
                  </div>
                  <div className="pd-multi-list">
                    {filteredExecutives.length ? filteredExecutives.map((value) => (
                      <label className="pd-multi-option" key={value}>
                        <input type="checkbox" className="form-check-input" checked={summaryFilters.ejecutivos.includes(value)} onChange={() => toggleSummaryExecutive(value)} />
                        <span>{String(value).toUpperCase()}</span>
                      </label>
                    )) : (
                      <div className="pd-small pd-muted">Ningún ejecutivo coincide con la búsqueda.</div>
                    )}
                  </div>
                  <div className="pd-multi-hint">Si no marcas ninguno, se muestran todos.</div>
                </div>
              )}
            </div>
          </div>
        ) : (
          <Field label="Ejecutivo">
            <select className="form-select" value={detailFilters.ejecutivo} onChange={(e) => onFilter("ejecutivo", e.target.value)}>
              <option value="">Todos</option>
              {options.ejecutivos.map((value) => (
                <option key={value} value={value}>
                  {String(value).toUpperCase()}
                </option>
              ))}
            </select>
          </Field>
        )}
        <Field label="Contacto">
          <select className="form-select" value={viewFilters.contacto} onChange={(e) => onFilter("contacto", e.target.value)}>
            <option value="">Todos</option>
            {options.contactos.map((value) => (
              <option key={value} value={value}>{value}</option>
            ))}
          </select>
        </Field>
        {view === "detalle" && (
          <Field label="Acción">
            <select className="form-select" value={detailFilters.accion} onChange={(e) => onFilter("accion", e.target.value)}>
              <option value="">Todas</option>
              {options.acciones.map((value) => (
                <option key={value} value={value}>{value}</option>
              ))}
            </select>
          </Field>
        )}
        {view === "detalle" && (
          <Field label="Estado">
            <select className="form-select" value={detailFilters.estado} onChange={(e) => onFilter("estado", e.target.value)}>
              <option value="">Todos</option>
              {options.estados.map((value) => (
                <option key={value} value={value}>{value}</option>
              ))}
            </select>
          </Field>
        )}
        <Field label="Tramo mora">
          <select className="form-select" value={viewFilters.tramo_mora} onChange={(e) => onFilter("tramo_mora", e.target.value)}>
            <option value="">Todos</option>
            {options.tramos_mora.map((value) => (
              <option key={value} value={value}>{value}</option>
            ))}
          </select>
        </Field>
        <Field label="Canal">
          <select className="form-select" value={viewFilters.canal} onChange={(e) => onFilter("canal", e.target.value)}>
            <option value="">Todos</option>
            {options.canales.map((value) => (
              <option key={value} value={value}>{value}</option>
            ))}
          </select>
        </Field>
        <Field label="Zona">
          <select className="form-select" value={viewFilters.zona} onChange={(e) => onFilter("zona", e.target.value)}>
            <option value="">Todas</option>
            {options.zonas.map((value) => (
              <option key={value} value={value}>{value}</option>
            ))}
          </select>
        </Field>
        <Field label="Filas">
          <select className="form-select" value={pageSize} onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }}>
            {[50, 100, 200, 500].map((value) => (
              <option key={value} value={value}>{value}</option>
            ))}
          </select>
        </Field>
      </FilterBar>

      {error && <div className="alert alert-danger">{error}</div>}

      <div className="pd-tabbed">
        <ViewTabs
          value={view}
          onChange={changeView}
          options={[
            { value: "resumen", label: "Resumen por cobrador" },
            { value: "detalle", label: "Detalle de gestiones" },
          ]}
        />
        <SectionCard
          exportName={exportFileName("Gestiones-SCT", view, sharedFilters.fecha_desde, sharedFilters.fecha_hasta)}
          bodyClassName=""
          footer={
            <Pagination
              summary={`Mostrando ${formatNumber(from)}-${formatNumber(to)} de ${formatNumber(total)} ${view === "resumen" ? "cobradores" : "gestiones"}. Página ${page} de ${totalPages}.`}
              onPrev={() => setPage((prev) => Math.max(1, prev - 1))}
              onNext={() => setPage((prev) => Math.min(totalPages, prev + 1))}
              prevDisabled={page <= 1 || loading}
              nextDisabled={page >= totalPages || loading}
            />
          }
        >
          {loading ? (
            <LoadingState text="Cargando gestiones..." />
          ) : view === "detalle" ? (
            <div className="pd-table-scroll">
              <table className="pd-table pd-table-compact">
                <thead>
                  <tr>
                    {detailColumns.map((label) => (
                      <th key={label}>{label}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.id_gestion}>
                      <td>{formatGestionDate(row.fech_gest)}</td>
                      <td>{display(row.ddas_nrt_ppal)}</td>
                      <td>{display(row.ddas_drt_ppal)}</td>
                      <td>{display(row.ddas_id_numero_operac)}</td>
                      <td>{display(row.tramo_mora)}</td>
                      <td className="pd-cell-ejecutivo">{display(row.cobrador_actual)}</td>
                      <td>{display(row.contacto)}</td>
                      <td>{display(row.estado)}</td>
                      <td>{formatGestionDate(row.fecha_comp)}</td>
                      <td className="pd-cell-comment">{display(row.com_gest)}</td>
                      <td>{display(row.accion)}</td>
                      <td>{display(row.canal)}</td>
                      <td>{display(row.zona)}</td>
                    </tr>
                  ))}
                  {!rows.length && <EmptyRow colSpan={detailColumns.length} text="No hay gestiones para los filtros seleccionados. Prueba con otro rango de fechas." />}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="pd-table-scroll">
              <table className="pd-table">
                <thead>
                  <tr>
                    <th rowSpan={2}>Cobrador</th>
                    {contactoColumns.length > 0 && (
                      <th colSpan={contactoColumns.length} className="pd-th-group-1 pd-group-start">Gestiones por contacto</th>
                    )}
                    <th rowSpan={2} className="pd-num pd-th-key pd-group-start">Total gestiones</th>
                  </tr>
                  <tr>
                    {contactoColumns.map((column, idx) => (
                      <th key={column} className={`pd-num pd-th-sub-1${idx === 0 ? " pd-group-start" : ""}`}>{column}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {summaryRows.map((row) => (
                    <tr key={row.cobrador_actual || "sin-cobrador"}>
                      <td className="pd-cell-ejecutivo">{display(row.cobrador_actual)}</td>
                      {contactoColumns.map((column, idx) => (
                        <td key={column} className={`pd-num${idx === 0 ? " pd-group-start" : ""}`}>{formatNumber(row.contactos?.[column])}</td>
                      ))}
                      <td className="pd-num pd-group-start pd-cell-strong">{formatNumber(row.total_gestiones)}</td>
                    </tr>
                  ))}
                  {!rows.length && <EmptyRow colSpan={summaryColSpan} text="No hay gestiones para los filtros seleccionados. Prueba con otro rango de fechas." />}
                </tbody>
              </table>
            </div>
          )}
        </SectionCard>
      </div>
    </div>
  );
}
