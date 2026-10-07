import React, { useEffect, useState } from "react";
import { useAuth } from "../auth/AuthContext";

import { downloadLaAraucanaExcel, fetchLaAraucanaFilters, fetchLaAraucanaNegocios, fetchLaAraucanaResumen } from "../api";
import { EmptyRow, Field, FilterBar, LoadingState, PageHeader, SectionCard, StatusLegend, ViewTabs, aporteLegendItems, phoenixGrupalAlFinal, exportFileName } from "../components/productividad/ui";

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

// Negocios: una fila por ejecutivo con la cantidad de reprogramaciones y su monto.
function pivotNegocios(rows) {
  const grouped = new Map();
  rows.forEach((row) => {
    const current = grouped.get(row.ejecutivo) || { ejecutivo: row.ejecutivo, q_negocios: 0, monto: 0 };
    current.q_negocios += Number(row.q_negocios || 0);
    current.monto += Number(row.monto || 0);
    grouped.set(row.ejecutivo, current);
  });
  return Array.from(grouped.values()).sort((a, b) => a.ejecutivo.localeCompare(b.ejecutivo));
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
  const [rows, setRows] = useState([]);
  const [negocios, setNegocios] = useState({ rows: [], detalle: [], sin_gestion: null });
  const [loadingFilters, setLoadingFilters] = useState(true);
  const [loading, setLoading] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState("");
  const canDownload = ["super_admin", "admin", "coordinador"].includes(user?.role || "");
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
  const negocioRows = pivotNegocios(negocios.rows);
  const negocioTotal = {
    q_negocios: negocioRows.reduce((acc, row) => acc + row.q_negocios, 0),
    monto: negocioRows.reduce((acc, row) => acc + row.monto, 0),
  };
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
    if (!selected.periodo) {
      return;
    }
    // Evita que una respuesta antigua pise la de la pestana o filtro actual.
    let cancelled = false;
    async function loadResumen() {
      setLoading(true);
      setError("");
      try {
        if (view === "negocios") {
          const data = await fetchLaAraucanaNegocios({ periodo: selected.periodo, ejecutivo: selected.ejecutivo });
          if (!cancelled) {
            setNegocios({ rows: data.rows || [], detalle: data.detalle || [], sin_gestion: data.sin_gestion || null });
          }
        } else {
          const data = await fetchLaAraucanaResumen(selected);
          if (!cancelled) {
            setRows(data.rows || []);
          }
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
  }, [selected, view]);

  function onFilter(name, value) {
    setSelected((prev) => ({ ...prev, [name]: value }));
  }

  function onPeriodo(value) {
    setSelected((prev) => ({ ...prev, periodo: value }));
  }

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
      </FilterBar>

      {error && <div className="alert alert-danger">{error}</div>}

      <div className="pd-tabbed">
        <ViewTabs
          value={view}
          onChange={setView}
          options={[
            { value: "productividad", label: "Productividad" },
            { value: "negocios", label: "Negocios" },
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
                  <th>Ejecutivo</th>
                  <th className="pd-num">Reprogramación</th>
                  <th className="pd-num">Monto</th>
                </tr>
              </thead>
              <tbody>
                {phoenixGrupalAlFinal(negocioRows).map((row) => (
                  <tr key={row.ejecutivo}>
                    <td className="pd-cell-ejecutivo">{row.ejecutivo}</td>
                    <td className="pd-num">{formatMoney(row.q_negocios)}</td>
                    <td className="pd-num">{formatRecovero(row.monto)}</td>
                  </tr>
                ))}
                {!negocioRows.length && <EmptyRow colSpan={3} />}
                {negocioRows.length > 0 && (
                  <tr className="pd-row-total">
                    <td>Total</td>
                    <td className="pd-num">{formatMoney(negocioTotal.q_negocios)}</td>
                    <td className="pd-num">{formatRecovero(negocioTotal.monto)}</td>
                  </tr>
                )}
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
            (sinGestion && Number(sinGestion.q_negocios) > 0 && !selected.ejecutivo
              ? ` Fuera del resumen: ${formatMoney(sinGestion.q_negocios)} negocios sin gestion en el mes (${formatRecovero(sinGestion.monto)}).`
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
                  <th className="pd-num">Monto</th>
                  <th>Usuario</th>
                  <th>Contacto</th>
                  <th>Respuesta</th>
                  <th>Fecha gestion</th>
                  <th>Criterio</th>
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
                    <td className="pd-num">{formatRecovero(row.monto)}</td>
                    <td>{row.usuario}</td>
                    <td>{row.contacto}</td>
                    <td>{row.respuesta}</td>
                    <td>{formatFecha(row.fecha_gestion)}</td>
                    <td>{row.criterio}</td>
                  </tr>
                ))}
                {!negocios.detalle.length && <EmptyRow colSpan={11} />}
              </tbody>
            </table>
          </div>
        </SectionCard>
      )}
    </div>
  );
}
