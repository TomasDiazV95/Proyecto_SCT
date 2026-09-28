import { Fragment, useEffect, useMemo, useState } from "react";

import { fetchBitFilters, fetchBitGeneral, fetchBitTramos } from "../api";
import { Field, FilterBar, LoadingState, PageHeader, SectionCard, StatusLegend, ViewTabs, cumplimientoClass, cumplimientoLegendItems, phoenixGrupalAlFinal, exportFileName } from "../components/productividad/ui";

const TRAMOS = ["30-90", "90+"];
const TRAMO_GROUP_CLASS = { "30-90": "1", "90+": "2" };

function formatMoney(value) {
  return new Intl.NumberFormat("es-CL", { maximumFractionDigits: 0 }).format(Number(value || 0));
}

function formatPct(value) {
  return `${(Number(value || 0) * 100).toFixed(2)}%`;
}

function formatPctOrNd(value) {
  return value === null || value === undefined ? "N/D" : formatPct(value);
}

function capCumplMeta(value) {
  return Math.min(Number(value || 0), 1.3);
}

// Cumplimiento viene en fraccion (1 = 100%); el semaforo comun trabaja en escala 0-100.
function cumplimientoFraccionClass(value) {
  return cumplimientoClass(value === null || value === undefined ? null : Number(value) * 100);
}


export default function BitPage() {
  const [view, setView] = useState("general");
  const [filters, setFilters] = useState({ periodo: "", ejecutivo: "" });
  const [options, setOptions] = useState({ periodos: [], ejecutivos: [] });
  const [general, setGeneral] = useState({ rows: [], total: null, metas: [] });
  const [tramoData, setTramoData] = useState({ rows: [] });
  const [contencionFile, setContencionFile] = useState("");
  const [metasOpen, setMetasOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadFilters() {
      try {
        const data = await fetchBitFilters();
        setOptions({ periodos: data.periodos || [], ejecutivos: data.ejecutivos || [] });
        setFilters((prev) => ({ ...prev, periodo: data.periodos?.[0] || "" }));
      } catch (err) {
        setError(err.message);
      }
    }
    loadFilters();
  }, []);

  // Al cambiar el periodo, el filtro de ejecutivo solo ofrece los disponibles en ese periodo.
  useEffect(() => {
    if (!filters.periodo) {
      return;
    }
    fetchBitFilters(filters.periodo)
      .then((data) => {
        const disponibles = data.ejecutivos || [];
        setOptions((prev) => ({ ...prev, ejecutivos: disponibles }));
        setFilters((prev) => (prev.ejecutivo && !disponibles.includes(prev.ejecutivo) ? { ...prev, ejecutivo: "" } : prev));
      })
      .catch((err) => setError(err.message));
  }, [filters.periodo]);

  useEffect(() => {
    if (!filters.periodo) {
      return;
    }
    async function loadData() {
      setLoading(true);
      setError("");
      try {
        if (view === "general") {
          const data = await fetchBitGeneral(filters);
          setGeneral({ rows: data.rows || [], total: data.total || null, metas: data.metas || [] });
          setContencionFile(data.contencion_file || "");
        } else {
          const data = await fetchBitTramos(filters);
          setTramoData({ rows: data.rows || [] });
          setContencionFile(data.contencion_file || "");
        }
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, [view, filters]);

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

  const metaByTramo = useMemo(() => Object.fromEntries(general.metas.map((meta) => [meta.tramo, meta])), [general.metas]);

  function ponderacionLabel(tramo) {
    const ponderacion = metaByTramo[tramo]?.ponderacion;
    return ponderacion === undefined ? "" : `pondera ${Math.round(ponderacion * 100)}%`;
  }

  function renderTramoCells(row, tramo, isTotal) {
    const data = row.tramos?.[tramo];
    if (!data || (!data.monto_inicial && !data.meta_monto)) {
      return (
        <td colSpan={4} className="pd-center pd-group-start pd-cell-muted">
          Sin cartera
        </td>
      );
    }
    return (
      <>
        <td className="pd-num pd-group-start">${formatMoney(data.monto_inicial)}</td>
        <td className="pd-num">
          ${formatMoney(data.monto_contenido)}
          <span className="pd-cell-sub">{formatPct(data.pct_contencion)} contiene</span>
        </td>
        <td className="pd-num">${formatMoney(data.meta_monto)}</td>
        <td className="pd-num">
          <span className={isTotal ? "pd-status pd-status-none" : cumplimientoFraccionClass(data.cumplimiento)}>{formatPctOrNd(data.cumplimiento)}</span>
        </td>
      </>
    );
  }

  function renderGeneralRow(row, key, isTotal = false) {
    return (
      <tr key={key} className={isTotal ? "pd-row-total" : undefined}>
        <td className={isTotal ? undefined : "pd-cell-ejecutivo"}>{row.ejecutivo}</td>
        {TRAMOS.map((tramo) => (
          <Fragment key={tramo}>{renderTramoCells(row, tramo, isTotal)}</Fragment>
        ))}
        <td className="pd-num pd-group-start">
          <span className={isTotal ? "pd-status pd-status-none" : cumplimientoFraccionClass(row.cumplimiento)}>{formatPctOrNd(row.cumplimiento)}</span>
        </td>
      </tr>
    );
  }

  function renderGeneralTable() {
    const subHeaders = ["Mto Inicial", "Contenido", "Meta $", "Cumplimiento"];
    return (
      <table className="pd-table">
        <thead>
          <tr>
            <th rowSpan={2}>Ejecutivo</th>
            {TRAMOS.map((tramo) => (
              <th key={tramo} colSpan={4} className={`pd-th-group-${TRAMO_GROUP_CLASS[tramo]} pd-group-start`}>
                Tramo {tramo} <span className="pd-th-note">{ponderacionLabel(tramo)}</span>
              </th>
            ))}
            <th rowSpan={2} className="pd-num pd-th-key pd-group-start">Cumplimiento Final</th>
          </tr>
          <tr>
            {TRAMOS.map((tramo) =>
              subHeaders.map((label, idx) => (
                <th key={`${tramo}-${label}`} className={`pd-num pd-th-sub-${TRAMO_GROUP_CLASS[tramo]}${idx === 0 ? " pd-group-start" : ""}`}>
                  {label}
                </th>
              ))
            )}
          </tr>
        </thead>
        <tbody>
          {phoenixGrupalAlFinal(general.rows).map((row, idx) => renderGeneralRow(row, `bit-general-${row.ejecutivo}-${idx}`))}
          {!general.rows.length && (
            <tr>
              <td colSpan={10} className="pd-empty">Sin datos para los filtros seleccionados.</td>
            </tr>
          )}
          {general.total && general.rows.length > 0 && renderGeneralRow(general.total, "bit-general-total", true)}
        </tbody>
      </table>
    );
  }

  function renderTramoTable() {
    return (
      <table className="pd-table">
        <thead>
          <tr>
            <th>Tramo</th>
            <th className="pd-num">Mto Inicial</th>
            <th className="pd-num">Mto Contenido</th>
            <th className="pd-num">% Contiene</th>
            <th className="pd-num pd-th-key">% Cumplimiento meta</th>
          </tr>
        </thead>
        <tbody>
          {tramoData.rows.map((row, idx) => (
            <tr key={`tramo-${row.tramo}-${idx}`}>
              <td>{row.tramo}</td>
              <td className="pd-num">${formatMoney(row.monto_inicial)}</td>
              <td className="pd-num">${formatMoney(row.monto_contenido)}</td>
              <td className="pd-num">{formatPct(row.pct_contiene ?? row.pct_contencion)}</td>
              <td className="pd-num">
                <span className={cumplimientoFraccionClass(row.pct_cumpl_meta)}>{formatPct(capCumplMeta(row.pct_cumpl_meta))}</span>
              </td>
            </tr>
          ))}
          {!tramoData.rows.length && (
            <tr>
              <td colSpan={5} className="pd-empty">Sin datos para los filtros seleccionados.</td>
            </tr>
          )}
        </tbody>
      </table>
    );
  }

  function renderMetasDrawer() {
    if (!metasOpen) {
      return null;
    }
    return (
      <>
        <div className="pd-drawer-backdrop" onClick={() => setMetasOpen(false)} />
        <aside className="pd-drawer" role="dialog" aria-modal="true" aria-labelledby="bit-drawer-title">
          <div className="pd-drawer-header">
            <div>
              <h2 id="bit-drawer-title" className="pd-section-title">Metas del mes</h2>
              <p className="pd-section-desc">Vigentes para {filters.periodo || "N/D"}</p>
            </div>
            <button type="button" className="btn-close" aria-label="Cerrar" onClick={() => setMetasOpen(false)} />
          </div>
          <div className="pd-drawer-body">
            <div className="iv-drawer-grid">
              {TRAMOS.map((tramo) => {
                const meta = metaByTramo[tramo];
                return (
                  <div key={tramo} className={`iv-drawer-block ${tramo === "30-90" ? "iv-accent-consumo" : "iv-accent-hipot"}`}>
                    <div className="iv-drawer-block-head">
                      <span>Tramo {tramo}</span>
                      <span className="iv-drawer-peso">{meta ? `Pondera ${formatPct(meta.ponderacion)}` : ""}</span>
                    </div>
                    <table className="pd-table pd-table-plain pd-table-compact pd-table-static">
                      <tbody>
                        <tr>
                          <td>Meta contención</td>
                          <td className="pd-num pd-cell-strong">{meta?.meta === null || meta?.meta === undefined ? "Sin meta" : formatPct(meta.meta)}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                );
              })}
            </div>
          </div>
        </aside>
      </>
    );
  }

  return (
    <div className="pd-page">
      <PageHeader title="Banco Internacional Vigente" subtitle="Seguimiento y cumplimiento de Banco Internacional, cartera vigente." />

      <FilterBar
        actions={
          view === "general" && (
            <button type="button" className="pd-btn pd-btn-secondary" onClick={() => setMetasOpen(true)}>
              <i className="bi bi-info-circle" aria-hidden="true" /> Metas
            </button>
          )
        }
      >
        <Field label="Periodo">
          <select className="form-select" value={filters.periodo} onChange={(e) => onFilter("periodo", e.target.value)}>
            {options.periodos.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Ejecutivo">
          <select className="form-select" value={filters.ejecutivo} onChange={(e) => onFilter("ejecutivo", e.target.value)}>
            <option value="">Todos</option>
            {options.ejecutivos.map((v) => (
              <option key={v} value={v}>
                {String(v).toUpperCase()}
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
            { value: "general", label: "Vista General" },
            { value: "tramo", label: "Vista Tramo" },
          ]}
        />
        <SectionCard
          exportName={exportFileName("BIT-Vigente", view, filters.periodo)}
          bodyClassName=""
          footer={
            <>
              <StatusLegend items={cumplimientoLegendItems} />
              <span>Archivo: {contencionFile || "N/D"}</span>
            </>
          }
        >
          {loading ? <LoadingState /> : <div className="pd-table-scroll">{view === "general" ? renderGeneralTable() : renderTramoTable()}</div>}
        </SectionCard>
      </div>
    </div>
  );
}
