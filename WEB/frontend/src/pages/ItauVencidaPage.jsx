import { useEffect, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { fetchItauVencidaFilters, fetchItauVencidaGeneral } from "../api";
import { Field, FilterBar, LoadingState, PageHeader, SectionCard, StatusLegend, ViewTabs, cumplimientoClass, cumplimientoLegendItems, phoenixGrupalAlFinal, exportFileName } from "../components/productividad/ui";


function formatMoney(value) {
  return `${new Intl.NumberFormat("es-CL", { maximumFractionDigits: 0 }).format(Number(value || 0) / 1e6)} M`;
}


function formatPct(value) {
  if (value === null || value === undefined) {
    return "N/D";
  }
  return `${(Number(value || 0) * 100).toFixed(2)}%`;
}


// Los cumplimientos de meta se muestran sin decimales.
function formatCumpl(value) {
  if (value === null || value === undefined) {
    return "N/D";
  }
  return `${(Number(value || 0) * 100).toFixed(0)}%`;
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


// Cumplimiento viene en fraccion (1 = 100%); el semaforo comun trabaja en escala 0-100.
function cumplimientoFraccionClass(value) {
  return cumplimientoClass(value === null || value === undefined ? null : Number(value) * 100);
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

  // Al cambiar la fecha de carga, el filtro de ejecutivo solo ofrece los disponibles en ese periodo.
  useEffect(() => {
    if (!filters.fecha_carga) {
      return;
    }
    fetchItauVencidaFilters(filters.fecha_carga)
      .then((data) => {
        const disponibles = data.ejecutivos || [];
        setOptions((prev) => ({ ...prev, ejecutivos: disponibles }));
        setFilters((prev) => (prev.ejecutivo && !disponibles.includes(prev.ejecutivo) ? { ...prev, ejecutivo: "" } : prev));
      })
      .catch((err) => setError(err.message));
  }, [filters.fecha_carga]);

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
        <table className="pd-table pd-table-plain pd-table-compact pd-table-static">
          <thead>
            <tr>
              <th>Tramo</th>
              <th className="pd-num">Meta individual</th>
            </tr>
          </thead>
          <tbody>
            {fases.map((meta) => (
              <tr key={`${meta.producto}-${meta.fase}`}>
                <td>Fase {meta.fase}</td>
                <td className="pd-num pd-cell-strong">{formatPct(meta.meta_contencion)}</td>
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
          <div className="pd-small pd-muted">
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
        <div className="pd-drawer-backdrop" onClick={() => setMetasOpen(false)} />
        <aside className="pd-drawer" role="dialog" aria-modal="true" aria-labelledby="iv-drawer-title">
          <div className="pd-drawer-header">
            <div>
              <h2 id="iv-drawer-title" className="pd-section-title">Metas del mes</h2>
              <p className="pd-section-desc">Vigentes para {formatDate(metadata.periodo) || "N/D"}</p>
            </div>
            <button type="button" className="btn-close" aria-label="Cerrar" onClick={() => setMetasOpen(false)} />
          </div>

          <div className="pd-drawer-body">
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
    return (
      <>
        <td className="pd-num pd-group-start">${formatMoney(row[`${producto}_saldo_ini`])}</td>
        <td className="pd-num">${formatMoney(row[`${producto}_saldo_cont`])}</td>
        <td className="pd-num">${formatMoney(row[`${producto}_meta_monto`])}</td>
        <td className="pd-num">
          <span className={cumplimientoFraccionClass(row[`${producto}_cumplimiento`])}>{formatCumpl(row[`${producto}_cumplimiento`])}</span>
        </td>
      </>
    );
  }

  function renderRow(row, key, isTotal = false) {
    return (
      <tr key={key} className={isTotal ? "pd-row-total" : undefined}>
        <td className={isTotal ? undefined : "pd-cell-ejecutivo"}>{row.ejecutivo}</td>
        {renderGroupCells(row, "consumo")}
        {renderGroupCells(row, "hipotecario")}
        <td className="pd-num pd-group-start">
          <span className={cumplimientoFraccionClass(row.cumplimiento)}>{formatCumpl(row.cumplimiento)}</span>
        </td>
      </tr>
    );
  }

  function renderFaseCells(fase, producto) {
    // Fase sin meta para el producto (p.ej. Hipotecario fase 7): no entra al calculo.
    if (fase[`${producto}_meta_pct`] == null) {
      return (
        <td colSpan={4} className="pd-center pd-group-start pd-cell-muted">
          Sin meta
        </td>
      );
    }
    return (
      <>
        <td className="pd-num pd-group-start">${formatMoney(fase[`${producto}_saldo_ini`])}</td>
        <td className="pd-num">${formatMoney(fase[`${producto}_saldo_cont`])}</td>
        <td className="pd-num">
          ${formatMoney(fase[`${producto}_meta_monto`])}
          <span className="pd-cell-sub">meta {formatPct(fase[`${producto}_meta_pct`])}</span>
        </td>
        <td className="pd-num">
          <span className={cumplimientoFraccionClass(fase[`${producto}_cumplimiento`])}>{formatCumpl(fase[`${producto}_cumplimiento`])}</span>
        </td>
      </>
    );
  }

  function renderDetalleBloque(row, keyPrefix, isTotal = false) {
    const fases = row.fases || [];
    return [
      ...fases.map((fase, idx) => (
        <tr key={`${keyPrefix}-fase-${fase.fase}`}>
          {idx === 0 && (
            <td rowSpan={fases.length + 1} className={`pd-cell-rowhead${isTotal ? "" : " pd-cell-ejecutivo"}`}>
              {row.ejecutivo}
            </td>
          )}
          <td className="pd-center pd-muted pd-cell-strong">Fase {fase.fase}</td>
          {renderFaseCells(fase, "consumo")}
          {renderFaseCells(fase, "hipotecario")}
          <td className="pd-num pd-group-start pd-cell-muted">—</td>
        </tr>
      )),
      <tr key={`${keyPrefix}-subtotal`} className={isTotal ? "pd-row-total" : "pd-row-subtotal"}>
        {!fases.length && <td className={isTotal ? undefined : "pd-cell-ejecutivo"}>{row.ejecutivo}</td>}
        <td className="pd-center pd-cell-strong">Total</td>
        {renderGroupCells(row, "consumo")}
        {renderGroupCells(row, "hipotecario")}
        <td className="pd-num pd-group-start">
          <span className={cumplimientoFraccionClass(row.cumplimiento)}>{formatCumpl(row.cumplimiento)}</span>
        </td>
      </tr>,
    ];
  }

  function renderTable() {
    const detalle = view === "detalle";
    const subHeaders = ["Saldo Inicial", "Contenido", "Meta $", "Cumplimiento"];
    return (
      <table className={`pd-table${detalle ? " pd-table-static" : ""}`}>
        <thead>
          <tr>
            <th rowSpan={2}>Ejecutivo</th>
            {detalle && <th rowSpan={2} className="pd-center pd-th-key">Fase</th>}
            <th colSpan={4} className="pd-th-group-1 pd-group-start">
              Consumo <span className="pd-th-note">pondera 60%</span>
            </th>
            <th colSpan={4} className="pd-th-group-2 pd-group-start">
              Hipotecario <span className="pd-th-note">pondera 40%</span>
            </th>
            <th rowSpan={2} className="pd-num pd-th-key pd-group-start">Cumplimiento Final</th>
          </tr>
          <tr>
            {subHeaders.map((label, idx) => (
              <th key={`c-${label}`} className={`pd-num pd-th-sub-1${idx === 0 ? " pd-group-start" : ""}`}>{label}</th>
            ))}
            {subHeaders.map((label, idx) => (
              <th key={`h-${label}`} className={`pd-num pd-th-sub-2${idx === 0 ? " pd-group-start" : ""}`}>{label}</th>
            ))}
          </tr>
        </thead>
        {detalle ? (
          <>
            {phoenixGrupalAlFinal(rows).map((row, idx) => (
              <tbody key={`iv-detalle-${row.ejecutivo}-${idx}`} className="pd-tbody-group">
                {renderDetalleBloque(row, `iv-detalle-${idx}`)}
              </tbody>
            ))}
            {total && <tbody className="pd-tbody-group">{renderDetalleBloque(total, "iv-detalle-total", true)}</tbody>}
          </>
        ) : (
          <tbody>
            {phoenixGrupalAlFinal(rows).map((row, idx) => renderRow(row, `itau-vencida-${row.ejecutivo}-${idx}`))}
            {total && renderRow(total, "itau-vencida-total", true)}
          </tbody>
        )}
      </table>
    );
  }

  return (
    <div className="pd-page">
      <PageHeader
        title="Itaú Vencida"
        subtitle="Productividad y contención de cartera vencida Itaú."
        actions={
          <button type="button" className="pd-btn pd-btn-ghost" onClick={logout}>
            <i className="bi bi-box-arrow-right" aria-hidden="true" /> Cerrar sesión
          </button>
        }
      />

      <FilterBar
        actions={
          <button type="button" className="pd-btn pd-btn-secondary" onClick={() => setMetasOpen(true)}>
            <i className="bi bi-info-circle" aria-hidden="true" /> Metas
          </button>
        }
        note={`Base: contención Phoenix ${formatDate(metadata.fecha_carga || filters.fecha_carga) || "N/D"} · Mes metas/carterizado: ${formatDate(metadata.periodo) || "N/D"}`}
      >
        <Field label="Fecha de carga">
          <select className="form-select" value={filters.fecha_carga} onChange={(e) => onFilter("fecha_carga", e.target.value)}>
            {options.fechas_carga.map((value) => (
              <option key={value} value={value}>
                {formatDate(value)}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Ejecutivo">
          <select className="form-select" value={filters.ejecutivo} onChange={(e) => onFilter("ejecutivo", e.target.value)}>
            <option value="">Todos</option>
            {options.ejecutivos.map((value) => (
              <option key={value} value={value}>
                {String(value).toUpperCase()}
              </option>
            ))}
          </select>
        </Field>
      </FilterBar>

      {error && <div className="alert alert-danger">{error}</div>}

      {renderMetasDrawer()}

      <div className="pd-tabbed">
        <ViewTabs
          value={view}
          onChange={setView}
          options={[
            { value: "resumen", label: "Resumen" },
            { value: "detalle", label: "Detalle por fase" },
          ]}
        />
        <SectionCard
          exportName={exportFileName("Itau-Vencida", view, filters.fecha_carga)}
          bodyClassName=""
          footer={
            <StatusLegend items={cumplimientoLegendItems} />
          }
        >
          {loading ? (
            <LoadingState />
          ) : !filtrosMedibles.length ? (
            <div className="alert alert-warning">
              {formatDate(metadata.periodo).slice(3) || "Este mes"} no tiene casos medibles configurados, por eso no hay cumplimiento que mostrar.
              Se configuran en Panel Administrativo &gt; Itaú &gt; Casos medibles Itaú Vencida.
            </div>
          ) : (
            <div className="pd-table-scroll">{renderTable()}</div>
          )}
        </SectionCard>
      </div>
    </div>
  );
}
