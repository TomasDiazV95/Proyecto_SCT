import { useEffect, useMemo, useState } from "react";

import { fetchBitCastigoFilters, fetchBitCastigoGeneral } from "../api";
import { Field, FilterBar, LoadingState, MetasBlock, MetasButton, MetasDrawer, PageHeader, SectionCard, StatusLegend, cumplimientoClass, cumplimientoLegendItems, phoenixGrupalAlFinal, exportFileName } from "../components/productividad/ui";


function formatMoney(value) {
  return new Intl.NumberFormat("es-CL", { maximumFractionDigits: 0 }).format(Number(value || 0));
}


function formatPct(value) {
  return `${(Number(value || 0) * 100).toFixed(2)}%`;
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

      <SectionCard
        exportName={exportFileName("BIT-Castigo", filters.periodo)}
        bodyClassName=""
        footer={
          <>
            <StatusLegend items={cumplimientoLegendItems} />
            <span>Archivo: {contencionFile || "N/D"}</span>
          </>
        }
      >
        {loading ? (
          <LoadingState />
        ) : (
          <div className="pd-table-scroll">
            <table className="pd-table">
              <thead>
                <tr>
                  <th rowSpan={2}>Ejecutivo</th>
                  <th colSpan={3} className="pd-th-group-1 pd-group-start">Recupero Castigo</th>
                  <th rowSpan={2} className="pd-num pd-th-key pd-group-start">% Cumplimiento meta</th>
                </tr>
                <tr>
                  <th className="pd-num pd-th-sub-1 pd-group-start">Mto Inicial</th>
                  <th className="pd-num pd-th-sub-1">Recupero</th>
                  <th className="pd-num pd-th-sub-1">% Recupero</th>
                </tr>
              </thead>
              <tbody>
                {phoenixGrupalAlFinal(rows).map((row, idx) => (
                  <tr key={`bit-castigo-${row.ejecutivo}-${idx}`}>
                    <td className="pd-cell-ejecutivo">{row.ejecutivo}</td>
                    <td className="pd-num pd-group-start">${formatMoney(row.monto_inicial)}</td>
                    <td className="pd-num">${formatMoney(row.monto_contenido)}</td>
                    <td className="pd-num">{formatPct(row.pct_contencion)}</td>
                    <td className="pd-num pd-group-start">
                      <span className={cumplimientoFraccionClass(row.pct_cumpl_meta)}>{formatPct(capCumplMeta(row.pct_cumpl_meta))}</span>
                    </td>
                  </tr>
                ))}
                {totalRow && (
                  <tr className="pd-row-total">
                    <td>{totalRow.ejecutivo}</td>
                    <td className="pd-num pd-group-start">${formatMoney(totalRow.monto_inicial)}</td>
                    <td className="pd-num">${formatMoney(totalRow.monto_contenido)}</td>
                    <td className="pd-num">{formatPct(totalRow.pct_contencion)}</td>
                    <td className="pd-num pd-group-start">
                      <span className="pd-status pd-status-none">{formatPct(totalRow.pct_cumpl_meta)}</span>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>
    </div>
  );
}
