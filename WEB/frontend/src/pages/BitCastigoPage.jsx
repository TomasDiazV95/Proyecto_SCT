import { useEffect, useMemo, useState } from "react";

import { fetchBitCastigoFilters, fetchBitCastigoGeneral } from "../api";
import { Field, FilterBar, LoadingState, MetasBlock, MetasButton, MetasDrawer, PageHeader, SectionCard, StatusLegend, ViewTabs, cumplimientoClass, cumplimientoLegendItems, phoenixGrupalAlFinal, exportFileName } from "../components/productividad/ui";


function formatMoney(value) {
  return new Intl.NumberFormat("es-CL", { maximumFractionDigits: 0 }).format(Number(value || 0));
}


function formatPct(value) {
  return `${(Number(value || 0) * 100).toFixed(2)}%`;
}


// Los cumplimientos de meta se muestran sin decimales.
function formatCumpl(value) {
  return `${(Number(value || 0) * 100).toFixed(0)}%`;
}


// Sin asignacion cargada para el periodo no hay base para calcular la efectividad.
function formatEfectividad(row) {
  return Number(row.monto_asignado || 0) > 0 ? formatPct(row.pct_efectividad) : "N/D";
}


// Cobertura de gestion: RUT asignados con gestion telefonica o en terreno hasta el 4to dia habil.
function formatCobertura(row) {
  if (row.pct_cobertura === null || row.pct_cobertura === undefined || !(Number(row.ruts_asignados || 0) > 0)) {
    return "N/D";
  }
  return `${Math.round(Number(row.pct_cobertura) * 100)}%`;
}


function capCumplMeta(value) {
  return Math.min(Number(value || 0), 1.3);
}


// Cumplimiento viene en fraccion (1 = 100%); el semaforo comun trabaja en escala 0-100.
function cumplimientoFraccionClass(value) {
  return cumplimientoClass(value === null || value === undefined ? null : Number(value) * 100);
}


export default function BitCastigoPage() {
  const [filters, setFilters] = useState({ periodo: "", ejecutivo: "" });
  const [options, setOptions] = useState({ periodos: [], ejecutivos: [] });
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(null);
  const [contencionFile, setContencionFile] = useState("");
  const [meta, setMeta] = useState(null);
  const [metasOpen, setMetasOpen] = useState(false);
  const [view, setView] = useState("general");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadFilters() {
      try {
        const data = await fetchBitCastigoFilters();
        setOptions(data);
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
    fetchBitCastigoFilters(filters.periodo)
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
        const data = await fetchBitCastigoGeneral(filters);
        setRows(data.rows || []);
        setTotal(data.total || null);
        setContencionFile(data.contencion_file || "");
        setMeta(data.meta ?? null);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }

    loadData();
  }, [filters]);

  function onFilter(name, value) {
    setFilters((prev) => ({ ...prev, [name]: value }));
  }

  const totalRow = useMemo(() => {
    if (!total) {
      return null;
    }
    const visibleCumplMeta = rows
      .map((row) => capCumplMeta(row.pct_cumpl_meta))
      .filter((value) => Number.isFinite(value));
    const avgCumplMeta = visibleCumplMeta.length
      ? visibleCumplMeta.reduce((acc, value) => acc + value, 0) / visibleCumplMeta.length
      : Number(total.pct_cumpl_meta || 0);

    return {
      ...total,
      pct_cumpl_meta: capCumplMeta(avgCumplMeta),
    };
  }, [rows, total]);

  function renderGeneralTable() {
    return (
      <table className="pd-table pd-table-equal">
        <thead>
          <tr>
            <th>Ejecutivo</th>
            <th className="pd-num pd-group-start">Deuda Asignada</th>
            <th className="pd-num">Recupero</th>
            <th className="pd-num">% Efectividad</th>
            <th className="pd-num">Nuevos Convenios</th>
            <th className="pd-num">% Cobertura gestión 4° día hábil</th>
            <th className="pd-num pd-th-key pd-group-start">% Cumplimiento meta</th>
          </tr>
        </thead>
        <tbody>
          {phoenixGrupalAlFinal(rows).map((row, idx) => (
            <tr key={`bit-castigo-${row.ejecutivo}-${idx}`}>
              <td className="pd-cell-ejecutivo">{row.ejecutivo}</td>
              <td className="pd-num pd-group-start">${formatMoney(row.monto_asignado)}</td>
              <td className="pd-num">${formatMoney(row.recupero_asignado)}</td>
              <td className="pd-num">{formatEfectividad(row)}</td>
              <td className="pd-num">{Number(row.nuevos_convenios || 0)}</td>
              <td className="pd-num" title={`${row.ruts_gestionados || 0} de ${row.ruts_asignados || 0} RUT`}>{formatCobertura(row)}</td>
              <td className="pd-num pd-group-start">
                <span className={cumplimientoFraccionClass(row.pct_cumpl_meta)}>{formatCumpl(capCumplMeta(row.pct_cumpl_meta))}</span>
              </td>
            </tr>
          ))}
          {totalRow && (
            <tr className="pd-row-total">
              <td>{totalRow.ejecutivo}</td>
              <td className="pd-num pd-group-start">${formatMoney(totalRow.monto_asignado)}</td>
              <td className="pd-num">${formatMoney(totalRow.recupero_asignado)}</td>
              <td className="pd-num">{formatEfectividad(totalRow)}</td>
              <td className="pd-num">{Number(totalRow.nuevos_convenios || 0)}</td>
              <td className="pd-num" title={`${totalRow.ruts_gestionados || 0} de ${totalRow.ruts_asignados || 0} RUT`}>{formatCobertura(totalRow)}</td>
              <td className="pd-num pd-group-start">
                <span className="pd-status pd-status-none">{formatCumpl(totalRow.pct_cumpl_meta)}</span>
              </td>
            </tr>
          )}
        </tbody>
      </table>
    );
  }

  // Negocios: convenios nuevos del periodo y su abono inicial (recupero de esos convenios).
  function renderNegociosTable() {
    return (
      <table className="pd-table">
        <thead>
          <tr>
            <th>Ejecutivo</th>
            <th className="pd-num pd-group-start">Nuevos Convenios</th>
            <th className="pd-num">Abono Inicial</th>
          </tr>
        </thead>
        <tbody>
          {phoenixGrupalAlFinal(rows).map((row, idx) => (
            <tr key={`bit-castigo-negocios-${row.ejecutivo}-${idx}`}>
              <td className="pd-cell-ejecutivo">{row.ejecutivo}</td>
              <td className="pd-num pd-group-start">{Number(row.nuevos_convenios || 0)}</td>
              <td className="pd-num">${formatMoney(row.abono_inicial)}</td>
            </tr>
          ))}
          {totalRow && (
            <tr className="pd-row-total">
              <td>{totalRow.ejecutivo}</td>
              <td className="pd-num pd-group-start">{Number(totalRow.nuevos_convenios || 0)}</td>
              <td className="pd-num">${formatMoney(totalRow.abono_inicial)}</td>
            </tr>
          )}
        </tbody>
      </table>
    );
  }

  return (
    <div className="pd-page">
      <PageHeader title="Banco Internacional Castigo" subtitle="Seguimiento y cumplimiento de Banco Internacional, cartera castigo." />

      <FilterBar actions={<MetasButton onClick={() => setMetasOpen(true)} />}>
        <Field label="Periodo">
          <select className="form-select" value={filters.periodo} onChange={(e) => onFilter("periodo", e.target.value)}>
            {options.periodos.map((value) => (
              <option key={value} value={value}>
                {value}
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

      <MetasDrawer open={metasOpen} onClose={() => setMetasOpen(false)} subtitle={`Vigentes para ${filters.periodo || "N/D"}`}>
        {meta ? (
          <div className="iv-drawer-grid iv-drawer-grid-single">
            <MetasBlock title="Recupero Castigo">
              <table className="pd-table pd-table-plain pd-table-compact pd-table-static">
                <thead>
                  <tr>
                    <th>Variable</th>
                    <th className="pd-num">Meta</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>Recupero castigo</td>
                    <td className="pd-num pd-cell-strong">${formatMoney(meta)}</td>
                  </tr>
                </tbody>
              </table>
            </MetasBlock>
          </div>
        ) : (
          <div className="alert alert-light border">No hay metas cargadas para este mes.</div>
        )}
        
      </MetasDrawer>

      <div className="pd-tabbed">
        <ViewTabs
          value={view}
          onChange={setView}
          options={[
            { value: "general", label: "Vista General" },
            { value: "negocios", label: "Negocios" },
          ]}
        />
        <SectionCard
          exportName={exportFileName("BIT-Castigo", view, filters.periodo)}
          bodyClassName=""
          footer={
            <>
              {view === "general" && <StatusLegend items={cumplimientoLegendItems} />}
              <span>Archivo: {contencionFile || "N/D"}</span>
            </>
          }
        >
          {loading ? <LoadingState /> : <div className="pd-table-scroll">{view === "general" ? renderGeneralTable() : renderNegociosTable()}</div>}
        </SectionCard>
      </div>
    </div>
  );
}
