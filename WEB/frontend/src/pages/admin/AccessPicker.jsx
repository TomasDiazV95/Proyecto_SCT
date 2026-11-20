import { useMemo, useState } from "react";
import { Segmented } from "../../components/productividad/ui";
import {
  ADMIN,
  ESPECIALES,
  GLOBAL,
  accesoEfectivo,
  aplicarEstado,
  alternar,
  contarCambios,
  estadoPanel,
  resumenAccesos,
} from "./accesos";

// Selector de accesos de un usuario: accesos especiales, una tarjeta por panel (en el orden del inicio)
// y, al pie, lo que el usuario vera con esa seleccion.
// bulk: asignacion masiva; cada marca es solo lo que se agrega o se quita, sin vista previa.

const ROLES_ADMIN = ["super_admin", "admin"];

function normalizar(texto) {
  return String(texto || "").normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();
}

function plural(n, uno, varios) {
  return `${n} ${n === 1 ? uno : varios}`;
}

export function CopiarAccesos({ usuarios, excluirId, onCopiar }) {
  const opciones = useMemo(
    () =>
      usuarios
        .filter((u) => u.id !== excluirId && (u.modules || []).length && !ROLES_ADMIN.includes(u.role_code))
        .sort((a, b) => String(a.full_name || a.email).localeCompare(String(b.full_name || b.email), "es")),
    [usuarios, excluirId]
  );
  return (
    <label className="pd-field pd-acc-copiar">
      <span className="pd-label">Copiar accesos de…</span>
      <select
        className="form-select"
        value=""
        onChange={(e) => {
          const origen = opciones.find((u) => String(u.id) === e.target.value);
          if (origen) {
            onCopiar(origen);
          }
        }}
      >
        <option value="">Elige un usuario con los mismos accesos</option>
        {opciones.map((u) => (
          <option key={u.id} value={u.id}>
            {u.full_name || u.email} · {plural(u.modules.length, "acceso", "accesos")}
          </option>
        ))}
      </select>
    </label>
  );
}

function PanelCard({ panel, seleccion, abiertos, onEstado, onModulo, bloqueadoPor, bulk, busqueda }) {
  const estado = estadoPanel(panel, seleccion, abiertos);
  const deshabilitado = Boolean(bloqueadoPor) || panel.soloSuperAdmin;
  const marcados = panel.modulos.filter((m) => seleccion.includes(m.code)).length;
  // Las paginas propias del panel (ej. Itau Vencida y Negocios en Administrativo) cuentan como un modulo mas.
  const total = panel.modulos.length + (panel.propio ? 1 : 0);
  const coincideTitulo = !busqueda || normalizar(panel.titulo).includes(busqueda);
  const modulosVisibles = coincideTitulo ? panel.modulos : panel.modulos.filter((m) => normalizar(m.nombre).includes(busqueda));
  const mostrarModulos = !panel.simple && (estado !== "nada" || (busqueda && !coincideTitulo));

  let contador = "";
  if (bloqueadoPor) contador = bloqueadoPor;
  else if (panel.soloSuperAdmin) contador = "Solo lo abre el super admin";
  else if (!panel.simple && estado === "todo") contador = `Todo · ${plural(total, "módulo", "módulos")}`;
  else if (!panel.simple && estado === "algunos") contador = `${marcados} de ${total}`;

  return (
    <section className={`pd-acc-panel is-${bloqueadoPor ? "incluido" : estado}${deshabilitado ? " is-disabled" : ""}`}>
      <div className="pd-acc-panel-head">
        <div className="pd-acc-panel-titulo">
          <strong>{panel.titulo}</strong>
          {contador && <span className="pd-acc-panel-contador">{contador}</span>}
        </div>
        {panel.simple ? (
          <label className="pd-acc-switch">
            <input
              type="checkbox"
              role="switch"
              checked={Boolean(bloqueadoPor) || estado === "todo"}
              disabled={deshabilitado}
              onChange={(e) => onEstado(panel, e.target.checked ? "todo" : "nada")}
            />
            <span className="pd-acc-switch-track" aria-hidden="true"><span /></span>
            <span>{bulk ? "Incluir" : "Con acceso"}</span>
          </label>
        ) : (
          !deshabilitado && (
            <Segmented
              value={estado}
              onChange={(valor) => onEstado(panel, valor)}
              options={[
                { value: "nada", label: bulk ? "—" : "Sin acceso" },
                { value: "algunos", label: "Algunos" },
                { value: "todo", label: "Todo el panel" },
              ]}
            />
          )
        )}
      </div>
      {mostrarModulos && !deshabilitado && (
        <>
          {estado === "todo" && <p className="pd-acc-nota">Incluye {total === 1 ? "su módulo" : `sus ${total} módulos`} y los que se agreguen después.</p>}
          {estado !== "todo" && panel.propio && (
            <p className="pd-acc-nota">Las páginas principales del panel solo se abren con «Todo el panel»; aquí eliges módulos sueltos.</p>
          )}
          <div className="pd-acc-modulos">
            {modulosVisibles.map((m) => {
              const incluido = estado === "todo";
              const checked = incluido || seleccion.includes(m.code);
              return (
                <label key={m.code} className={`pd-module-option${checked ? " is-selected" : ""}${incluido ? " is-included" : ""}`}>
                  <input className="form-check-input" type="checkbox" checked={checked} disabled={incluido} onChange={() => onModulo(m.code)} />
                  <span>{m.nombre}</span>
                </label>
              );
            })}
          </div>
        </>
      )}
    </section>
  );
}

export default function AccessPicker({ modules, paneles, seleccion, onChange, rol = null, original = null, bulk = false, usuarios = null, excluirId = null }) {
  const [texto, setTexto] = useState("");
  const [abiertos, setAbiertos] = useState(() => new Set());
  const [copiado, setCopiado] = useState("");
  const busqueda = normalizar(texto.trim());
  const rolAdmin = !bulk && ROLES_ADMIN.includes(rol);
  const conGlobal = !bulk && seleccion.includes(GLOBAL);

  const visibles = useMemo(
    () =>
      paneles.filter(
        (p) => !busqueda || normalizar(p.titulo).includes(busqueda) || p.modulos.some((m) => normalizar(m.nombre).includes(busqueda))
      ),
    [paneles, busqueda]
  );
  const especialesVisibles = ESPECIALES.filter((e) => !busqueda || normalizar(`${e.titulo} ${e.detalle}`).includes(busqueda));

  const vista = useMemo(() => {
    if (bulk) {
      return null;
    }
    const acceso = accesoEfectivo(rol, seleccion, modules);
    return resumenAccesos(rol, seleccion, acceso, paneles);
  }, [bulk, rol, seleccion, modules, paneles]);
  const cambios = original ? contarCambios(original, seleccion) : 0;

  function onEstado(panel, estado) {
    setAbiertos((prev) => {
      const sig = new Set(prev);
      if (estado === "algunos") sig.add(panel.code);
      else sig.delete(panel.code);
      return sig;
    });
    onChange(aplicarEstado(panel, seleccion, estado));
  }

  function copiar(origen) {
    onChange([...(origen.modules || [])]);
    setAbiertos(new Set());
    setCopiado(`Se copiaron los accesos de ${origen.full_name || origen.email}. Revísalos antes de guardar.`);
  }

  return (
    <div className="pd-acc">
      {rolAdmin && (
        <div className="pd-acc-aviso">
          <i className="bi bi-shield-check" aria-hidden="true" /> Con el rol {rol === "super_admin" ? "super administrador" : "administrador"} ve todos los paneles; los accesos marcados no cambian nada.
        </div>
      )}

      <div className="pd-acc-tools">
        <label className="pd-field pd-acc-buscar">
          <span className="pd-label">Buscar panel o módulo</span>
          <span className="pd-acc-buscar-input">
            <i className="bi bi-search" aria-hidden="true" />
            <input className="form-control" value={texto} onChange={(e) => setTexto(e.target.value)} placeholder="Ej: SC Tardía, KPI, Veritus" />
          </span>
        </label>
        {usuarios && <CopiarAccesos usuarios={usuarios} excluirId={excluirId} onCopiar={copiar} />}
      </div>
      {copiado && (
        <p className="pd-acc-copiado" role="status">
          <i className="bi bi-clipboard-check" aria-hidden="true" /> {copiado}
        </p>
      )}

      {especialesVisibles.length > 0 && (
        <div className="pd-acc-grupo">
          <h3 className="pd-acc-grupo-titulo">Accesos especiales</h3>
          <div className="pd-acc-especiales">
            {especialesVisibles.map((e) => {
              const on = seleccion.includes(e.code);
              return (
                <label key={e.code} className={`pd-module-option pd-acc-especial${on ? " is-selected" : ""}`}>
                  <input className="form-check-input" type="checkbox" checked={on} onChange={() => onChange(alternar(seleccion, e.code))} />
                  <span>
                    <strong>{e.titulo}</strong>
                    <small>{e.detalle}</small>
                  </span>
                </label>
              );
            })}
          </div>
        </div>
      )}

      <div className="pd-acc-grupo">
        <h3 className="pd-acc-grupo-titulo">Paneles</h3>
        {visibles.length ? (
          <div className="pd-acc-paneles">
            {visibles.map((panel) => (
              <PanelCard
                key={panel.code}
                panel={panel}
                seleccion={seleccion}
                abiertos={abiertos}
                onEstado={onEstado}
                onModulo={(code) => onChange(alternar(seleccion, code))}
                bloqueadoPor={rolAdmin ? "Incluido por el rol" : conGlobal && panel.code !== ADMIN ? "Incluido por Acceso global" : null}
                bulk={bulk}
                busqueda={busqueda}
              />
            ))}
          </div>
        ) : (
          <p className="pd-acc-vacio">Ningún panel o módulo coincide con “{texto}”.</p>
        )}
      </div>

      {vista && (
        <div className="pd-acc-resumen" aria-live="polite">
          <div className="pd-acc-resumen-linea">
            <span>
              <i className="bi bi-eye" aria-hidden="true" /> Verá{" "}
              <strong>{vista.items.length ? `${plural(vista.paneles, "panel", "paneles")} · ${plural(vista.modulos, "módulo", "módulos")}` : "nada todavía"}</strong>
            </span>
            {original && <span className={`pd-acc-cambios${cambios ? " is-dirty" : ""}`}>{cambios ? plural(cambios, "cambio sin guardar", "cambios sin guardar") : "Sin cambios"}</span>}
          </div>
          {vista.items.length > 0 && (
            <div className="pd-user-modules pd-acc-resumen-chips">
              {vista.items.map((item) => (
                <span key={item.code} className={`pd-user-module${item.completo ? " is-completo" : ""}`} title={item.detalle || undefined}>
                  {item.etiqueta}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
