import { useEffect, useMemo, useState } from "react";

import { fetchProcuradoresDetalle, fetchProcuradoresFilters, fetchProcuradoresGeneral, saveProcuradoresLogros } from "../../api";
import { useAuth } from "../../auth/AuthContext";
import { Drawer, EmptyRow, Field, FilterBar, LoadingState, MetasBlock, MetasButton, MetasDrawer, PageHeader, SectionCard, StatusLegend, ViewTabs, cumplimientoClass, cumplimientoLegendItems, exportFileName } from "../../components/productividad/ui";
import useDataVersion, { fechaVigente } from "../../hooks/useDataVersion";


const VARIABLES = [
  { key: "notificaciones", label: "Notif." },
  { key: "embargos", label: "Embargos" },
  { key: "oficios", label: "Oficios" },
  { key: "incautaciones", label: "Incaut." },
  { key: "recupero", label: "Recup. Castigo (MM$)" },
  { key: "gestion_judicial", label: "Gestión Judicial" },
];

const NOMBRE_VARIABLE = {
  notificaciones: "Notificaciones",
  embargos: "Embargos",
  oficios: "Oficios",
  incautaciones: "Incautaciones",
  recupero: "Recupero castigo (MM$)",
  gestion_judicial: "Gestión judicial (%)",
};

const PESTANAS_GESTION = [
  { value: "notificaciones", label: "Notificaciones", icon: "bi-envelope" },
  { value: "embargos", label: "Embargos", icon: "bi-lock" },
  { value: "oficios", label: "Oficios", icon: "bi-file-earmark-text" },
  { value: "incautaciones", label: "Incautaciones", icon: "bi-truck" },
];

const ES_MANUAL = (variable) => variable === "recupero" || variable === "gestion_judicial";


function formatNumero(value) {
  return new Intl.NumberFormat("es-CL", { maximumFractionDigits: 2 }).format(Number(value || 0));
}


function formatValor(variable, value) {
  return variable === "gestion_judicial" ? `${formatNumero(value)}%` : formatNumero(value);
}


function formatPct(value) {
  return `${(Number(value || 0) * 100).toFixed(0)}%`;
}


// Cumplimiento viene en fraccion (1 = 100%); el semaforo comun trabaja en escala 0-100.
function cumplimientoFraccionClass(value) {
  return cumplimientoClass(value === null || value === undefined ? null : Number(value) * 100);
}


function CeldaVariable({ variable, dato, mapeada }) {
  if (!dato) {
    return <span className="pd-muted">—</span>;
  }
  const sinLogro = dato.logro === null || dato.logro === undefined;
  const titulo = dato.meta === null ? "Sin meta: no suma al cumplimiento" : `Peso ${formatPct(dato.peso)}${dato.grupal ? " · meta grupal de la cartera" : ""}`;
  return (
    <span title={titulo}>
      <span className="pd-cell-strong">{sinLogro ? (dato.manual ? "Pendiente" : "N/D") : formatValor(variable, dato.logro)}</span>
      {dato.meta !== null && <span className="pd-muted"> / {formatValor(variable, dato.meta)}</span>}
      {dato.grupal && <span className="pd-muted pd-small"> grupal</span>}
      <br />
      {dato.meta === null ? (
        <span className="pd-muted pd-small">sin meta</span>
      ) : (
        <span className={cumplimientoFraccionClass(mapeada || dato.manual ? dato.cumplimiento : null)}>{sinLogro ? "N/D" : formatPct(dato.cumplimiento)}</span>
      )}
    </span>
  );
}


export default function ProcuradoresPage() {
  const dataVersion = useDataVersion();
  const { user } = useAuth();
  const puedeEditar = user?.role === "super_admin";
  const [periodo, setPeriodo] = useState("");
  const [periodos, setPeriodos] = useState([]);
  const [carteraFiltro, setCarteraFiltro] = useState("");
  const [opcionesCartera, setOpcionesCartera] = useState([]);
  const [data, setData] = useState(null);
  const [view, setView] = useState("general");
  const [detalle, setDetalle] = useState(null);
  const [detalleLoading, setDetalleLoading] = useState(false);
  const [usuarioDetalle, setUsuarioDetalle] = useState("");
  const [metasOpen, setMetasOpen] = useState(false);
  const [logrosOpen, setLogrosOpen] = useState(false);
  const [logros, setLogros] = useState({});
  const [guardando, setGuardando] = useState(false);
  const [errorLogros, setErrorLogros] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchProcuradoresFilters()
      .then((body) => {
        setPeriodos(body.periodos || []);
        setOpcionesCartera(body.carteras || []);
        setPeriodo((prev) => fechaVigente(prev, periodos, body.periodos || []));
      })
      .catch((err) => setError(err.message));
  }, [dataVersion]);

  useEffect(() => {
    if (!periodo) {
      return undefined;
    }
    let vigente = true;
    setLoading(true);
    setError("");
    fetchProcuradoresGeneral(periodo)
      .then((body) => vigente && setData(body))
      .catch((err) => vigente && setError(err.message))
      .finally(() => vigente && setLoading(false));
    return () => {
      vigente = false;
    };
  }, [periodo, dataVersion]);

  // Las pestañas de gestión comparten el detalle del periodo: se pide una vez y se filtra en memoria.
  const enGestion = view !== "general";

  useEffect(() => {
    if (!periodo || !enGestion) {
      return undefined;
    }
    let vigente = true;
    setDetalleLoading(true);
    fetchProcuradoresDetalle(periodo)
      .then((body) => vigente && setDetalle(body.rows || []))
      .catch((err) => vigente && setError(err.message))
      .finally(() => vigente && setDetalleLoading(false));
    return () => {
      vigente = false;
    };
  }, [periodo, enGestion, dataVersion]);

  useEffect(() => {
    setUsuarioDetalle("");
  }, [view, carteraFiltro]);

  const carteras = useMemo(
    () => (data?.carteras || []).filter((item) => !carteraFiltro || item.cartera === carteraFiltro),
    [data, carteraFiltro]
  );
  const metasManuales = useMemo(() => (data?.metas || []).filter((meta) => ES_MANUAL(meta.variable)), [data]);
  const detalleVista = useMemo(
    () => (detalle || []).filter((row) => row.variable === view && (!carteraFiltro || row.cartera === carteraFiltro)),
    [detalle, view, carteraFiltro]
  );
  const usuariosDetalle = useMemo(() => Array.from(new Set(detalleVista.map((row) => row.usuario))).sort(), [detalleVista]);
  const detalleFiltrado = useMemo(
    () => detalleVista.filter((row) => !usuarioDetalle || row.usuario === usuarioDetalle),
    [detalleVista, usuarioDetalle]
  );

  function claveLogro(meta) {
    return `${meta.cartera}|${meta.ejecutivo}|${meta.variable}`;
  }

  function abrirLogros() {
    setLogros(Object.fromEntries(metasManuales.map((meta) => [claveLogro(meta), meta.logro_manual ?? ""])));
    setErrorLogros("");
    setLogrosOpen(true);
  }

  async function guardarLogros() {
    setGuardando(true);
    setErrorLogros("");
    try {
      const valores = metasManuales.map((meta) => {
        const texto = String(logros[claveLogro(meta)] ?? "").trim().replace(",", ".");
        return { cartera: meta.cartera, ejecutivo: meta.ejecutivo, variable: meta.variable, valor: texto === "" ? null : Number(texto) };
      });
      if (valores.some((item) => item.valor !== null && !Number.isFinite(item.valor))) {
        throw new Error("Revisa los valores: deben ser números.");
      }
      await saveProcuradoresLogros(periodo, valores);
      setData(await fetchProcuradoresGeneral(periodo));
      setLogrosOpen(false);
    } catch (err) {
      setErrorLogros(err.message);
    } finally {
      setGuardando(false);
    }
  }

  function renderCartera(item) {
    // Cada cartera muestra solo sus variables (Gestión Judicial es solo de Tanner).
    const columnas = VARIABLES.filter((variable) => item.rows.some((row) => row.variables[variable.key]));
    return (
      <SectionCard
        key={item.cartera}
        title={item.titulo}
        description={item.mapeada ? "" : "Sin mapear en el CRM judicial: solo se muestran las metas."}
        exportName={exportFileName("Procuradores", item.titulo, periodo)}
        bodyClassName=""
        footer={<StatusLegend items={cumplimientoLegendItems} />}
      >
        <div className="pd-table-scroll">
          <table className="pd-table">
            <thead>
              <tr>
                <th>Procurador</th>
                {columnas.map((variable) => (
                  <th key={variable.key} className="pd-num">{variable.label}</th>
                ))}
                <th className="pd-num pd-th-key pd-group-start">% Cumplimiento</th>
              </tr>
            </thead>
            <tbody>
              {item.rows.map((row) => (
                <tr key={`${item.cartera}-${row.ejecutivo}`}>
                  <td className="pd-cell-ejecutivo">{row.ejecutivo}</td>
                  {columnas.map((variable) => (
                    <td key={variable.key} className="pd-num">
                      <CeldaVariable variable={variable.key} dato={row.variables[variable.key]} mapeada={item.mapeada} />
                    </td>
                  ))}
                  <td className="pd-num pd-group-start" title={row.pendientes.length ? `Falta: ${row.pendientes.join(", ")}` : undefined}>
                    <span className={cumplimientoFraccionClass(row.cumplimiento)}>{row.cumplimiento === null ? "N/D" : formatPct(row.cumplimiento)}</span>
                  </td>
                </tr>
              ))}
              {!item.rows.length && <EmptyRow colSpan={columnas.length + 2} />}
            </tbody>
          </table>
        </div>
      </SectionCard>
    );
  }

  function renderDetalle() {
    return (
      <table className="pd-table pd-table-compact pd-table-plain">
        <thead>
          <tr>
            <th>Cartera</th>
            <th>Operación</th>
            <th>Usuario</th>
            <th>Tribunal</th>
            <th>Fecha</th>
          </tr>
        </thead>
        <tbody>
          {detalleFiltrado.map((row) => (
            <tr key={`${row.variable}-${row.cartera}-${row.op}-${row.usuario}`}>
              <td>{row.cartera_titulo}</td>
              <td>{row.op}</td>
              <td className="pd-cell-ejecutivo">{row.usuario}</td>
              <td>{row.tribunal}</td>
              <td>{row.fecha}</td>
            </tr>
          ))}
          {!detalleFiltrado.length && <EmptyRow colSpan={5} text="No hay gestiones para los filtros seleccionados." />}
        </tbody>
      </table>
    );
  }

  return (
    <div className="pd-page">
      <PageHeader title="Procuradores" subtitle="Gestiones judiciales y cumplimiento de metas por cartera." />

      <FilterBar
        actions={
          <>
            {puedeEditar && (
              <button type="button" className="pd-btn pd-btn-secondary" onClick={abrirLogros} disabled={!metasManuales.length}>
                <i className="bi bi-pencil-square" aria-hidden="true" /> Ingresar logros
              </button>
            )}
            <MetasButton onClick={() => setMetasOpen(true)} />
          </>
        }
      >
        <Field label="Periodo">
          <select className="form-select" value={periodo} onChange={(e) => setPeriodo(e.target.value)}>
            {periodos.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Cartera">
          <select className="form-select" value={carteraFiltro} onChange={(e) => setCarteraFiltro(e.target.value)}>
            <option value="">Todas</option>
            {opcionesCartera.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </Field>
      </FilterBar>

      {error && <div className="alert alert-danger">{error}</div>}

      <MetasDrawer open={metasOpen} onClose={() => setMetasOpen(false)} subtitle={`Vigentes para ${periodo || "N/D"}. Tope de ${formatPct(data?.tope_cumplimiento)} por variable.`}>
        <div className="iv-drawer-grid iv-drawer-grid-single">
          {(data?.carteras || []).map((item) => (
            <MetasBlock key={item.cartera} title={item.titulo}>
              <table className="pd-table pd-table-plain pd-table-compact pd-table-static">
                <thead>
                  <tr>
                    <th>Procurador</th>
                    <th>Variable</th>
                    <th className="pd-num">Peso</th>
                    <th className="pd-num">Meta</th>
                  </tr>
                </thead>
                <tbody>
                  {data.metas.filter((meta) => meta.cartera === item.cartera).map((meta) => (
                    <tr key={claveLogro(meta)}>
                      <td>{meta.ejecutivo === "GRUPAL" ? "Grupal" : meta.ejecutivo}</td>
                      <td>{NOMBRE_VARIABLE[meta.variable]}</td>
                      <td className="pd-num">{formatPct(meta.peso)}</td>
                      <td className="pd-num pd-cell-strong">{formatValor(meta.variable, meta.meta)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </MetasBlock>
          ))}
        </div>
      </MetasDrawer>

      <Drawer
        open={logrosOpen}
        onClose={() => setLogrosOpen(false)}
        className="pd-drawer-logros"
        title="Ingresar logros"
        subtitle={`Recupero castigo y gestión judicial de ${periodo}. Déjalo vacío si aún no está.`}
        footer={
          <>
            <button type="button" className="pd-btn pd-btn-secondary" onClick={() => setLogrosOpen(false)} disabled={guardando}>Cancelar</button>
            <button type="button" className="pd-btn pd-btn-primary" onClick={guardarLogros} disabled={guardando}>{guardando ? "Guardando..." : "Guardar"}</button>
          </>
        }
      >
        {errorLogros && <div className="alert alert-danger">{errorLogros}</div>}
        <table className="pd-table pd-table-plain pd-table-compact pd-table-static">
          <thead>
            <tr>
              <th>Cartera</th>
              <th>Procurador</th>
              <th>Variable</th>
              <th className="pd-num">Meta</th>
              <th className="pd-num">Logro</th>
            </tr>
          </thead>
          <tbody>
            {metasManuales.map((meta) => (
              <tr key={claveLogro(meta)}>
                <td>{meta.cartera_titulo}</td>
                <td>{meta.ejecutivo === "GRUPAL" ? "Grupal" : meta.ejecutivo}</td>
                <td>{NOMBRE_VARIABLE[meta.variable]}</td>
                <td className="pd-num">{formatValor(meta.variable, meta.meta)}</td>
                <td className="pd-num">
                  <input
                    className="form-control"
                    inputMode="decimal"
                    aria-label={`Logro de ${NOMBRE_VARIABLE[meta.variable]}, ${meta.cartera_titulo}, ${meta.ejecutivo}`}
                    value={logros[claveLogro(meta)] ?? ""}
                    onChange={(e) => setLogros((prev) => ({ ...prev, [claveLogro(meta)]: e.target.value }))}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Drawer>

      <div className="pd-tabbed">
        <ViewTabs
          value={view}
          onChange={setView}
          options={[
            { value: "general", label: "Vista General", icon: "bi-grid" },
            ...PESTANAS_GESTION,
          ]}
        />
        {enGestion ? (
          <SectionCard
            title={NOMBRE_VARIABLE[view]}
            description={detalleLoading || !detalle ? "" : `${detalleFiltrado.length} ${detalleFiltrado.length === 1 ? "gestión" : "gestiones"} en ${periodo}`}
            actions={
              <div className="pd-negocios-filtros pd-no-export">
                <select className="form-select form-select-sm" value={usuarioDetalle} onChange={(e) => setUsuarioDetalle(e.target.value)} aria-label="Usuario">
                  <option value="">Todos los usuarios</option>
                  {usuariosDetalle.map((nombre) => <option key={nombre} value={nombre}>{nombre}</option>)}
                </select>
              </div>
            }
            exportName={exportFileName("Procuradores", view, periodo)}
            bodyClassName=""
          >
            {detalleLoading || !detalle ? <LoadingState /> : <div className="pd-table-scroll">{renderDetalle()}</div>}
          </SectionCard>
        ) : loading && !data ? (
          <LoadingState />
        ) : (
          carteras.map(renderCartera)
        )}
      </div>
    </div>
  );
}
