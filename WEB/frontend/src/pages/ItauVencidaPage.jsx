import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { fetchItauVencidaFilters, fetchItauVencidaGeneral } from "../api";


function formatMoney(value) {
  return new Intl.NumberFormat("es-CL", { maximumFractionDigits: 0 }).format(Number(value || 0));
}


function formatPct(value) {
  if (value === null || value === undefined) {
    return "N/D";
  }
  return `${(Number(value || 0) * 100).toFixed(2)}%`;
}


function formatDate(value) {
  if (!value) {
    return "";
  }
  const [year, month, day] = String(value).slice(0, 10).split("-");
  if (!year || !month || !day) {
    return value;
  }
  return `${day}-${month}-${year}`;
}


// Color semantico solo para cumplimiento: < 50% critico, 50-79% intermedio, >= 80% optimo.
function cumplimientoClass(value) {
  if (value === null || value === undefined) {
    return "iv-badge iv-badge-na";
  }
  const num = Number(value);
  if (num >= 0.8) {
    return "iv-badge iv-badge-ok";
  }
  if (num >= 0.5) {
    return "iv-badge iv-badge-warn";
  }
  return "iv-badge iv-badge-bad";
}


export default function ItauVencidaPage() {
  const [filters, setFilters] = useState({ fecha_carga: "", ejecutivo: "" });
  const [options, setOptions] = useState({ fechas_carga: [], ejecutivos: [] });
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(null);
  const [metas, setMetas] = useState([]);
  const [filtrosMedibles, setFiltrosMedibles] = useState([]);
  const [metasOpen, setMetasOpen] = useState(false);
  const [view, setView] = useState("resumen");
  const [metadata, setMetadata] = useState({ fecha_carga: "", periodo: "" });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const { logout } = useAuth();

  useEffect(() => {
    async function loadFilters() {
      try {
        const data = await fetchItauVencidaFilters();
        setOptions(data);
        setFilters((prev) => ({ ...prev, fecha_carga: data.fechas_carga?.[0] || "" }));
      } catch (err) {
        setError(err.message);
      }
    }
    loadFilters();
  }, []);

  useEffect(() => {
    if (!filters.fecha_carga) {
      return;
    }

    async function loadData() {
      setLoading(true);
      setError("");
      try {
        const data = await fetchItauVencidaGeneral(filters);
        setRows(data.rows || []);
        setTotal(data.total || null);
        setMetas(data.metas || []);
        setFiltrosMedibles(data.filtros_medibles || []);
        setMetadata({ fecha_carga: data.fecha_carga || filters.fecha_carga, periodo: data.periodo || "" });
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }

    loadData();
  }, [filters]);

  useEffect(() => {
    if (!metasOpen) {
      return undefined;
    }
    function onKeyDown(event) {
      if (event.key === "Escape") {
        setMetasOpen(false);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [metasOpen]);

  function onFilter(name, value) {
    setFilters((prev) => ({ ...prev, [name]: value }));
  }

  function renderMetasProducto(producto, titulo, accentClass) {
    const fases = metas.filter((meta) => meta.producto === producto);
    if (!fases.length) {
      return null;
    }
    return (
      <div className={`iv-drawer-block ${accentClass}`}>
        <div className="iv-drawer-block-head">
          <span>{titulo}</span>
          <span className="iv-drawer-peso">Pondera {formatPct(fases[0].ponderacion)}</span>
        </div>
        <table className="table table-sm mb-0 iv-drawer-table">
          <thead>
            <tr>
              <th>Tramo</th>
              <th className="text-end">Meta individual</th>
            </tr>
          </thead>
          <tbody>
            {fases.map((meta) => (
              <tr key={`${meta.producto}-${meta.fase}`}>
                <td>Fase {meta.fase}</td>
                <td className="text-end fw-semibold">{formatPct(meta.meta_contencion)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  function renderFiltrosMedibles() {
    const etiquetas = { DETALLE_MARCA: "Detalle marca", CANAL: "Canal", PRODUCTO: "Producto", SEGMENTO: "Segmento", FASE_PROY_MAX: "Fase" };
    const grupos = [];
    filtrosMedibles.forEach((filtro) => {
      let grupo = grupos.find((item) => item.columna === filtro.columna);
      if (!grupo) {
        grupo = { columna: filtro.columna, valores: [] };
        grupos.push(grupo);
      }
      grupo.valores.push(filtro.valor);
    });

    return (
      <div className="iv-medibles">
        <div className="iv-medibles-title">Casos medibles del mes</div>
        {grupos.length ? (
          <ul className="iv-medibles-list">
            {grupos.map((grupo) => (
              <li key={grupo.columna}>
                <span className="iv-medibles-col">{etiquetas[grupo.columna] || grupo.columna}</span>
                {grupo.valores.map((valor) => (
                  <span key={valor} className="iv-medibles-valor">{grupo.columna === "FASE_PROY_MAX" ? `Fase ${valor}` : valor}</span>
                ))}
              </li>
            ))}
          </ul>
        ) : (
          <div className="small iv-drawer-muted">
            Este mes no tiene casos medibles configurados. Se agregan en Panel Administrativo &gt; Itaú.
          </div>
        )}
      </div>
    );
  }

  function renderMetasDrawer() {
    if (!metasOpen) {
      return null;
    }
    return (
      <>
        <div className="iv-drawer-backdrop" onClick={() => setMetasOpen(false)} />
        <aside className="iv-drawer" role="dialog" aria-modal="true" aria-labelledby="iv-drawer-title">
          <div className="iv-drawer-header">
            <div>
              <h2 id="iv-drawer-title" className="h5 m-0">Metas de contención</h2>
              <div className="small iv-drawer-muted">Vigentes para {formatDate(metadata.periodo) || "N/D"}</div>
            </div>
            <button type="button" className="btn-close" aria-label="Cerrar" onClick={() => setMetasOpen(false)} />
          </div>

          <div className="iv-drawer-body">
            {metas.length ? (
              <div className="iv-drawer-grid">
                {renderMetasProducto("CONSUMO", "Contención Consumo", "iv-accent-consumo")}
                {renderMetasProducto("HIPOTECARIO", "Contención Hipotecario", "iv-accent-hipot")}
              </div>
            ) : (
              <div className="alert alert-light border">No hay metas cargadas para este mes.</div>
            )}
            {renderFiltrosMedibles()}
          </div>
        </aside>
      </>
    );
  }

  function renderGroupCells(row, producto) {
    const cls = producto === "consumo" ? "iv-consumo" : "iv-hipot";
    return (
      <>
        <td className={`text-center ${cls} iv-group-start`}>${formatMoney(row[`${producto}_saldo_ini`])}</td>
        <td className={`text-center ${cls}`}>${formatMoney(row[`${producto}_saldo_cont`])}</td>
        <td className={`text-center ${cls}`}>${formatMoney(row[`${producto}_meta_monto`])}</td>
        <td className={`text-center ${cls}`}>
          <span className={cumplimientoClass(row[`${producto}_cumplimiento`])}>{formatPct(row[`${producto}_cumplimiento`])}</span>
        </td>
      </>
    );
  }

  function renderRow(row, key, isTotal = false) {
    return (
      <tr key={key} className={isTotal ? "fw-semibold itau-total-row" : undefined}>
        <td>{row.ejecutivo}</td>
        {renderGroupCells(row, "consumo")}
        {renderGroupCells(row, "hipotecario")}
        <td className="text-center iv-final iv-group-start">
          <span className={cumplimientoClass(row.cumplimiento)}>{formatPct(row.cumplimiento)}</span>
        </td>
      </tr>
    );
  }

  function renderFaseCells(fase, producto) {
    const cls = producto === "consumo" ? "iv-consumo" : "iv-hipot";
    // Fase sin meta para el producto (p.ej. Hipotecario fase 7): no entra al calculo.
    if (fase[`${producto}_meta_pct`] == null) {
      return (
        <td colSpan={4} className={`text-center ${cls} iv-group-start iv-no-aplica`}>
          Sin meta
        </td>
      );
    }
    return (
      <>
        <td className={`text-center ${cls} iv-group-start`}>${formatMoney(fase[`${producto}_saldo_ini`])}</td>
        <td className={`text-center ${cls}`}>${formatMoney(fase[`${producto}_saldo_cont`])}</td>
        <td className={`text-center ${cls}`}>
          ${formatMoney(fase[`${producto}_meta_monto`])}
          <div className="iv-meta-pct">meta {formatPct(fase[`${producto}_meta_pct`])}</div>
        </td>
        <td className={`text-center ${cls}`}>
          <span className={cumplimientoClass(fase[`${producto}_cumplimiento`])}>{formatPct(fase[`${producto}_cumplimiento`])}</span>
        </td>
      </>
    );
  }

  function renderDetalleBloque(row, keyPrefix, isTotal = false) {
    const fases = row.fases || [];
    return [
      ...fases.map((fase, idx) => (
        <tr key={`${keyPrefix}-fase-${fase.fase}`} className={isTotal ? "iv-detalle-total-fase" : undefined}>
          {idx === 0 && (
            <td rowSpan={fases.length + 1} className={`iv-detalle-ejecutivo${isTotal ? " fw-semibold" : ""}`}>
              {row.ejecutivo}
            </td>
          )}
          <td className="text-center iv-fase-cell">Fase {fase.fase}</td>
          {renderFaseCells(fase, "consumo")}
          {renderFaseCells(fase, "hipotecario")}
          <td className="text-center iv-final iv-group-start iv-no-aplica">—</td>
        </tr>
      )),
      <tr key={`${keyPrefix}-subtotal`} className={`fw-semibold iv-subtotal-row${isTotal ? " itau-total-row" : ""}`}>
        {!fases.length && <td>{row.ejecutivo}</td>}
        <td className="text-center iv-fase-cell">Total</td>
        {renderGroupCells(row, "consumo")}
        {renderGroupCells(row, "hipotecario")}
        <td className="text-center iv-final iv-group-start">
          <span className={cumplimientoClass(row.cumplimiento)}>{formatPct(row.cumplimiento)}</span>
        </td>
      </tr>,
    ];
  }

  function renderTable() {
    const detalle = view === "detalle";
    const subHeaders = ["Saldo Inicial", "Contenido", "Meta $", "Cumplimiento"];
    return (
      <table className={`table align-middle mb-0 itau-vencida-table${detalle ? " iv-detalle-table" : " table-hover"}`}>
        <thead>
          <tr>
            <th rowSpan={2} className="align-middle">Ejecutivo</th>
            {detalle && <th rowSpan={2} className="text-center align-middle iv-fase-head">Fase</th>}
            <th colSpan={4} className="text-center iv-consumo iv-group-start">
              Consumo <span className="iv-peso">pondera 60%</span>
            </th>
            <th colSpan={4} className="text-center iv-hipot iv-group-start">
              Hipotecario <span className="iv-peso">pondera 40%</span>
            </th>
            <th rowSpan={2} className="text-center align-middle iv-final iv-group-start">Cumplimiento Final</th>
          </tr>
          <tr>
            {subHeaders.map((label, idx) => (
              <th key={`c-${label}`} className={`text-center iv-consumo iv-sub${idx === 0 ? " iv-group-start" : ""}`}>{label}</th>
            ))}
            {subHeaders.map((label, idx) => (
              <th key={`h-${label}`} className={`text-center iv-hipot iv-sub${idx === 0 ? " iv-group-start" : ""}`}>{label}</th>
            ))}
          </tr>
        </thead>
        {detalle ? (
          <>
            {rows.map((row, idx) => (
              <tbody key={`iv-detalle-${row.ejecutivo}-${idx}`} className="iv-detalle-group">
                {renderDetalleBloque(row, `iv-detalle-${idx}`)}
              </tbody>
            ))}
            {total && <tbody className="iv-detalle-group">{renderDetalleBloque(total, "iv-detalle-total", true)}</tbody>}
          </>
        ) : (
          <tbody>
            {rows.map((row, idx) => renderRow(row, `itau-vencida-${row.ejecutivo}-${idx}`))}
            {total && renderRow(total, "itau-vencida-total", true)}
          </tbody>
        )}
      </table>
    );
  }

  return (
    <div className="container-fluid py-4 app-shell itau-castigo-page">
      <div className="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
        <div>
          <h1 className="h3 m-0">Itaú Vencida - Productividad</h1>
          <Link to="/productividad" className="small text-decoration-none">
            Volver al Home
          </Link>
        </div>
        <div className="btn-group">
          <button className="btn btn-outline-secondary" onClick={logout}>Cerrar sesion</button>
        </div>
      </div>

      <div className="card shadow-sm mb-3 itau-filter-card">
        <div className="card-body">
          <div className="row g-2 align-items-end">
            <div className="col-12 col-md-3">
              <label className="form-label">Fecha de carga</label>
              <select className="form-select" value={filters.fecha_carga} onChange={(e) => onFilter("fecha_carga", e.target.value)}>
                {options.fechas_carga.map((value) => (
                  <option key={value} value={value}>
                    {formatDate(value)}
                  </option>
                ))}
              </select>
            </div>
            <div className="col-12 col-md-3">
              <label className="form-label">Ejecutivo</label>
              <select className="form-select" value={filters.ejecutivo} onChange={(e) => onFilter("ejecutivo", e.target.value)}>
                <option value="">Todos</option>
                {options.ejecutivos.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </div>
            <div className="col-12 col-md-4 small text-muted">
              Base: contención Phoenix {formatDate(metadata.fecha_carga || filters.fecha_carga) || "N/D"} | Mes metas/carterizado: {formatDate(metadata.periodo) || "N/D"}
            </div>
            <div className="col-12 col-md-2 text-md-end">
              <button type="button" className="btn btn-sm iv-info-btn" onClick={() => setMetasOpen(true)}>
                <span aria-hidden="true">ⓘ</span> Metas
              </button>
            </div>
          </div>
        </div>
      </div>

      {error && <div className="alert alert-danger">{error}</div>}

      {renderMetasDrawer()}

      <div className="iv-tabs" role="tablist">
        <button type="button" role="tab" aria-selected={view === "resumen"} className={`iv-tab${view === "resumen" ? " active" : ""}`} onClick={() => setView("resumen")}>
          Resumen
        </button>
        <button type="button" role="tab" aria-selected={view === "detalle"} className={`iv-tab${view === "detalle" ? " active" : ""}`} onClick={() => setView("detalle")}>
          Detalle por fase
        </button>
      </div>

      <div className="card shadow-sm iv-tab-card">
        <div className="card-body table-responsive">
          {loading ? (
            <div className="text-center py-4">Cargando...</div>
          ) : !filtrosMedibles.length ? (
            <div className="alert alert-warning mb-0">
              {formatDate(metadata.periodo).slice(3) || "Este mes"} no tiene casos medibles configurados, por eso no hay cumplimiento que mostrar.
              Se configuran en Panel Administrativo &gt; Itaú &gt; Casos medibles Itaú Vencida.
            </div>
          ) : (
            renderTable()
          )}
        </div>
      </div>

      <div className="card shadow-sm mt-3 itau-legend-card">
        <div className="card-body py-2 small">
          <strong>Cumplimiento:</strong>
          <span className="ms-3"><span className="iv-badge iv-badge-bad">&lt; 50%</span> Crítico</span>
          <span className="ms-3"><span className="iv-badge iv-badge-warn">50% – 79%</span> Intermedio</span>
          <span className="ms-3"><span className="iv-badge iv-badge-ok">≥ 80%</span> Óptimo</span>
        </div>
      </div>
    </div>
  );
}
