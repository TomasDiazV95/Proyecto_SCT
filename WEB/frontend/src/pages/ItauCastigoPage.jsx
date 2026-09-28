import { useEffect, useMemo, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { fetchItauCastigoFilters, fetchItauCastigoGeneral } from "../api";
import { EmptyRow, Field, FilterBar, LoadingState, MetasBlock, MetasButton, MetasDrawer, PageHeader, SectionCard, Segmented, StatusLegend, cumplimientoClass, cumplimientoLegendItems, phoenixGrupalAlFinal, exportFileName } from "../components/productividad/ui";


function formatMoney(value) {
  return new Intl.NumberFormat("es-CL", { maximumFractionDigits: 0 }).format(Number(value || 0));
}


function formatPct(value) {
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


// Cumplimiento viene en fraccion (1 = 100%); el semaforo comun trabaja en escala 0-100.
function cumplimientoFraccionClass(value) {
  return cumplimientoClass(value === null || value === undefined ? null : Number(value) * 100);
}


export default function ItauCastigoPage() {
  const [productoTab, setProductoTab] = useState("Phoenix");
  const [filters, setFilters] = useState({ fecha_carga: "", ejecutivo: "" });
  const [options, setOptions] = useState({ fechas_carga: [], ejecutivos: [], productos: [] });
  const [rows, setRows] = useState([]);
  const [metadata, setMetadata] = useState({ fecha_carga: "", periodo: "" });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [metasOpen, setMetasOpen] = useState(false);
  const { user, logout } = useAuth();
  
  useEffect(() => {
    async function loadFilters() {
      try {
        const data = await fetchItauCastigoFilters();
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
    fetchItauCastigoFilters(filters.fecha_carga)
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
        const data = await fetchItauCastigoGeneral(filters);
        setRows(data.rows || []);
        setMetadata({ fecha_carga: data.fecha_carga || filters.fecha_carga, periodo: data.periodo || "" });
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

  // Pestañas Phoenix / Phoenix MCV: cada ejecutivo cae en la del cobrador donde tiene mas casos (cobrador_vista).
  const productoTabs = [
    { value: "Phoenix", label: "Phoenix" },
    { value: "Phoenix MCV", label: "Phoenix MCV" },
  ];

  const tabRows = useMemo(
    () => rows.filter((row) => String(row.cobrador_vista || "").trim().toUpperCase() === productoTab.toUpperCase()),
    [rows, productoTab]
  );

  // Total de la pestaña: se suma primero y se divide despues, igual que el total del backend (tope 130%).
  const tabTotal = useMemo(() => {
    if (!tabRows.length) {
      return null;
    }
    const deuda = tabRows.reduce((acc, row) => acc + Number(row.deuda_total || 0), 0);
    const recupero = tabRows.reduce((acc, row) => acc + Number(row.recupero_total || 0), 0);
    const meta = tabRows.reduce((acc, row) => acc + Number(row.meta_recupero || 0), 0);
    return {
      ejecutivo: "Total general",
      deuda_total: deuda,
      recupero_total: recupero,
      pct_efectividad: deuda ? recupero / deuda : 0,
      meta_recupero: meta,
      cumplimiento: meta ? Math.min(recupero / meta, 1.3) : 0,
    };
  }, [tabRows]);

  const generalMetas = useMemo(() => {
    const metas = new Map();
    rows.forEach((row) => {
      const cobrador = String(row.cobrador_vista || "Sin cobrador").trim();
      if (!metas.has(cobrador)) {
        metas.set(cobrador, {
          cobrador_vista: cobrador,
          meta_recupero: Number(row.meta_recupero || 0),
        });
      }
    });
    return Array.from(metas.values()).sort((a, b) => a.cobrador_vista.localeCompare(b.cobrador_vista));
  }, [rows]);

  function renderMetasDrawer() {
    return (
      <MetasDrawer open={metasOpen} onClose={() => setMetasOpen(false)} subtitle={`Vigentes para ${formatDate(metadata.periodo) || "N/D"}`}>
        {generalMetas.length ? (
          <div className="iv-drawer-grid iv-drawer-grid-single">
            <MetasBlock title="Recupero Castigo">
              <table className="pd-table pd-table-plain pd-table-compact pd-table-static">
                <thead>
                  <tr>
                    <th>Cobrador</th>
                    <th className="pd-num">Meta Recupero</th>
                  </tr>
                </thead>
                <tbody>
                  {generalMetas.map((row) => (
                    <tr key={row.cobrador_vista}>
                      <td>{row.cobrador_vista}</td>
                      <td className="pd-num pd-cell-strong">${formatMoney(row.meta_recupero)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </MetasBlock>
          </div>
        ) : (
          <div className="alert alert-light border">No hay metas cargadas para este mes.</div>
        )}
      </MetasDrawer>
    );
  }

  function renderGeneralTable() {
    const groupClass = productoTab === "Phoenix" ? 1 : 2;
    return (
      <>
        <div className="pd-card-toolbar">
          <span className="pd-label">Producto</span>
          <Segmented value={productoTab} onChange={setProductoTab} options={productoTabs} />
        </div>
        <div className="pd-table-scroll">
          <table className="pd-table">
            <thead>
              <tr>
                <th rowSpan={2}>Ejecutivo</th>
                <th colSpan={4} className={`pd-th-group-${groupClass} pd-group-start`}>{productoTab}</th>
                <th rowSpan={2} className="pd-num pd-th-key pd-group-start">Cumplimiento</th>
              </tr>
              <tr>
                {["Total Deuda", "Recupero Total", "% Efectividad", "Meta $"].map((label, idx) => (
                  <th key={label} className={`pd-num pd-th-sub-${groupClass}${idx === 0 ? " pd-group-start" : ""}`}>{label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {phoenixGrupalAlFinal(tabRows).map((row, idx) => (
                <tr key={`itau-general-${row.ejecutivo}-${idx}`}>
                  <td className="pd-cell-ejecutivo">{row.ejecutivo}</td>
                  <td className="pd-num pd-group-start">${formatMoney(row.deuda_total)}</td>
                  <td className="pd-num">${formatMoney(row.recupero_total)}</td>
                  <td className="pd-num">{formatPct(row.pct_efectividad)}</td>
                  <td className="pd-num">${formatMoney(row.meta_recupero)}</td>
                  <td className="pd-num pd-group-start">
                    <span className={cumplimientoFraccionClass(row.cumplimiento)}>{formatPct(row.cumplimiento)}</span>
                  </td>
                </tr>
              ))}
              {!tabRows.length && <EmptyRow colSpan={6} text={`Sin ejecutivos en ${productoTab} para los filtros seleccionados.`} />}
              {tabTotal && (
                <tr className="pd-row-total">
                  <td>{tabTotal.ejecutivo}</td>
                  <td className="pd-num pd-group-start">${formatMoney(tabTotal.deuda_total)}</td>
                  <td className="pd-num">${formatMoney(tabTotal.recupero_total)}</td>
                  <td className="pd-num">{formatPct(tabTotal.pct_efectividad)}</td>
                  <td className="pd-num">${formatMoney(tabTotal.meta_recupero)}</td>
                  <td className="pd-num pd-group-start">
                    <span className="pd-status pd-status-none">{formatPct(tabTotal.cumplimiento)}</span>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </>
    );
  }

  return (
    <div className="pd-page">
      <PageHeader
        title="Itaú Castigo"
        subtitle="Productividad y recupero de cartera castigada Itaú."
        actions={
          <button type="button" className="pd-btn pd-btn-ghost" onClick={logout}>
            <i className="bi bi-box-arrow-right" aria-hidden="true" /> Cerrar sesión
          </button>
        }
      />

      <FilterBar
        actions={<MetasButton onClick={() => setMetasOpen(true)} />}
        note={`Base: ${formatDate(metadata.fecha_carga || filters.fecha_carga) || "N/D"} · Mes metas/carterizado: ${formatDate(metadata.periodo) || "N/D"}`}>
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

      <SectionCard exportName={exportFileName("Itau-Castigo", productoTab, filters.fecha_carga)} bodyClassName="" footer={<StatusLegend items={cumplimientoLegendItems} />}>
        {loading ? <LoadingState /> : renderGeneralTable()}
      </SectionCard>
    </div>
  );
}
