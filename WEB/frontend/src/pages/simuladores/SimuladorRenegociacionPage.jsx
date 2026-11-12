import React, { useEffect, useMemo, useRef, useState } from "react";
import { PageHeader, SectionCard } from "../../components/productividad/ui";
import {
  CAMPANAS,
  MESES_CUOTON,
  VALORES_INICIALES,
  fecha,
  fechaAInput,
  pesos,
  resumenCliente,
  simular,
} from "./simuladorRenegociacion";
import "./simuladores.css";

// Todo en una pantalla: formulario compacto a la izquierda y ficha de pago a la derecha.

const BREADCRUMB = [
  { label: "Inicio", to: "/" },
  { label: "Simulador de Renegociaciones Itaú", to: "/simuladores" },
];

const GRACIA_OPCIONES = Array.from({ length: 13 }, (_, i) => i);

// ---- Entrada de numeros al estilo chileno: miles con punto y decimales con coma ----
function soloDigitos(texto) {
  return String(texto ?? "").replace(/\D/g, "");
}

function miles(texto) {
  const digitos = soloDigitos(texto);
  return digitos ? new Intl.NumberFormat("es-CL").format(Number(digitos)) : "";
}

// Acepta "1,99" o "1.99"; deja escribir la coma final ("1,").
function limpiarDecimal(texto) {
  const limpio = String(texto ?? "").replace(/[^\d.,]/g, "").replace(".", ",");
  const [entero, ...resto] = limpio.split(",");
  return resto.length ? `${entero},${resto.join("").replace(/,/g, "")}` : entero;
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

function formInicial(campanaCode) {
  return {
    deuda: "",
    abono: "",
    pctCuotas: coma(CAMPANAS[campanaCode].pctCuotas),
    tasa: coma(VALORES_INICIALES.tasa),
    cuotas: String(VALORES_INICIALES.cuotas),
    gracia: String(VALORES_INICIALES.gracia),
    fecha: fechaAInput(new Date()),
    seguro: coma(VALORES_INICIALES.seguro),
    gastos: coma(VALORES_INICIALES.gastos),
    notaria: miles(VALORES_INICIALES.notaria),
    holgura: miles(VALORES_INICIALES.holgura),
  };
}

function aCalculo(form) {
  return {
    deuda: soloDigitos(form.deuda),
    abono: soloDigitos(form.abono),
    pctCuotas: decimal(form.pctCuotas),
    tasa: decimal(form.tasa),
    cuotas: soloDigitos(form.cuotas),
    gracia: form.gracia,
    fecha: form.fecha,
    seguro: decimal(form.seguro),
    gastos: decimal(form.gastos),
    notaria: soloDigitos(form.notaria),
    holgura: soloDigitos(form.holgura),
  };
}

// Copia al portapapeles; en http (acceso por IP de red) el API moderno no existe y se usa el metodo clasico.
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

export default function SimuladorRenegociacionPage() {
  const [campanaCode, setCampanaCode] = useState("estandar");
  const [form, setForm] = useState(() => formInicial("estandar"));
  const [costosAbiertos, setCostosAbiertos] = useState(false);
  const [aviso, setAviso] = useState("");
  const [mostrarTabla, setMostrarTabla] = useState(false);
  const [fichaVisible, setFichaVisible] = useState(true);
  const deudaRef = useRef(null);
  const fichaRef = useRef(null);
  const tablaRef = useRef(null);
  const avisoTimer = useRef(null);

  const campana = CAMPANAS[campanaCode];
  const tieneCuoton = campanaCode === "apoya";
  const r = useMemo(() => simular(aCalculo(form)), [form]);
  // Sin deuda todavia no es un error: es el punto de partida.
  const sinDatos = soloDigitos(form.deuda) === "";
  const errores = sinDatos ? {} : r.erroresCampo;

  const deudaNum = Number(soloDigitos(form.deuda)) || 0;
  const abonoNum = Number(soloDigitos(form.abono)) || 0;
  const pct = Math.min(100, Math.max(0, decimal(form.pctCuotas)));
  const base = Math.max(0, deudaNum - abonoNum);
  const tasaAnual = (Math.pow(1 + decimal(form.tasa) / 100, 12) - 1) * 100;

  useEffect(() => {
    deudaRef.current?.focus();
  }, []);

  // En pantallas angostas, una barra fija muestra la cuota mientras la ficha no esta a la vista.
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

  // Al activar la tabla se baja hasta ella; apagada, la pagina cabe en una pantalla.
  useEffect(() => {
    if (mostrarTabla) {
      tablaRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [mostrarTabla]);

  function set(campo, valor) {
    setForm((prev) => ({ ...prev, [campo]: valor }));
  }

  function elegirCampana(code) {
    setCampanaCode(code);
    // Se conservan los datos del cliente; solo cambia el % a cuotas de la campana.
    setForm((prev) => ({ ...prev, pctCuotas: coma(CAMPANAS[code].pctCuotas) }));
  }

  function limpiar() {
    setForm(formInicial(campanaCode));
    setAviso("");
    deudaRef.current?.focus();
  }

  function flash(texto) {
    setAviso(texto);
    window.clearTimeout(avisoTimer.current);
    avisoTimer.current = window.setTimeout(() => setAviso(""), 2500);
  }

  async function copiarResumen() {
    if (!r.ok) {
      return;
    }
    try {
      await copiarTexto(resumenCliente(campana, r));
      flash("Copiado: pégalo en el chat o correo del cliente");
    } catch {
      flash("No se pudo copiar en este navegador");
    }
  }

  // Tabla de amortizacion: gracia (G), cuotas y, en Itau Apoya, el cuoton en su fecha.
  const filasTabla = useMemo(() => {
    if (!r.ok) {
      return [];
    }
    const filas = r.filas.map((f) => ({ ...f, tipo: f.gracia ? "gracia" : "cuota" }));
    if (tieneCuoton && r.cuoton > 0) {
      const pos = filas.findIndex((f) => f.fecha && f.fecha > r.fechaCuoton);
      filas.splice(pos === -1 ? filas.length : pos, 0, { id: "cuoton", tipo: "cuoton", fecha: r.fechaCuoton, cuota: r.cuoton });
    }
    return filas;
  }, [r, tieneCuoton]);

  const mensajeFicha = sinDatos ? "Ingresa el saldo de la deuda para calcular." : r.errores?.[0];
  const holguraNum = Number(soloDigitos(form.holgura)) || 0;

  return (
    <div className="pd-page sim-page">
      <PageHeader title="Simulador de Renegociaciones Itaú" breadcrumb={BREADCRUMB.slice(0, 1)} />

      <div className="sim-layout">
        <form className="pd-card sim-form sim-no-print" onSubmit={(e) => e.preventDefault()} noValidate autoComplete="off">
          <div className="sim-form-top">
            <div className="sim-campanas" role="radiogroup" aria-label="Campaña">
              {Object.values(CAMPANAS).map((c) => (
                <button
                  key={c.code}
                  type="button"
                  role="radio"
                  aria-checked={campanaCode === c.code}
                  title={c.detalle}
                  className={`sim-campana${campanaCode === c.code ? " is-active" : ""}`}
                  onClick={() => elegirCampana(c.code)}
                >
                  <i className={`bi ${c.icono}`} aria-hidden="true" />
                  <span className="sim-campana-titulo">{c.titulo}</span>
                  <span className="sim-campana-detalle">{c.code === "apoya" ? "75% + cuotón" : "100% cuotas"}</span>
                </button>
              ))}
            </div>
            <button type="button" className="pd-btn pd-btn-secondary pd-btn-sm sim-btn-limpiar" onClick={limpiar} title="Borra los datos ingresados y vuelve a los valores por defecto">
              <i className="bi bi-eraser" aria-hidden="true" /> Limpiar
            </button>
          </div>

          <Seccion numero="1" titulo="Deuda del cliente">
            <div className="sim-grid sim-grid-3">
              <Campo label="Saldo deuda" prefijo="$" error={errores.deuda}>
                <input ref={deudaRef} className="form-control" inputMode="numeric" placeholder="Ej: 10.000.000" value={form.deuda} onChange={(e) => set("deuda", miles(e.target.value))} />
              </Campo>
              <Campo label="Pie / abono" prefijo="$" error={errores.abono}>
                <input className="form-control" inputMode="numeric" placeholder="0" value={form.abono} onChange={(e) => set("abono", miles(e.target.value))} />
              </Campo>
              <Campo label={campana.pctBloqueado ? "% a cuotas (fijo)" : "% a cuotas"} sufijo="%" error={errores.pctCuotas}>
                <input className="form-control" inputMode="decimal" value={form.pctCuotas} disabled={campana.pctBloqueado} onChange={(e) => set("pctCuotas", limpiarDecimal(e.target.value))} />
              </Campo>
            </div>
            <div className="sim-reparto" aria-hidden="true">
              <span className="sim-reparto-cuotas" style={{ width: `${pct}%` }} />
              <span className="sim-reparto-resto" />
            </div>
            <div className="sim-reparto-montos">
              <span><span className="sim-dot sim-dot-cuotas" />A cuotas {coma(pct)}% <strong>{base > 0 ? pesos(base * pct / 100) : ""}</strong></span>
              {pct < 100 && <span><span className="sim-dot sim-dot-resto" />{tieneCuoton ? "Al cuotón" : "Pago único"} {coma(Math.round((100 - pct) * 100) / 100)}% <strong>{base > 0 ? pesos(base * (100 - pct) / 100) : ""}</strong></span>}
            </div>
          </Seccion>

          <Seccion numero="2" titulo="Plan de pago">
            <div className="sim-grid sim-grid-4">
              <Campo label="Tasa mensual" sufijo="%" error={errores.tasa} hint={decimal(form.tasa) > 0 ? `≈ ${coma(tasaAnual.toFixed(1))}% anual` : null}>
                <input className="form-control" inputMode="decimal" value={form.tasa} onChange={(e) => set("tasa", limpiarDecimal(e.target.value))} />
              </Campo>
              <Campo label="N° de cuotas" sufijo="cuotas" error={errores.cuotas}>
                <input className="form-control" inputMode="numeric" placeholder="Ej: 72" value={form.cuotas} onChange={(e) => set("cuotas", soloDigitos(e.target.value).slice(0, 3))} />
              </Campo>
              <Campo label="Meses de gracia" error={errores.gracia}>
                <select className="form-select sim-gracia-select" value={form.gracia} onChange={(e) => set("gracia", e.target.value)}>
                  {GRACIA_OPCIONES.map((g) => <option key={g} value={g}>{g === 0 ? "Sin gracia" : plural(g, "mes", "meses")}</option>)}
                </select>
              </Campo>
              <Campo label="Fecha de operación" error={errores.fecha}>
                <input className="form-control" type="date" value={form.fecha} onChange={(e) => set("fecha", e.target.value)} />
              </Campo>
            </div>
          </Seccion>

          <section className={`sim-seccion sim-costos${costosAbiertos ? " is-open" : ""}`}>
            <button type="button" className="sim-seccion-head sim-costos-toggle" aria-expanded={costosAbiertos} onClick={() => setCostosAbiertos((v) => !v)}>
              <span className="sim-num" aria-hidden="true">3</span>
              <span className="sim-seccion-titulo">Costos</span>
              <span className="sim-costos-resumen">
                Seguro {form.seguro || "0"}% · notaría ${form.notaria || "0"}
                {decimal(form.gastos) > 0 ? ` · cobranza ${form.gastos}%` : ""}
                {holguraNum > 0 ? ` · holgura $${form.holgura}` : ""}
              </span>
              <span className="sim-costos-accion">{costosAbiertos ? "Ocultar" : "Editar"} <i className={`bi ${costosAbiertos ? "bi-chevron-up" : "bi-chevron-down"}`} aria-hidden="true" /></span>
            </button>
            {costosAbiertos && (
              <div className="sim-grid sim-grid-4">
                <Campo label="Seguro" sufijo="%" error={errores.seguro}>
                  <input className="form-control" inputMode="decimal" value={form.seguro} onChange={(e) => set("seguro", limpiarDecimal(e.target.value))} />
                </Campo>
                <Campo label="Cobranza" sufijo="%" error={errores.gastos}>
                  <input className="form-control" inputMode="decimal" value={form.gastos} onChange={(e) => set("gastos", limpiarDecimal(e.target.value))} />
                </Campo>
                <Campo label="Notaría" prefijo="$" error={errores.notaria}>
                  <input className="form-control" inputMode="numeric" value={form.notaria} onChange={(e) => set("notaria", miles(e.target.value))} />
                </Campo>
                <Campo label="Holgura/cuota" prefijo="$" error={errores.holgura}>
                  <input className="form-control" inputMode="numeric" value={form.holgura} onChange={(e) => set("holgura", miles(e.target.value))} title="Monto extra para no quedar bajo la cuota real" />
                </Campo>
              </div>
            )}
          </section>

          <label className="sim-switch">
            <input type="checkbox" role="switch" checked={mostrarTabla} onChange={(e) => setMostrarTabla(e.target.checked)} />
            <span className="sim-switch-track" aria-hidden="true"><span /></span>
            <i className="bi bi-table" aria-hidden="true" />
            <span>Mostrar tabla de amortización</span>
            {r.ok && <span className="sim-switch-meta">{plural(r.cuotas, "cuota", "cuotas")}{r.gracia ? ` + ${r.gracia} de gracia` : ""}</span>}
          </label>
        </form>

        <aside className="sim-ficha" ref={fichaRef} aria-live="polite">
          <div className="sim-ficha-top">
            <div className="sim-ficha-fila">
              <span className="sim-ficha-label">Cuota mensual estimada</span>
              <span className="sim-ficha-etiqueta"><i className={`bi ${campana.icono}`} aria-hidden="true" /> {campana.titulo}</span>
            </div>
            <span className={`sim-ficha-cuota${r.ok ? "" : " is-empty"}`} key={r.ok ? r.cuota : "vacio"}>{r.ok ? pesos(r.cuota) : "$ —"}</span>
            <span className={`sim-ficha-sub${!r.ok && !sinDatos ? " is-error" : ""}`}>
              {r.ok ? `${plural(r.cuotas, "cuota", "cuotas")} · tasa ${coma(r.tasa)}% mensual` : mensajeFicha}
            </span>
          </div>

          {tieneCuoton && (
            <div className="sim-cuoton">
              <span>
                <span className="sim-ficha-label">Cuotón final · mes {MESES_CUOTON}</span>
                <span className="sim-cuoton-valor">{r.ok ? pesos(r.cuoton) : "$ —"}</span>
              </span>
              <span className="sim-cuoton-fecha">{r.ok ? fecha(r.fechaCuoton) : ""}</span>
            </div>
          )}

          <dl className="sim-ficha-datos">
            <div><dt>1ª cuota</dt><dd>{r.ok ? fecha(r.primeraCuota) : "—"}{r.ok && <small>en {r.diasPrimeraCuota} días</small>}</dd></div>
            <div><dt>Última cuota</dt><dd>{r.ok ? fecha(r.ultimaCuota) : "—"}</dd></div>
            <div><dt>Saldo a financiar</dt><dd>{r.ok ? pesos(r.saldoFinanciar) : "—"}</dd></div>
            <div><dt>Total en cuotas</dt><dd>{r.ok ? pesos(r.costoTotal) : "—"}</dd></div>
          </dl>

          <div className="sim-ficha-acciones sim-no-print">
            <button type="button" className="pd-btn pd-btn-primary sim-btn-copiar" onClick={copiarResumen} disabled={!r.ok}>
              <i className="bi bi-chat-square-text" aria-hidden="true" /> Copiar resumen para el cliente
            </button>
            <button type="button" className="pd-btn pd-btn-secondary" onClick={() => window.print()} disabled={!r.ok} title="Imprimir o guardar como PDF" aria-label="Imprimir o guardar como PDF">
              <i className="bi bi-printer" aria-hidden="true" />
            </button>
          </div>
          <span className={`pd-small sim-aviso sim-no-print${aviso ? " is-visible" : ""}`} role="status">{aviso}</span>

          <p className="sim-nota">Valores referenciales; no constituyen una oferta formal de crédito. La cuota final la confirma el banco.</p>
        </aside>
      </div>

      {mostrarTabla && (
        <div ref={tablaRef} className="sim-tabla-bloque">
          <SectionCard
            title="Tabla de amortización"
            description={tieneCuoton ? "Gracia (G) suma el interés al saldo; luego cuota fija. El cuotón final aparece en su fecha." : "Gracia (G) suma el interés al saldo; luego cuota fija hasta saldar."}
            bodyClassName="pd-table-scroll sim-tabla-wrap"
            exportName={r.ok ? `Amortizacion_${campana.titulo.replace(/\s+/g, "-")}_${fechaAInput(new Date())}` : undefined}
            actions={
              <button type="button" className="pd-btn pd-btn-ghost pd-btn-sm sim-no-print" onClick={() => { setMostrarTabla(false); window.scrollTo({ top: 0, behavior: "smooth" }); }}>
                <i className="bi bi-x-lg" aria-hidden="true" /> Ocultar
              </button>
            }
          >
            {r.ok ? (
              <table className="pd-table pd-table-compact sim-tabla">
                <thead>
                  <tr>
                    <th>N° cuota</th>
                    <th>Vencimiento</th>
                    <th className="text-end">Saldo inicial</th>
                    <th className="text-end" title="Sin holgura ni redondeo: la cuota informada al cliente es la de la ficha">Cuota banco</th>
                    <th className="text-end">Abono a capital</th>
                    <th className="text-end">Interés</th>
                    <th className="text-end">Saldo capital</th>
                  </tr>
                </thead>
                <tbody>
                  {filasTabla.map((f) => (
                    f.tipo === "cuoton" ? (
                      <tr key="cuoton" className="sim-fila-cuoton">
                        <td><i className="bi bi-flag-fill" aria-hidden="true" /> Cuotón</td>
                        <td>{fecha(f.fecha)}</td>
                        <td className="text-end">—</td>
                        <td className="text-end">{pesos(f.cuota)}</td>
                        <td colSpan={3} className="sim-fila-nota">Pago final de la parte no incluida en cuotas</td>
                      </tr>
                    ) : (
                      <tr key={f.id} className={f.tipo === "gracia" ? "sim-fila-gracia" : undefined}>
                        <td>{f.id}</td>
                        <td>{f.tipo === "gracia" ? "Gracia" : fecha(f.fecha)}</td>
                        <td className="text-end">{pesos(f.inicio)}</td>
                        <td className="text-end">{f.tipo === "gracia" ? "—" : pesos(f.cuota)}</td>
                        <td className="text-end">{f.tipo === "gracia" ? "—" : pesos(f.capital)}</td>
                        <td className="text-end">{pesos(f.interes)}</td>
                        <td className="text-end">{pesos(f.saldo)}</td>
                      </tr>
                    )
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="sim-vacio">
                <i className="bi bi-table" aria-hidden="true" />
                <span>{mensajeFicha}</span>
              </div>
            )}
          </SectionCard>
        </div>
      )}

      {r.ok && !fichaVisible && (
        <button type="button" className="sim-barra-movil sim-no-print" onClick={() => fichaRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })}>
          <span>
            <span className="sim-barra-label">Cuota estimada</span>
            <strong>{pesos(r.cuota)}</strong>
          </span>
          {tieneCuoton && r.cuoton > 0 && <span className="sim-barra-extra">+ cuotón {pesos(r.cuoton)}</span>}
          <i className="bi bi-chevron-up" aria-hidden="true" />
        </button>
      )}
    </div>
  );
}
