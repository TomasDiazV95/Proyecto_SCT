import { useEffect, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { fetchItauVigenteFilters, fetchItauVigenteGeneral } from "../api";
import { Field, FilterBar, LoadingState, PageHeader, SectionCard, StatusLegend, ViewTabs, cumplimientoClass, cumplimientoLegendItems, exportFileName } from "../components/productividad/ui";


function formatMoney(value) {
  return `${new Intl.NumberFormat("es-CL", { maximumFractionDigits: 0 }).format(Number(value || 0) / 1e6)} M`;
}


// El recupero de castigo se muestra en pesos: la meta es de pocos millones.
function formatPesos(value) {
  if (value === null || value === undefined) {
    return "—";
  }
  return `$${new Intl.NumberFormat("es-CL", { maximumFractionDigits: 0 }).format(Number(value || 0))}`;
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


export default function ItauVigentePage() {
  const [filters, setFilters] = useState({ fecha_carga: "", ejecutivo: "" });
  const [options, setOptions] = useState({ fechas_carga: [], ejecutivos: [] });
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(null);
  const [metas, setMetas] = useState([]);
  const [castigo, setCastigo] = useState(null);
  const [metasOpen, setMetasOpen] = useState(false);
  const [view, setView] = useState("resumen");
  const [metadata, setMetadata] = useState({ fecha_carga: "", periodo: "" });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const { logout } = useAuth();

  useEffect(() => {
    async function loadFilters() {
      try {
        const data = await fetchItauVigenteFilters();
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
        const data = await fetchItauVigenteGeneral(filters);
        setRows(data.rows || []);
        setTotal(data.total || null);
        setMetas(data.metas || []);
        setCastigo(data.castigo || null);
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

  function ponderacion(producto) {
    const meta = metas.find((item) => item.producto === producto);
    return meta ? `pondera ${(Number(meta.ponderacion || 0) * 100).toFixed(0)}%` : "";
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

  function renderMetasCastigo() {
    if (!castigo) {
      return null;
    }
    return (
      <div className="iv-drawer-block iv-accent-castigo">
        <div className="iv-drawer-block-head">
          <span>Castigo Itaú Telefonía</span>
          <span className="iv-drawer-peso">Pondera {formatPct(castigo.ponderacion)}</span>
        </div>
        <table className="pd-table pd-table-plain pd-table-compact pd-table-static">
          <tbody>
            <tr>
              <td>Meta de recupero</td>
              <td className="pd-num pd-cell-strong">{formatPesos(castigo.meta)}</td>
            </tr>
            <tr>
              <td>Recupero grupal (suma de los ejecutivos)</td>
              <td className="pd-num pd-cell-strong">{formatPesos(castigo.recupero)}</td>
            </tr>
          </tbody>
        </table>
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
        <aside className="pd-drawer" role="dialog" aria-modal="true" aria-labelledby="ivg-drawer-title">
          <div className="pd-drawer-header">
            <div>
              <h2 id="ivg-drawer-title" className="pd-section-title">Metas del mes</h2>
              <p className="pd-section-desc">Vigentes para {formatDate(metadata.periodo) || "N/D"}</p>
            </div>
            <button type="button" className="btn-close" aria-label="Cerrar" onClick={() => setMetasOpen(false)} />
          </div>

          <div className="pd-drawer-body">
            {metas.length || castigo ? (
              <div className="iv-drawer-grid">
                {renderMetasProducto("CONSUMO", "Contención Consumo", "iv-accent-consumo")}
                {renderMetasProducto("HIPOTECARIO", "Contención Hipotecario", "iv-accent-hipot")}
                {renderMetasCastigo()}
              </div>
            ) : (
              <div className="alert alert-light border">No hay metas cargadas para este mes.</div>
            )}
            <p className="pd-small pd-muted">
              El cumplimiento máximo es de 130% por variable. Cada caso se asigna al ejecutivo con la mejor gestión del mes.
            </p>
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

  function renderCastigoCells(row) {
    return (
      <>
        <td className="pd-num pd-group-start">{formatPesos(row.castigo_recupero)}</td>
        <td className="pd-num">
          <span className={cumplimientoFraccionClass(row.castigo_cumplimiento)}>{formatCumpl(row.castigo_cumplimiento)}</span>
        </td>
      </>
    );
  }

  function renderFinalCell(row) {
    return (
      <td className="pd-num pd-group-start">
        <span className={cumplimientoFraccionClass(row.cumplimiento)}>{formatCumpl(row.cumplimiento)}</span>
      </td>
    );
  }

  function renderRow(row, key, isTotal = false) {
    return (
      <tr key={key} className={isTotal ? "pd-row-total" : undefined}>
        <td className={isTotal ? undefined : "pd-cell-ejecutivo"}>{row.ejecutivo}</td>
        {renderGroupCells(row, "consumo")}
        {renderGroupCells(row, "hipotecario")}
        {renderCastigoCells(row)}
        {renderFinalCell(row)}
      </tr>
    );
  }

  function renderFaseCells(fase, producto) {
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
          {/* El castigo y el cumplimiento final no se abren por fase. */}
          <td colSpan={2} className="pd-num pd-group-start pd-cell-muted">—</td>
          <td className="pd-num pd-group-start pd-cell-muted">—</td>
        </tr>
      )),
      <tr key={`${keyPrefix}-subtotal`} className={isTotal ? "pd-row-total" : "pd-row-subtotal"}>
        {!fases.length && <td className={isTotal ? undefined : "pd-cell-ejecutivo"}>{row.ejecutivo}</td>}
        <td className="pd-center pd-cell-strong">Total</td>
        {renderGroupCells(row, "consumo")}
        {renderGroupCells(row, "hipotecario")}
        {renderCastigoCells(row)}
        {renderFinalCell(row)}
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
              Consumo <span className="pd-th-note">{ponderacion("CONSUMO")}</span>
            </th>
            <th colSpan={4} className="pd-th-group-2 pd-group-start">
              Hipotecario <span className="pd-th-note">{ponderacion("HIPOTECARIO")}</span>
            </th>
            <th colSpan={2} className="pd-th-group pd-group-start">
              Castigo{" "}
              <span className="pd-th-note">
                {castigo ? `meta ${formatPesos(castigo.meta)} · pondera ${(Number(castigo.ponderacion || 0) * 100).toFixed(0)}%` : ""}
              </span>
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
            <th className="pd-num pd-group-start">Recupero</th>
            <th className="pd-num">Cumplimiento grupal</th>
          </tr>
        </thead>
        {detalle ? (
          <>
            {rows.map((row, idx) => (
              <tbody key={`ivg-detalle-${row.ejecutivo}-${idx}`} className="pd-tbody-group">
                {renderDetalleBloque(row, `ivg-detalle-${idx}`)}
              </tbody>
            ))}
            {total && <tbody className="pd-tbody-group">{renderDetalleBloque(total, "ivg-detalle-total", true)}</tbody>}
          </>
        ) : (
          <tbody>
            {rows.map((row, idx) => renderRow(row, `itau-vigente-${row.ejecutivo}-${idx}`))}
            {total && renderRow(total, "itau-vigente-total", true)}
          </tbody>
        )}
      </table>
    );
  }

  return (
    <div className="pd-page">
      <PageHeader
        title="Itaú Vigente"
        subtitle="Productividad, contención vigente y recupero castigo de los ejecutivos telefónicos Itaú."
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
        note={`Base: contención Phoenix ${formatDate(metadata.fecha_carga || filters.fecha_carga) || "N/D"}, fases 1 a 3 Call y Contact Center · Recupero castigo: ${formatDate(castigo?.fecha_recupero) || "N/D"}`}
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
          exportName={exportFileName("Itau-Vigente", view, filters.fecha_carga)}
          bodyClassName=""
          footer={
            <StatusLegend items={cumplimientoLegendItems} />
          }
        >
          {loading ? <LoadingState /> : <div className="pd-table-scroll">{renderTable()}</div>}
        </SectionCard>
      </div>
    </div>
  );
}
