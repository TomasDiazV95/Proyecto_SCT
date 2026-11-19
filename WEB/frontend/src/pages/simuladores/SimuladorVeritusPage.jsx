import React, { useEffect, useMemo, useRef, useState } from "react";
import { fetchVeritusDeudor } from "../../api";
import { PageHeader, SectionCard } from "../../components/productividad/ui";
import { fecha, fechaAInput, pesos } from "./simuladorRenegociacion";
import {
  CUOTA_MINIMA,
  PRODUCTOS,
  cuotasSugeridas,
  descuentoDeMonto,
  formatearRut,
  montoConDescuento,
  resumenCliente,
  simular,
} from "./simuladorVeritus";
import "./simuladores.css";

// Mismo esquema que el simulador Itau: formulario a la izquierda y ficha del plan a la derecha.
// El RUT trae la deuda desde la asignacion Veritus del mes; el calculo corre en el navegador.

const BREADCRUMB = [{ label: "Inicio", to: "/" }];

// ---- Entrada de numeros al estilo chileno ----
function soloDigitos(texto) {
  return String(texto ?? "").replace(/\D/g, "");
}

function miles(texto) {
  const digitos = soloDigitos(texto);
  return digitos ? new Intl.NumberFormat("es-CL").format(Number(digitos)) : "";
}

function limpiarDecimal(texto) {
  const limpio = String(texto ?? "").replace(/[^\d.,]/g, "").replace(".", ",");
  const [entero, ...resto] = limpio.split(",");
  return resto.length ? `${entero},${resto.join("").replace(/,/g, "").slice(0, 1)}` : entero;
}

function decimal(texto) {
  const n = Number(String(texto ?? "").replace(",", "."));
  return Number.isFinite(n) ? n : 0;
}

function coma(valor) {
  return String(valor).replace(".", ",");
}

function plural(n, uno, varios) {
  return `${n} ${n === 1 ? uno : varios}`;
}

// Mientras se escribe solo se filtran caracteres: el RUT puede venir con o sin DV y el backend
// resuelve ambas lecturas. Al encontrarlo se muestra formateado (12.345.678-9).
function formatoRutEscrito(texto) {
  return String(texto ?? "").replace(/[^0-9kK.\-\s]/g, "").toUpperCase().slice(0, 14);
}

async function copiarTexto(texto) {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(texto);
    return;
  }
  const area = document.createElement("textarea");
  area.value = texto;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.appendChild(area);
  area.select();
  const ok = document.execCommand("copy");
  area.remove();
  if (!ok) {
    throw new Error("sin portapapeles");
  }
}

function Seccion({ numero, titulo, extra, children }) {
  return (
    <section className="sim-seccion">
      <div className="sim-seccion-head">
        <span className="sim-num" aria-hidden="true">{numero}</span>
        <h2 className="sim-seccion-titulo">{titulo}</h2>
        {extra && <span className="sim-seccion-extra">{extra}</span>}
      </div>
      {children}
    </section>
  );
}

function Campo({ label, sufijo, prefijo, hint, error, children }) {
  return (
    <label className={`sim-campo${error ? " is-invalid" : ""}`}>
      <span className="sim-label">{label}</span>
      <span className="sim-input">
        {prefijo && <span className="sim-input-pre">{prefijo}</span>}
        {children}
        {sufijo && <span className="sim-input-suf">{sufijo}</span>}
      </span>
      {error ? <span className="sim-error">{error}</span> : hint && <span className="sim-hint">{hint}</span>}
    </label>
  );
}

const FORM_VACIO = {
  saldoAjustado: "",
  descuento: coma(PRODUCTOS.convenio.descuentoMax),
  monto: "",
  cuotas: "",
  inicio: "",
};

function formVacio() {
  return { ...FORM_VACIO, inicio: fechaAInput(new Date()) };
}

// Texto bajo la cuota grande de la ficha (y etiqueta de la barra movil) segun el tipo de plan.
function subtituloPlan(r) {
  const ultima = r.cuota !== null && r.ultimaMonto !== r.cuota ? ` · última ${pesos(r.ultimaMonto)}` : "";
  if (r.pie !== null && r.modificadas === 1) {
    return `Pie ${pesos(r.pie)} + ${plural(r.libres, "cuota", "cuotas")}${ultima}`;
  }
  if (r.modificadas > 0) {
    return `${plural(r.cuotas, "cuota", "cuotas")} · ${plural(r.modificadas, "modificada", "modificadas")}`;
  }
  return `${plural(r.cuotas, "cuota", "cuotas")}${ultima}`;
}

function etiquetaBarra(r) {
  if (r.cuotas === 1) return "Pago único";
  if (r.cuota === null) return "Cuotas a medida · total";
  if (r.pie !== null && r.modificadas === 1) return `Pie + ${r.libres} cuotas de`;
  return `${r.libres} cuotas de`;
}

export default function SimuladorVeritusPage() {
  const [rutInput, setRutInput] = useState("");
  const [buscando, setBuscando] = useState(false);
  const [errorRut, setErrorRut] = useState("");
  const [deudor, setDeudor] = useState(null);
  const [verOperaciones, setVerOperaciones] = useState(false);
  const [productoCode, setProductoCode] = useState("convenio");
  const [form, setForm] = useState(formVacio);
  // Cuotas con monto puesto a mano: { indice: digitos }. "" = se esta escribiendo (cuenta como automatica).
  const [fijas, setFijas] = useState({});
  const [mostrarCalendario, setMostrarCalendario] = useState(false);
  const [aviso, setAviso] = useState("");
  const [fichaVisible, setFichaVisible] = useState(true);
  const rutRef = useRef(null);
  const fichaRef = useRef(null);
  const calendarioRef = useRef(null);
  const avisoTimer = useRef(null);
  const busquedaId = useRef(0);

  const producto = PRODUCTOS[productoCode];
  const r = useMemo(
    () =>
      simular({
        producto: productoCode,
        saldoTotal: deudor?.deuda_total || 0,
        saldoAjustado: soloDigitos(form.saldoAjustado),
        monto: soloDigitos(form.monto),
        cuotas: soloDigitos(form.cuotas),
        inicio: form.inicio,
        fijas,
      }),
    [form, productoCode, deudor, fijas]
  );
  const sinDatos = soloDigitos(form.saldoAjustado) === "";
  const errores = sinDatos ? {} : r.erroresCampo;
  const montoNum = Number(soloDigitos(form.monto)) || 0;
  const sugeridas = montoNum > 0 ? cuotasSugeridas(producto, montoNum) : null;
  const nCuotas = Number(form.cuotas) || 0;
  const nModificadas = r.calendario ? r.calendario.filter((c) => c.fija).length : 0;
  const pieAuto = r.calendario && !r.calendario[0]?.fija ? r.calendario[0]?.monto : null;

  useEffect(() => {
    rutRef.current?.focus();
  }, []);

  useEffect(() => {
    const nodo = fichaRef.current;
    if (!nodo || typeof IntersectionObserver === "undefined") {
      return undefined;
    }
    const obs = new IntersectionObserver(([entrada]) => setFichaVisible(entrada.isIntersecting), { threshold: 0.25 });
    obs.observe(nodo);
    return () => obs.disconnect();
  }, []);

  useEffect(() => () => window.clearTimeout(avisoTimer.current), []);

  useEffect(() => {
    if (mostrarCalendario) {
      calendarioRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [mostrarCalendario]);

  function flash(texto) {
    setAviso(texto);
    window.clearTimeout(avisoTimer.current);
    avisoTimer.current = window.setTimeout(() => setAviso(""), 2500);
  }

  // Carga el plan sugerido para una deuda: descuento maximo y el mayor N° de cuotas sobre el minimo.
  function planInicial(saldo, code) {
    const prod = PRODUCTOS[code];
    const monto = montoConDescuento(saldo, prod.descuentoMax);
    return {
      saldoAjustado: miles(saldo),
      descuento: coma(prod.descuentoMax),
      monto: miles(monto),
      cuotas: String(cuotasSugeridas(prod, monto)),
    };
  }

  async function buscar(e) {
    e?.preventDefault();
    const rut = rutInput.trim();
    if (!rut) {
      setErrorRut("Ingresa un RUT.");
      rutRef.current?.focus();
      return;
    }
    const id = ++busquedaId.current;
    setBuscando(true);
    setErrorRut("");
    try {
      const data = await fetchVeritusDeudor(rut);
      if (id !== busquedaId.current) {
        return;
      }
      const rutTexto = formatearRut(data.rut, data.dv);
      setDeudor({ ...data, rutTexto });
      setRutInput(rutTexto);
      setVerOperaciones(false);
      setForm((prev) => ({ ...prev, ...planInicial(data.deuda_total, productoCode) }));
      setFijas({});
    } catch (err) {
      if (id !== busquedaId.current) {
        return;
      }
      setDeudor(null);
      setErrorRut(err.message || "No se pudo buscar el RUT.");
    } finally {
      if (id === busquedaId.current) {
        setBuscando(false);
      }
    }
  }

  function elegirProducto(code) {
    setProductoCode(code);
    const prod = PRODUCTOS[code];
    setForm((prev) => {
      const monto = Number(soloDigitos(prev.monto)) || 0;
      const cuotas = Number(soloDigitos(prev.cuotas)) || 0;
      // Se conserva el monto; solo se ajustan las cuotas si pasan el maximo del producto nuevo.
      if (!monto) {
        return prev;
      }
      return { ...prev, cuotas: String(cuotas > prod.maxCuotas || !cuotas ? cuotasSugeridas(prod, monto) : cuotas) };
    });
  }

  function cambiarSaldo(valor) {
    const saldo = soloDigitos(valor);
    setForm((prev) => ({
      ...prev,
      saldoAjustado: miles(saldo),
      monto: saldo ? miles(montoConDescuento(saldo, decimal(prev.descuento))) : "",
    }));
  }

  function cambiarDescuento(valor) {
    const texto = limpiarDecimal(valor);
    setForm((prev) => {
      const saldo = soloDigitos(prev.saldoAjustado);
      const desc = Math.min(100, decimal(texto));
      return { ...prev, descuento: texto, monto: saldo ? miles(montoConDescuento(saldo, desc)) : prev.monto };
    });
  }

  function cambiarMonto(valor) {
    const monto = soloDigitos(valor);
    setForm((prev) => {
      const saldo = soloDigitos(prev.saldoAjustado);
      return { ...prev, monto: miles(monto), descuento: saldo && monto ? coma(descuentoDeMonto(saldo, monto)) : prev.descuento };
    });
  }

  // ---- Cuotas modificadas a mano ----
  function fijarCuota(indice, valor) {
    const digitos = soloDigitos(valor).slice(0, 12);
    setFijas((prev) => ({ ...prev, [indice]: digitos }));
  }

  function soltarCuota(indice) {
    setFijas((prev) => {
      const siguiente = { ...prev };
      delete siguiente[indice];
      return siguiente;
    });
  }

  // Al salir de una cuota que quedo vacia, vuelve a ser automatica.
  function cerrarCuota(indice) {
    if (fijas[indice] === "") {
      soltarCuota(indice);
    }
  }

  // Al terminar de escribir el N° de cuotas se descartan las fijadas que quedaron fuera del plan.
  function podarFijas() {
    setFijas((prev) => {
      const dentro = Object.entries(prev).filter(([indice]) => Number(indice) < nCuotas);
      return dentro.length === Object.keys(prev).length ? prev : Object.fromEntries(dentro);
    });
  }

  function limpiar() {
    busquedaId.current += 1;
    setBuscando(false);
    setRutInput("");
    setErrorRut("");
    setDeudor(null);
    setForm(formVacio());
    setFijas({});
    setAviso("");
    rutRef.current?.focus();
  }

  async function copiarResumen() {
    if (!r.ok) {
      return;
    }
    try {
      await copiarTexto(resumenCliente(deudor, r));
      flash("Copiado: pégalo en el chat o correo del cliente");
    } catch {
      flash("No se pudo copiar en este navegador");
    }
  }

  const mensajeFicha = sinDatos ? "Busca un RUT o ingresa el saldo para calcular." : r.errores?.[0];
  const pagoUnico = r.ok && r.cuotas === 1;

  return (
    <div className="pd-page sim-page sim-vt">
      <PageHeader title="Simulador de Convenios Veritus" breadcrumb={BREADCRUMB} />

      <div className="sim-layout">
        <div className="pd-card sim-form sim-no-print">
          <form className="sim-vt-buscar" onSubmit={buscar} noValidate autoComplete="off" role="search">
            <label className="sim-campo sim-vt-rut">
              <span className="sim-label">RUT del cliente</span>
              <span className={`sim-input${errorRut ? " is-error" : ""}`}>
                <span className="sim-input-pre"><i className="bi bi-person-vcard" aria-hidden="true" /></span>
                <input
                  ref={rutRef}
                  className="form-control"
                  placeholder="Ej: 12.345.678-9"
                  value={rutInput}
                  onChange={(e) => setRutInput(formatoRutEscrito(e.target.value))}
                  aria-invalid={Boolean(errorRut)}
                />
              </span>
            </label>
            <button type="submit" className="pd-btn pd-btn-primary sim-vt-btn-buscar" disabled={buscando}>
              {buscando ? <span className="spinner-border spinner-border-sm" aria-hidden="true" /> : <i className="bi bi-search" aria-hidden="true" />}
              Buscar
            </button>
            <button type="button" className="pd-btn pd-btn-secondary sim-btn-limpiar" onClick={limpiar} title="Borra el cliente y los datos ingresados">
              <i className="bi bi-eraser" aria-hidden="true" /> Limpiar
            </button>
          </form>
          {errorRut && <p className="sim-vt-error-rut" role="alert"><i className="bi bi-exclamation-circle" aria-hidden="true" /> {errorRut}</p>}

          {deudor && (
            <div className="sim-vt-deudor">
              <div className="sim-vt-deudor-head">
                <div>
                  <strong className="sim-vt-nombre">{deudor.nombre || "Sin nombre"}</strong>
                  <span className="sim-vt-rut-texto">{deudor.rutTexto}</span>
                </div>
                <div className="sim-vt-chips">
                  {deudor.banco && <span className="sim-vt-chip"><i className="bi bi-bank" aria-hidden="true" /> {deudor.banco}</span>}
                  {deudor.entidad_legal && <span className="sim-vt-chip" title="Entidad legal">{deudor.entidad_legal}</span>}
                  {deudor.portafolio && <span className="sim-vt-chip" title="Portafolio">{deudor.portafolio}</span>}
                </div>
              </div>
              <div className="sim-vt-contacto">
                <span><i className="bi bi-envelope" aria-hidden="true" /> {deudor.emails?.length ? deudor.emails.join(" · ") : "Sin correo en la ficha"}</span>
                {deudor.fonos?.length > 0 && <span><i className="bi bi-telephone" aria-hidden="true" /> {deudor.fonos.slice(0, 2).join(" · ")}{deudor.fonos.length > 2 ? ` +${deudor.fonos.length - 2}` : ""}</span>}
                <button type="button" className="sim-vt-link" aria-expanded={verOperaciones} onClick={() => setVerOperaciones((v) => !v)}>
                  {plural(deudor.operaciones.length, "operación", "operaciones")} <i className={`bi ${verOperaciones ? "bi-chevron-up" : "bi-chevron-down"}`} aria-hidden="true" />
                </button>
              </div>
              {verOperaciones && (
                <table className="pd-table pd-table-compact sim-vt-ops">
                  <thead>
                    <tr>
                      <th>Contrato</th>
                      <th>Producto</th>
                      <th>Castigo</th>
                      <th className="text-end">Saldo</th>
                    </tr>
                  </thead>
                  <tbody>
                    {deudor.operaciones.map((op) => (
                      <tr key={op.id_contrato}>
                        <td>{op.id_contrato}</td>
                        <td>{op.producto || "—"}</td>
                        <td>{op.fecha_castigo ? fecha(new Date(`${op.fecha_castigo}T00:00:00`)) : "—"}</td>
                        <td className="text-end">{pesos(op.saldo_final)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}

          <Seccion numero="1" titulo="Producto">
            <div className="sim-campanas sim-vt-productos" role="radiogroup" aria-label="Producto">
              {Object.values(PRODUCTOS).map((p) => (
                <button
                  key={p.code}
                  type="button"
                  role="radio"
                  aria-checked={productoCode === p.code}
                  title={p.detalle}
                  className={`sim-campana${productoCode === p.code ? " is-active" : ""}`}
                  onClick={() => elegirProducto(p.code)}
                >
                  <i className={`bi ${p.icono}`} aria-hidden="true" />
                  <span className="sim-campana-titulo">{p.titulo}</span>
                  <span className="sim-campana-detalle">hasta {p.maxCuotas} cuotas</span>
                </button>
              ))}
            </div>
            <p className="sim-vt-limites">
              Máx. <strong>{producto.maxCuotas}</strong> cuotas · descuento hasta <strong>{producto.descuentoMax}%</strong> · cuota mín. <strong>{pesos(CUOTA_MINIMA)}</strong>
            </p>
          </Seccion>

          <Seccion numero="2" titulo="Deuda y monto a pagar">
            <div className="sim-grid sim-grid-4">
              <Campo label="Saldo total (base)" prefijo="$" hint={deudor ? `Asignación ${deudor.periodo?.slice(4)}/${deudor.periodo?.slice(0, 4)}` : "Se llena con el RUT"}>
                <input className="form-control" value={deudor ? miles(deudor.deuda_total) : ""} placeholder="—" disabled readOnly />
              </Campo>
              <Campo label="Saldo ajustado" prefijo="$" error={errores.saldoAjustado} hint={deudor && soloDigitos(form.saldoAjustado) !== String(deudor.deuda_total) ? "Distinto al de la base" : "Referencia del descuento"}>
                <input className="form-control" inputMode="numeric" placeholder="Ej: 1.500.000" value={form.saldoAjustado} onChange={(e) => cambiarSaldo(e.target.value)} />
              </Campo>
              <Campo label="Descuento" sufijo="%" hint={`Máx. ${producto.descuentoMax}%`} error={decimal(form.descuento) > producto.descuentoMax ? `Supera el ${producto.descuentoMax}%` : null}>
                <input className="form-control" inputMode="decimal" value={form.descuento} onChange={(e) => cambiarDescuento(e.target.value)} />
              </Campo>
              <Campo label="Total a pagar" prefijo="$" error={errores.monto}>
                <input className="form-control sim-vt-monto" inputMode="numeric" placeholder="—" value={form.monto} onChange={(e) => cambiarMonto(e.target.value)} />
              </Campo>
            </div>
          </Seccion>

          <Seccion numero="3" titulo="Cuotas">
            <div className="sim-grid sim-grid-4">
              <Campo
                label="N° de cuotas"
                sufijo={`de ${producto.maxCuotas}`}
                error={errores.cuotas || (Number(form.cuotas) > producto.maxCuotas ? `Máximo ${producto.maxCuotas}` : null)}
                hint={sugeridas ? `Sugerido: ${sugeridas} (cuota ≥ ${pesos(CUOTA_MINIMA)})` : null}
              >
                <input className="form-control" inputMode="numeric" placeholder={`1 a ${producto.maxCuotas}`} value={form.cuotas} onChange={(e) => setForm((prev) => ({ ...prev, cuotas: soloDigitos(e.target.value).slice(0, 2) }))} onBlur={podarFijas} />
              </Campo>
              <Campo label="Inicio (cuota 1)" error={errores.inicio}>
                <input className="form-control" type="date" value={form.inicio} onChange={(e) => setForm((prev) => ({ ...prev, inicio: e.target.value }))} />
              </Campo>
              <Campo label="Pie (cuota 1)" prefijo="$" hint={nCuotas > 1 ? (fijas[0] ? "El resto se reparte parejo" : "Opcional · en gris, el automático") : "Requiere 2 cuotas o más"}>
                <input
                  className={`form-control${fijas[0] ? " sim-vt-monto" : ""}`}
                  inputMode="numeric"
                  placeholder={pieAuto != null ? miles(pieAuto) : "Automático"}
                  value={fijas[0] !== undefined ? miles(fijas[0]) : ""}
                  onChange={(e) => fijarCuota(0, e.target.value)}
                  onBlur={() => cerrarCuota(0)}
                  disabled={nCuotas <= 1}
                />
              </Campo>
            </div>
            {errores.fijas && <p className="sim-vt-error-rut" role="alert"><i className="bi bi-exclamation-circle" aria-hidden="true" /> {errores.fijas}</p>}
            {nCuotas > 1 && (
              <p className="sim-vt-limites">
                {nModificadas > 0 ? `${plural(nModificadas, "cuota modificada", "cuotas modificadas")} a mano · ` : "¿Otra cuota distinta? "}
                <button type="button" className="sim-vt-link sim-vt-link-inline" onClick={() => setMostrarCalendario(true)}>
                  Editar cada cuota en el calendario
                </button>
                {nModificadas > 0 && (
                  <>
                    {" · "}
                    <button type="button" className="sim-vt-link sim-vt-link-inline" onClick={() => setFijas({})}>Restablecer</button>
                  </>
                )}
              </p>
            )}
          </Seccion>

          <label className="sim-switch">
            <input type="checkbox" role="switch" checked={mostrarCalendario} onChange={(e) => setMostrarCalendario(e.target.checked)} />
            <span className="sim-switch-track" aria-hidden="true"><span /></span>
            <i className="bi bi-calendar-week" aria-hidden="true" />
            <span>Mostrar calendario de cuotas</span>
            {r.ok && <span className="sim-switch-meta">{plural(r.cuotas, "cuota", "cuotas")}{r.modificadas > 0 ? ` · ${r.modificadas} a mano` : ""}</span>}
          </label>
        </div>

        <aside className="sim-ficha" ref={fichaRef} aria-live="polite">
          <div className="sim-ficha-top">
            <div className="sim-ficha-fila">
              <span className="sim-ficha-label">{pagoUnico ? "Pago único" : r.ok && r.cuota === null ? "Total en cuotas a medida" : "Cuota mensual"}</span>
              <span className="sim-ficha-etiqueta"><i className={`bi ${producto.icono}`} aria-hidden="true" /> {producto.titulo}</span>
            </div>
            <span className={`sim-ficha-cuota${r.ok ? "" : " is-empty"}`} key={r.ok ? `${r.cuota}-${r.cuotas}` : "vacio"}>{r.ok ? pesos(r.cuota ?? r.monto) : "$ —"}</span>
            <span className={`sim-ficha-sub${!r.ok && !sinDatos ? " is-error" : ""}`}>
              {r.ok
                ? pagoUnico
                  ? `Total con ${coma(r.descuento)}% de descuento`
                  : subtituloPlan(r)
                : mensajeFicha}
            </span>
          </div>

          <dl className="sim-ficha-datos">
            <div><dt>Total a pagar</dt><dd>{r.ok ? pesos(r.monto) : "—"}</dd></div>
            <div><dt>Descuento</dt><dd>{r.ok ? `${coma(r.descuento)}%` : "—"}{r.ok && r.ahorro > 0 && <small>ahorra {pesos(r.ahorro)}</small>}</dd></div>
            <div><dt>{pagoUnico ? "Fecha de pago" : "1ª cuota"}</dt><dd>{r.ok ? fecha(r.primeraCuota) : "—"}</dd></div>
            <div><dt>Última cuota</dt><dd>{r.ok && !pagoUnico ? fecha(r.ultimaCuota) : "—"}</dd></div>
          </dl>

          {r.ok && r.alertas.length > 0 && (
            <div className="sim-vt-alerta" role="alert">
              <strong><i className="bi bi-exclamation-octagon" aria-hidden="true" /> Fuera de los límites del producto</strong>
              <ul>
                {r.alertas.map((a) => <li key={a}>{a}</li>)}
              </ul>
              <span>Se puede ofrecer igual: queda sujeto a revisión del aprobador de Veritus.</span>
            </div>
          )}
          {r.ok && r.alertas.length === 0 && (
            <div className="sim-vt-ok"><i className="bi bi-check-circle" aria-hidden="true" /> Dentro de los límites de {producto.titulo}</div>
          )}

          <div className="sim-ficha-acciones sim-no-print">
            <button type="button" className="pd-btn pd-btn-primary sim-btn-copiar" onClick={copiarResumen} disabled={!r.ok}>
              <i className="bi bi-chat-square-text" aria-hidden="true" /> Copiar resumen para el cliente
            </button>
            <button type="button" className="pd-btn pd-btn-secondary" onClick={() => window.print()} disabled={!r.ok} title="Imprimir o guardar como PDF" aria-label="Imprimir o guardar como PDF">
              <i className="bi bi-printer" aria-hidden="true" />
            </button>
          </div>
          <span className={`pd-small sim-aviso sim-no-print${aviso ? " is-visible" : ""}`} role="status">{aviso}</span>

          <p className="sim-nota">Valores referenciales. El convenio queda sujeto a aprobación de Veritus.</p>
        </aside>
      </div>

      {mostrarCalendario && (
        <div ref={calendarioRef} className="sim-tabla-bloque">
          <SectionCard
            title="Calendario de cuotas"
            description={
              r.calendario && r.cuotas > 1
                ? "Escribe el monto de cualquier cuota para fijarlo (ej. un pie más alto); las demás se reparten parejo el resto del total."
                : "Cuotas mensuales desde la fecha de inicio; la última ajusta el redondeo."
            }
            bodyClassName="pd-table-scroll sim-tabla-wrap"
            exportName={r.ok ? `Convenio_Veritus_${deudor ? deudor.rut : "simulacion"}_${fechaAInput(new Date())}` : undefined}
            actions={
              <>
                {nModificadas > 0 && (
                  <button type="button" className="pd-btn pd-btn-ghost pd-btn-sm sim-no-print pd-no-export" onClick={() => setFijas({})} title="Todas las cuotas vuelven a repartirse parejo">
                    <i className="bi bi-arrow-counterclockwise" aria-hidden="true" /> Restablecer cuotas
                  </button>
                )}
                <button type="button" className="pd-btn pd-btn-ghost pd-btn-sm sim-no-print pd-no-export" onClick={() => { setMostrarCalendario(false); window.scrollTo({ top: 0, behavior: "smooth" }); }}>
                  <i className="bi bi-x-lg" aria-hidden="true" /> Ocultar
                </button>
              </>
            }
          >
            {errores.fijas && (
              <p className="sim-vt-error-rut sim-vt-error-tabla" role="alert"><i className="bi bi-exclamation-circle" aria-hidden="true" /> {errores.fijas}</p>
            )}
            {r.calendario ? (
              <table className="pd-table pd-table-compact sim-tabla">
                <thead>
                  <tr>
                    <th>N° cuota</th>
                    <th>Vencimiento</th>
                    <th className="text-end">Monto</th>
                    <th className="text-end">Pagado acumulado</th>
                    <th className="text-end">Saldo por pagar</th>
                  </tr>
                </thead>
                <tbody>
                  {r.calendario.reduce((filas, c) => {
                    const acumulado = (filas.length ? filas[filas.length - 1].acumulado : 0) + c.monto;
                    filas.push({ ...c, acumulado });
                    return filas;
                  }, []).map((c, i) => (
                    <tr key={c.numero} className={[c.monto < CUOTA_MINIMA ? "sim-vt-bajo-minimo" : "", c.fija ? "sim-vt-fila-fija" : ""].join(" ").trim() || undefined}>
                      <td>{c.numero}{c.fija && <span className="sim-vt-tag-fija">{i === 0 ? "pie" : "a mano"}</span>}</td>
                      <td>{fecha(c.vencimiento)}</td>
                      <td className="text-end">
                        {r.cuotas > 1 ? (
                          <span className="sim-vt-cuota-edit">
                            <span aria-hidden="true">$</span>
                            <input
                              className={`sim-vt-cuota-input${c.fija ? " is-fija" : ""}`}
                              inputMode="numeric"
                              aria-label={`Monto de la cuota ${c.numero}`}
                              title={c.fija ? "Monto fijado a mano" : "Escribe un monto para fijar esta cuota"}
                              value={fijas[i] !== undefined ? miles(fijas[i]) : miles(c.monto)}
                              style={{ width: `${Math.max(9, (fijas[i] !== undefined ? miles(fijas[i]) : miles(c.monto)).length + 2)}ch` }}
                              onChange={(e) => fijarCuota(i, e.target.value)}
                              onBlur={() => cerrarCuota(i)}
                              onFocus={(e) => e.target.select()}
                            />
                            {fijas[i] !== undefined ? (
                              <button type="button" className="sim-vt-cuota-reset sim-no-print pd-no-export" title="Volver al monto automático" aria-label={`Volver al monto automático en la cuota ${c.numero}`} onClick={() => soltarCuota(i)}>
                                <i className="bi bi-x-circle" aria-hidden="true" />
                              </button>
                            ) : (
                              <span className="sim-vt-cuota-reset sim-no-print pd-no-export" aria-hidden="true" />
                            )}
                          </span>
                        ) : (
                          pesos(c.monto)
                        )}
                      </td>
                      <td className="text-end">{pesos(c.acumulado)}</td>
                      <td className="text-end">{pesos(r.monto - c.acumulado)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="sim-vacio">
                <i className="bi bi-calendar-week" aria-hidden="true" />
                <span>{mensajeFicha}</span>
              </div>
            )}
          </SectionCard>
        </div>
      )}

      {r.ok && !fichaVisible && (
        <button type="button" className="sim-barra-movil sim-no-print" onClick={() => fichaRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })}>
          <span>
            <span className="sim-barra-label">{etiquetaBarra(r)}</span>
            <strong>{pesos(r.cuota ?? r.monto)}</strong>
          </span>
          <span className="sim-barra-extra">total {pesos(r.monto)}</span>
          <i className="bi bi-chevron-up" aria-hidden="true" />
        </button>
      )}
    </div>
  );
}
