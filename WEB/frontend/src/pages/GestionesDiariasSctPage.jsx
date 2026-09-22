import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { fetchGestionesDiariasSctDetail, fetchGestionesDiariasSctFilters, fetchGestionesDiariasSctSummary } from "../api";

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

  return (
    <div className="container-fluid py-4 app-shell">
      <div className="d-flex justify-content-between align-items-center mb-3">
        <div>
          <h1 className="h3 m-0">Gestiones Diarias SCT</h1>
          <Link to="/administrativas" className="small text-decoration-none">
            Volver a Administrativas
          </Link>
        </div>
        <div className="btn-group">
          <button className={`btn btn-${view === "resumen" ? "primary" : "outline-primary"}`} onClick={() => { setRows([]); setContactoColumns([]); setTotal(0); setView("resumen"); setPage(1); }}>
            Resumen
          </button>
          <button className={`btn btn-${view === "detalle" ? "primary" : "outline-primary"}`} onClick={() => { setRows([]); setContactoColumns([]); setTotal(0); setView("detalle"); setPage(1); }}>
            Detalle
          </button>
        </div>
      </div>

      <div className="card shadow-sm mb-3">
        <div className="card-body">
          <div className="row g-2 align-items-end">
            <div className="col-12 col-md-2">
              <label className="form-label">Fecha desde</label>
              <input className="form-control" type="date" value={sharedFilters.fecha_desde} min={options.fecha_min || undefined} max={options.fecha_max || undefined} onChange={(e) => onFilter("fecha_desde", e.target.value)} />
            </div>
            <div className="col-12 col-md-2">
              <label className="form-label">Fecha hasta</label>
              <input className="form-control" type="date" value={sharedFilters.fecha_hasta} min={options.fecha_min || undefined} max={options.fecha_max || undefined} onChange={(e) => onFilter("fecha_hasta", e.target.value)} />
            </div>
            {view === "resumen" ? (
              <div className="col-12 col-md-3">
                <label className="form-label">Ejecutivos</label>
                <div className="position-relative">
                  <button className="btn btn-outline-secondary w-100 text-start d-flex justify-content-between align-items-center" type="button" onClick={() => setExecutiveDropdownOpen((prev) => !prev)}>
                    <span className="text-truncate">{executiveButtonText}</span>
                    <span className="ms-2">▾</span>
                  </button>
                  {executiveDropdownOpen && (
                    <div className="position-absolute bg-white border rounded shadow-sm p-2 mt-1 w-100" style={{ zIndex: 20, maxHeight: 360, overflow: "hidden" }}>
                      <input className="form-control form-control-sm mb-2" value={executiveSearch} onChange={(e) => setExecutiveSearch(e.target.value)} placeholder="Buscar ejecutivo" />
                      <div className="d-flex gap-2 mb-2">
                        <button className="btn btn-sm btn-outline-primary" type="button" onClick={() => selectVisibleExecutives(filteredExecutives)} disabled={!filteredExecutives.length}>
                          Seleccionar visibles
                        </button>
                        <button className="btn btn-sm btn-outline-secondary" type="button" onClick={clearSummaryExecutives} disabled={!summaryFilters.ejecutivos.length}>
                          Limpiar
                        </button>
                      </div>
                      <div className="overflow-auto" style={{ maxHeight: 240 }}>
                        {filteredExecutives.length ? filteredExecutives.map((value) => (
                          <label className="d-flex align-items-center gap-2 py-1 small" key={value}>
                            <input type="checkbox" className="form-check-input m-0" checked={summaryFilters.ejecutivos.includes(value)} onChange={() => toggleSummaryExecutive(value)} />
                            <span className="text-truncate">{value}</span>
                          </label>
                        )) : (
                          <div className="small text-muted py-2">Sin ejecutivos disponibles</div>
                        )}
                      </div>
                      <div className="small text-muted border-top pt-2 mt-2">Sin seleccion = todos</div>
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className="col-12 col-md-3">
                <label className="form-label">Ejecutivo</label>
                <select className="form-select" value={detailFilters.ejecutivo} onChange={(e) => onFilter("ejecutivo", e.target.value)}>
                  <option value="">Todos</option>
                  {options.ejecutivos.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
              </div>
            )}
            <div className="col-12 col-md-2">
              <label className="form-label">Contacto</label>
              <select className="form-select" value={viewFilters.contacto} onChange={(e) => onFilter("contacto", e.target.value)}>
                <option value="">Todos</option>
                {options.contactos.map((value) => (
                  <option key={value} value={value}>{value}</option>
                ))}
              </select>
            </div>
            {view === "detalle" && (
              <div className="col-12 col-md-2">
                <label className="form-label">Accion</label>
                <select className="form-select" value={detailFilters.accion} onChange={(e) => onFilter("accion", e.target.value)}>
                  <option value="">Todas</option>
                  {options.acciones.map((value) => (
                    <option key={value} value={value}>{value}</option>
                  ))}
                </select>
              </div>
            )}
            {view === "detalle" && (
              <div className="col-12 col-md-2">
                <label className="form-label">Estado</label>
                <select className="form-select" value={detailFilters.estado} onChange={(e) => onFilter("estado", e.target.value)}>
                  <option value="">Todos</option>
                  {options.estados.map((value) => (
                    <option key={value} value={value}>{value}</option>
                  ))}
                </select>
              </div>
            )}
            {(view === "detalle" || view === "resumen") && (
              <div className="col-12 col-md-2">
                <label className="form-label">Tramo mora</label>
                <select className="form-select" value={viewFilters.tramo_mora} onChange={(e) => onFilter("tramo_mora", e.target.value)}>
                  <option value="">Todos</option>
                  {options.tramos_mora.map((value) => (
                    <option key={value} value={value}>{value}</option>
                  ))}
                </select>
              </div>
            )}
            <div className="col-12 col-md-2">
              <label className="form-label">Canal</label>
              <select className="form-select" value={viewFilters.canal} onChange={(e) => onFilter("canal", e.target.value)}>
                <option value="">Todos</option>
                {options.canales.map((value) => (
                  <option key={value} value={value}>{value}</option>
                ))}
              </select>
            </div>
            <div className="col-12 col-md-2">
              <label className="form-label">Zona</label>
              <select className="form-select" value={viewFilters.zona} onChange={(e) => onFilter("zona", e.target.value)}>
                <option value="">Todas</option>
                {options.zonas.map((value) => (
                  <option key={value} value={value}>{value}</option>
                ))}
              </select>
            </div>
            <div className="col-12 col-md-2">
              <label className="form-label">Filas</label>
              <select className="form-select" value={pageSize} onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }}>
                {[50, 100, 200, 500].map((value) => (
                  <option key={value} value={value}>{value}</option>
                ))}
              </select>
            </div>
            <div className="col-12 col-md-2">
              <button className="btn btn-outline-secondary w-100" type="button" onClick={clearFilters}>
                Limpiar filtros
              </button>
            </div>
          </div>
        </div>
      </div>

      {error && <div className="alert alert-danger">{error}</div>}

      <div className="card shadow-sm">
        <div className="card-body">
          <div className="d-flex justify-content-between align-items-center mb-2">
            <span className="small text-muted">Mostrando {from}-{to} de {total} registros</span>
            <div className="btn-group btn-group-sm">
              <button className="btn btn-outline-primary" disabled={page <= 1 || loading} onClick={() => setPage((prev) => Math.max(1, prev - 1))}>Anterior</button>
              <button className="btn btn-outline-primary" disabled>{page} / {totalPages}</button>
              <button className="btn btn-outline-primary" disabled={page >= totalPages || loading} onClick={() => setPage((prev) => Math.min(totalPages, prev + 1))}>Siguiente</button>
            </div>
          </div>

          <div className="table-responsive">
            {loading ? (
              <div className="text-center py-4">Cargando...</div>
            ) : rows.length === 0 ? (
              <div className="text-center py-4 text-muted">No hay gestiones para los filtros seleccionados.</div>
            ) : (
              <table className="table table-striped table-hover align-middle gm-data-table">
                <thead>
                  {view === "detalle" ? (
                    <tr>
                      <th>Fecha gestion</th>
                      <th>RUT</th>
                      <th>DV</th>
                      <th>Operacion</th>
                      <th>Tramo mora</th>
                      <th>Cobrador</th>
                      <th>Contacto</th>
                      <th>Estado</th>
                      <th>Fecha compromiso</th>
                      <th>Comentario</th>
                      <th>Accion</th>
                      <th>Canal</th>
                      <th>Zona</th>
                    </tr>
                  ) : (
                    <tr>
                      <th>Cobrador</th>
                      {contactoColumns.map((column) => (
                        <th key={column}>{column}</th>
                      ))}
                      <th>Total gestiones</th>
                    </tr>
                  )}
                </thead>
                <tbody>
                  {view === "detalle"
                    ? rows.map((row) => (
                        <tr key={row.id_gestion}>
                          <td>{formatGestionDate(row.fech_gest)}</td>
                          <td>{display(row.ddas_nrt_ppal)}</td>
                          <td>{display(row.ddas_drt_ppal)}</td>
                          <td>{display(row.ddas_id_numero_operac)}</td>
                          <td>{display(row.tramo_mora)}</td>
                          <td>{display(row.cobrador_actual)}</td>
                          <td>{display(row.contacto)}</td>
                          <td>{display(row.estado)}</td>
                          <td>{formatGestionDate(row.fecha_comp)}</td>
                          <td className="text-wrap" style={{ minWidth: 260 }}>{display(row.com_gest)}</td>
                          <td>{display(row.accion)}</td>
                          <td>{display(row.canal)}</td>
                          <td>{display(row.zona)}</td>
                        </tr>
                      ))
                    : rows.map((row) => (
                        <tr key={row.cobrador_actual || "sin-cobrador"}>
                          <td>{display(row.cobrador_actual)}</td>
                          {contactoColumns.map((column) => (
                            <td key={column}>{Number(row.contactos?.[column] || 0)}</td>
                          ))}
                          <td>{display(row.total_gestiones)}</td>
                        </tr>
                      ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
