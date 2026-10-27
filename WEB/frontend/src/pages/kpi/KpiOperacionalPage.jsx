import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { fetchKpiOperacionalDashboard, fetchKpiOperacionalFilters } from "../../api";
import "./kpiOperacional.css";
import useDataVersion from "../../hooks/useDataVersion";

const MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];
const MONTHS_SHORT = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];

// Colores de los graficos (variables del CSS; paletas validadas para daltonismo y contraste).
const C = {
  actual: "var(--kpo-accent)",
  anterior: "var(--kpo-past)",
  directo: "var(--kpo-contact-1)",
  indirecto: "var(--kpo-contact-2)",
  sinContacto: "var(--kpo-contact-3)",
  cumplido: "var(--kpo-comp-ok)",
  pendiente: "var(--kpo-comp-wait)",
  incumplido: "var(--kpo-comp-bad)",
};

const FILTER_ORDER = ["mandante", "cartera", "tramo", "producto", "zona", "canal"];
// Cada filtro guarda los valores elegidos; vacio = todos.
const emptyFilters = { mandante: [], cartera: [], tramo: [], producto: [], zona: [], canal: [] };
// Con mas opciones que esto, el filtro deja elegir varias (salvo el mandante, que es de a uno).
const MAX_OPCIONES_SIMPLE = 2;
const emptyOptions = { mandantes: [], labels: {}, visibles: {}, carteras: [], tramos: [], productos: [], zonas: [], canales: [] };

// ------------------------------------------------------------
// Formato
// ------------------------------------------------------------
function nf(value, digits = 0) {
  return Number(value || 0).toLocaleString("es-CL", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

function fInt(value) {
  if (value === null || value === undefined) return "—";
  return nf(Math.round(Number(value)));
}

// Millones de pesos: sin decimales desde 1.000 MM, con uno bajo eso.
function fMM(value) {
  if (value === null || value === undefined) return "—";
  const mm = Number(value) / 1e6;
  return `$${nf(mm, Math.abs(mm) >= 1000 ? 0 : 1)} MM`;
}

function fPct(value) {
  if (value === null || value === undefined) return "—";
  return `${nf(value * 100, 1)}%`;
}

function fDec(value) {
  if (value === null || value === undefined) return "—";
  return nf(value, 1);
}

const FORMAT = { int: fInt, money: fMM, pct: fPct, dec: fDec };

// Etiquetas de las columnas chicas: montos en MM$ sin simbolo, para que quepan sin recortarse.
function fMMShort(value) {
  if (value === null || value === undefined) return "—";
  const mm = Number(value) / 1e6;
  return nf(mm, Math.abs(mm) >= 1000 ? 0 : 1);
}

const FORMAT_SHORT = { int: fInt, money: fMMShort, pct: fPct, dec: fDec };

function fDelta(delta, tipo) {
  if (delta === null || delta === undefined) return "—";
  const value = delta * 100;
  const sign = value >= 0.05 ? "+" : value <= -0.05 ? "−" : "";
  return `${sign}${nf(Math.abs(value), 1)}${tipo === "pp" ? " pp" : "%"}`;
}

function monthIdx(periodo) {
  return Number(periodo.split("-")[1]) - 1;
}

function monthShort(periodo) {
  return MONTHS_SHORT[monthIdx(periodo)];
}

function monthName(periodo) {
  return MONTHS[monthIdx(periodo)];
}

function cutLabel(iso) {
  if (!iso) return "";
  const [, month, day] = iso.split("-");
  return `${Number(day)} de ${MONTHS[Number(month) - 1]}`;
}

// ------------------------------------------------------------
// Lectura de la variacion: direccion y si es buena o mala
// ------------------------------------------------------------
// sentido: 1 = subir es mejor, -1 = bajar es mejor, 0 = ni bueno ni malo.
function trend(kpi, sentido) {
  const delta = kpi?.delta;
  if (delta === null || delta === undefined) return { dir: "none", calidad: "neutral" };
  const umbral = kpi.delta_tipo === "pp" ? 0.005 : 0.01; // bajo 0,5 pp o 1% se considera estable
  if (Math.abs(delta) < umbral) return { dir: "flat", calidad: "neutral" };
  const dir = delta > 0 ? "up" : "down";
  if (!sentido) return { dir, calidad: "neutral" };
  return { dir, calidad: delta * sentido > 0 ? "good" : "bad" };
}

const ARROW = { up: "▲", down: "▼", flat: "=", none: "" };

// Mes anterior al corte equivalente (mismos dias habiles para el cierre que hoy) o, si ya no quedan, su cierre.
function refLabel(mes) {
  if (!mes) return "el mes anterior";
  const nombre = monthName(mes.periodo);
  if (!mes.corte_equivalente || mes.corte_equivalente === mes.corte) return `el cierre de ${nombre}`;
  const n = mes.dias_habiles_restantes;
  const [, month, day] = mes.corte_equivalente.split("-");
  return `${nombre} a ${n} ${n === 1 ? "día hábil" : "días hábiles"} del cierre (${Number(day)}-${MONTHS_SHORT[Number(month) - 1].toLowerCase()})`;
}

function verdict(t, ref) {
  if (t.dir === "none") return "sin mes anterior para comparar";
  if (t.dir === "flat") return `igual que ${ref}`;
  if (t.calidad === "good") return `mejor que ${ref}`;
  if (t.calidad === "bad") return `peor que ${ref}`;
  return t.dir === "up" ? `más que ${ref}` : `menos que ${ref}`;
}

// ------------------------------------------------------------
// Componentes
// ------------------------------------------------------------
function Delta({ kpi, sentido, refText }) {
  const t = trend(kpi, sentido);
  return (
    <div className={`kpo-delta is-${t.calidad}`}>
      {t.dir !== "none" && (
        <span className="kpo-delta-chip">
          <span aria-hidden="true">{ARROW[t.dir]}</span> {fDelta(kpi.delta, kpi.delta_tipo)}
        </span>
      )}
      <span className="kpo-delta-text">{verdict(t, refText)}</span>
    </div>
  );
}

// Columnas de los 4 meses (del mas antiguo al actual); el mes actual en el color de acento.
// kpi2 (opcional): segunda serie en la misma escala, con una barra al lado de la principal en cada mes.
function MiniColumns({ kpi, meses, label, kpi2, label2 }) {
  const format = FORMAT[kpi?.tipo || "int"];
  const formatShort = FORMAT_SHORT[kpi?.tipo || "int"];
  const rows = meses
    .map((mes, i) => ({ ...mes, value: kpi?.valores[i], value2: kpi2?.valores[i], cierre: kpi?.valores_cierre?.[i] }))
    .reverse();
  const max = Math.max(0, ...rows.map((r) => Math.max(Number(r.value || 0), Number(r.value2 || 0))));
  if (max <= 0) return <div className="kpo-mini-empty">Sin datos para comparar</div>;
  const height = (value) => (value ? Math.max(3, Math.round((Number(value) / max) * 100)) : 0);
  const describe = (r) => `${monthName(r.periodo)} ${format(r.value)}${kpi2 ? ` (${label2}: ${format(r.value2)})` : ""}`;
  return (
    <>
      <div className={`kpo-mini${kpi2 ? " is-dual" : ""}`} role="img" aria-label={`${label}: ${rows.map(describe).join(", ")}`}>
        {rows.map((row, i) => {
          const current = i === rows.length - 1;
          const alCorte = !current && row.corte_equivalente && row.corte_equivalente !== row.corte;
          const cuando = current || alCorte ? `${monthName(row.periodo)} al ${cutLabel(alCorte ? row.corte_equivalente : row.corte)}` : `cierre de ${monthName(row.periodo)}`;
          const cierre = alCorte && row.cierre != null && row.cierre !== row.value ? ` · cierre: ${format(row.cierre)}` : "";
          return (
            <div key={row.periodo} className={`kpo-mini-col${current ? " is-current" : ""}`} title={`${label} · ${cuando}: ${format(row.value)}${kpi2 ? ` · ${label2}: ${format(row.value2)}` : ""}${cierre}`}>
              <span className="kpo-mini-value">{formatShort(row.value)}</span>
              {kpi2 && <span className="kpo-mini-value is-second">{formatShort(row.value2)}</span>}
              <div className="kpo-mini-track">
                <div className="kpo-mini-bar" style={{ height: `${height(row.value)}%`, background: current ? C.actual : C.anterior }} />
                {kpi2 && <div className="kpo-mini-bar is-second" style={{ height: `${height(row.value2)}%` }} />}
              </div>
              <span className="kpo-mini-month">{monthShort(row.periodo)}</span>
            </div>
          );
        })}
      </div>
      {kpi2 && (
        <div className="kpo-legend kpo-mini-legend">
          <span><span className="kpo-swatch" style={{ background: C.actual }} />{label}</span>
          <span><span className="kpo-swatch kpo-swatch-second" />{label2}</span>
        </div>
      )}
    </>
  );
}

// refText: contra que se compara (por defecto, el mes anterior al mismo dia habil).
function KpiCard({ label, help, kpi, meses, sentido = 1, note, kpi2, serie, serie2, refText }) {
  if (!kpi) return null;
  const format = FORMAT[kpi.tipo];
  const cierreAnterior = kpi.valores_cierre?.[1];
  // Al corte equivalente el mes anterior aun no cerraba: su cierre queda como referencia.
  const conCierre = meses[1] && meses[1].corte_equivalente !== meses[1].corte && cierreAnterior != null && cierreAnterior !== kpi.valores[1];
  return (
    <article className="kpo-card kpo-kpi">
      <header className="kpo-kpi-head">
        <h3 className="kpo-kpi-label">{label}</h3>
        <p className="kpo-kpi-help">{help}</p>
      </header>
      <div className="kpo-kpi-value">{format(kpi.valores[0])}</div>
      <Delta kpi={kpi} sentido={sentido} refText={refText || refLabel(meses[1])} />
      {conCierre && (
        <p className="kpo-kpi-note">
          Cierre de {monthName(meses[1].periodo)}: {format(cierreAnterior)} ({fDelta(kpi.delta_cierre, kpi.delta_tipo)} hoy vs cierre).
        </p>
      )}
      <MiniColumns kpi={kpi} meses={meses} label={serie || label} kpi2={kpi2} label2={serie2} />
      {kpi.tipo === "money" && <p className="kpo-kpi-note">Gráfico en millones de pesos (MM$).</p>}
      {note && <p className="kpo-kpi-note">{note}</p>}
    </article>
  );
}

// Barra 100% apilada por mes (del mas antiguo al actual), con leyenda y total.
function StackedMonths({ title, help, rows, series, totalLabel }) {
  return (
    <article className="kpo-card kpo-stacked">
      <header className="kpo-kpi-head">
        <h3 className="kpo-kpi-label">{title}</h3>
        <p className="kpo-kpi-help">{help}</p>
      </header>
      <div className="kpo-legend">
        {series.map((s) => (
          <span key={s.key}>
            <span className="kpo-swatch" style={{ background: s.color }} />
            {s.label}
          </span>
        ))}
      </div>
      <div className="kpo-stack-rows">
        {rows.map((row, i) => {
          const total = series.reduce((acc, s) => acc + (row[s.key] || 0), 0);
          const current = i === rows.length - 1;
          return (
            <div key={row.periodo} className={`kpo-stack-row${current ? " is-current" : ""}`}>
              <span className="kpo-stack-month">{monthShort(row.periodo)}</span>
              {total > 0 ? (
                <div className="kpo-stack" role="img" aria-label={`${title} ${monthName(row.periodo)}: ${series.map((s) => `${s.label} ${fInt(row[s.key])}`).join(", ")}`}>
                  {series.map((s) => {
                    const n = row[s.key] || 0;
                    if (!n) return null;
                    const share = n / total;
                    return (
                      <div
                        key={s.key}
                        className={`kpo-stack-seg${s.lightInk ? " is-light" : ""}`}
                        style={{ flexGrow: n, background: s.color }}
                        title={`${s.label}: ${fInt(n)} (${fPct(share)})`}
                      >
                        {share >= 0.14 && <span>{fPct(share)}</span>}
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="kpo-stack is-empty">Sin datos</div>
              )}
              <span className="kpo-stack-total">
                {fInt(total)}
                <small>{totalLabel}</small>
              </span>
            </div>
          );
        })}
      </div>
    </article>
  );
}

// Proyeccion de cierre: pagos a hoy + tubo de compromisos x cumplimiento en monto de los 3 meses cerrados.
function ProjectionCard({ proy, meses }) {
  if (!proy) return null;
  const prevMonth = meses[1] ? monthName(meses[1].periodo) : "el mes anterior";
  const tasaMeses = (proy.tasa_meses || []).slice().reverse().map((p) => monthShort(p).toLowerCase());
  const tasaLabel = tasaMeses.length > 1 ? `${tasaMeses[0]}–${tasaMeses[tasaMeses.length - 1]}` : tasaMeses[0] || "";
  const hoy = proy.pagos_hoy || 0;
  const aporte = proy.aporte_tubo || 0;
  const cierre = proy.cierre_anterior;
  const escala = Math.max(hoy + aporte, cierre || 0) * 1.08 || 1;
  const kpi = { tipo: "money", valores: [proy.proyeccion], delta: proy.delta_vs_cierre_anterior, delta_tipo: "pct" };

  return (
    <article className="kpo-card kpo-proj">
      <header className="kpo-kpi-head">
        <h3 className="kpo-kpi-label">Proyección de cierre de pagos</h3>
        <p className="kpo-kpi-help">
          Cuánto se espera cerrar a fin de mes si los compromisos pendientes se cumplen como en los últimos meses.
        </p>
      </header>

      {proy.proyeccion == null ? (
        <div className="kpo-mini-empty">Sin historial de compromisos para proyectar con estos filtros.</div>
      ) : (
        <>
          <div className="kpo-proj-top">
            <div className="kpo-kpi-value">{fMM(proy.proyeccion)}</div>
            <Delta kpi={kpi} sentido={1} refText={`el cierre de ${prevMonth}`} />
          </div>

          <div className="kpo-proj-bar-wrap" role="img" aria-label={`Pagos a hoy ${fMM(hoy)}, aporte esperado del tubo ${fMM(aporte)}${cierre ? `, cierre de ${prevMonth} ${fMM(cierre)}` : ""}`}>
            <div className="kpo-proj-bar">
              <div className="kpo-proj-seg is-hoy" style={{ width: `${(hoy / escala) * 100}%` }} title={`Pagos a hoy: ${fMM(hoy)}`} />
              {aporte > 0 && (
                <div className="kpo-proj-seg is-tubo" style={{ width: `${Math.max((aporte / escala) * 100, 0.6)}%` }} title={`Aporte esperado del tubo: ${fMM(aporte)}`} />
              )}
              {cierre > 0 && (
                <div className="kpo-proj-mark" style={{ left: `${(cierre / escala) * 100}%` }} title={`Cierre de ${prevMonth}: ${fMM(cierre)}`}>
                  <span>Cierre {monthShort(meses[1].periodo).toLowerCase()}</span>
                </div>
              )}
            </div>
            <div className="kpo-legend">
              <span><span className="kpo-swatch" style={{ background: "var(--kpo-accent)" }} />Pagos a hoy</span>
              <span><span className="kpo-swatch" style={{ background: "var(--kpo-past)" }} />Aporte esperado del tubo</span>
              {cierre > 0 && <span><span className="kpo-swatch kpo-swatch-line" />Cierre de {prevMonth}</span>}
            </div>
          </div>

          <dl className="kpo-proj-calc">
            <div>
              <dt>Pagos a hoy</dt>
              <dd>{fMM(hoy)}</dd>
            </div>
            <div>
              <dt>
                Tubo de compromisos
                <small>{fInt(proy.tubo_n)} pendientes que vencen hasta el {cutLabel(proy.fin_mes)}</small>
              </dt>
              <dd>{fMM(proy.tubo_monto)}</dd>
            </div>
            <div>
              <dt>
                × Cumplimiento en monto
                <small>promedio {tasaLabel}: de cada $100 comprometidos, cuánto se pagó</small>
              </dt>
              <dd>{fPct(proy.tasa)}</dd>
            </div>
            <div>
              <dt>= Aporte esperado del tubo</dt>
              <dd>+ {fMM(aporte)}</dd>
            </div>
            <div className="is-total">
              <dt>
                Proyección de cierre
                {proy.recuperacion_proyectada != null && <small>{fPct(proy.recuperacion_proyectada)} del saldo asignado</small>}
              </dt>
              <dd>{fMM(proy.proyeccion)}</dd>
            </div>
          </dl>
          <p className="kpo-kpi-note">
            En carteras de contención los pagos suman el saldo completo de la operación contenida, y el tubo suma el monto
            prometido; por eso el aporte del tubo suele verse chico al lado de los pagos.
          </p>
        </>
      )}
    </article>
  );
}

function Section({ num, title, desc, children }) {
  return (
    <section className="kpo-section" aria-labelledby={`kpo-sec-${num}`}>
      <div className="kpo-section-head">
        <span className="kpo-section-num" aria-hidden="true">{num}</span>
        <div>
          <h2 id={`kpo-sec-${num}`} className="kpo-section-title">{title}</h2>
          <p className="kpo-section-desc">{desc}</p>
        </div>
      </div>
      <div className="kpo-section-grid">{children}</div>
    </section>
  );
}

function Select({ id, label, value, options, allLabel, onChange, multiple = true }) {
  if (multiple && options.length > MAX_OPCIONES_SIMPLE) {
    return <MultiSelect id={id} label={label} value={value} options={options} allLabel={allLabel} onChange={onChange} />;
  }
  const actual = value[0] || "";
  return (
    <div className="kpo-field">
      <label htmlFor={id}>{label}</label>
      <select id={id} value={actual} onChange={(e) => onChange(e.target.value ? [e.target.value] : [])}>
        <option value="">{allLabel}</option>
        {options.map((option) => (
          <option key={option.valor} value={option.valor} disabled={!option.con_datos && option.valor !== actual}>
            {option.valor}{option.con_datos ? "" : " (sin datos)"}
          </option>
        ))}
      </select>
    </div>
  );
}

function MultiSelect({ id, label, value, options, allLabel, onChange }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    function closeOnOutside(event) {
      if (rootRef.current && !rootRef.current.contains(event.target)) setOpen(false);
    }
    function closeOnEscape(event) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", closeOnOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOnOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  function toggle(valor) {
    // Se conserva el orden de las opciones, no el de los clics.
    const next = value.includes(valor) ? value.filter((item) => item !== valor) : [...value, valor];
    onChange(options.map((option) => option.valor).filter((item) => next.includes(item)));
  }

  let summary = allLabel;
  if (value.length > 2) summary = `${value.length} seleccionados`;
  else if (value.length) summary = value.join(", ");

  return (
    <div className="kpo-field kpo-multi" ref={rootRef}>
      <label id={`${id}-label`} htmlFor={id}>{label}</label>
      <button
        type="button"
        id={id}
        className="kpo-multi-trigger"
        aria-haspopup="true"
        aria-expanded={open}
        aria-labelledby={`${id}-label ${id}`}
        onClick={() => setOpen((current) => !current)}
      >
        <span>{summary}</span>
        <span className="kpo-multi-chevron" aria-hidden="true">▾</span>
      </button>
      {open && (
        <div className="kpo-multi-panel" role="group" aria-labelledby={`${id}-label`}>
          <label className="kpo-multi-option kpo-multi-all">
            <input type="checkbox" checked={value.length === 0} onChange={() => onChange([])} />
            {allLabel}
          </label>
          {options.map((option) => {
            const checked = value.includes(option.valor);
            return (
              <label key={option.valor} className={`kpo-multi-option${option.con_datos || checked ? "" : " is-disabled"}`}>
                <input type="checkbox" checked={checked} disabled={!option.con_datos && !checked} onChange={() => toggle(option.valor)} />
                {option.valor}{option.con_datos ? "" : " (sin datos)"}
              </label>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------
// Pagina
// ------------------------------------------------------------
export default function KpiOperacionalPage() {
  const dataVersion = useDataVersion();
  const [filters, setFilters] = useState(emptyFilters);
  const [options, setOptions] = useState(emptyOptions);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Los filtros especificos dependen del mandante (y de la cartera elegida).
  useEffect(() => {
    let active = true;
    fetchKpiOperacionalFilters({ mandante: filters.mandante, cartera: filters.cartera, tramo: filters.tramo, producto: filters.producto })
      .then((res) => active && setOptions({ ...emptyOptions, ...res }))
      .catch((err) => active && setError(err.message));
    return () => {
      active = false;
    };
  }, [filters.mandante, filters.cartera, filters.tramo, filters.producto, dataVersion]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    fetchKpiOperacionalDashboard(filters)
      .then((res) => active && setData(res))
      .catch((err) => active && setError(err.message))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [filters, dataVersion]);

  function onFilter(field, value) {
    setFilters((prev) => {
      const next = { ...prev, [field]: value };
      // Al cambiar un filtro se limpian los que dependen de el.
      FILTER_ORDER.slice(FILTER_ORDER.indexOf(field) + 1).forEach((key) => {
        next[key] = [];
      });
      return next;
    });
  }

  const meses = data?.meses || [];
  const kpis = data?.kpis || {};
  const labels = options.labels || {};
  const visibles = options.visibles || {};
  const actual = meses[0]?.periodo;
  const anterior = meses[1]?.periodo;
  const prevMonth = anterior ? monthName(anterior) : "el mes anterior";
  const prevRef = refLabel(meses[1]);
  const restantes = data?.dias_habiles_restantes;
  // Los filtros especificos y el detalle por tramo solo aplican con un unico mandante elegido.
  const mandante = filters.mandante.length === 1 ? filters.mandante[0] : "";
  const tramoLabel = mandante ? labels.tramo || "Tramo" : "Mandante";
  const alcance = [
    filters.mandante.join(", ") || "Todos los mandantes",
    filters.cartera.join(", "),
    filters.producto.join(", "),
    filters.tramo.join(", "),
    filters.zona.length > 0 && `Zona ${filters.zona.join(", ")}`,
    filters.canal.length > 0 && `Canal ${filters.canal.join(", ")}`,
  ]
    .filter(Boolean)
    .join(" · ");

  const segmentos = data?.segmentos || [];
  const sinDatos = meses.filter((m) => !m.con_datos);
  const sinHistoria = meses.filter((m) => m.con_datos && m.meses_historia < 3);
  // Sin mandante: mandantes sin datos este mes pero si en los anteriores (el total no es comparable).
  const mandantesSinMes = !mandante
    ? segmentos.filter((s) => !s.meses[actual] && meses.slice(1).some((m) => s.meses[m.periodo])).map((s) => s.mandante)
    : [];

  // Resumen en palabras de los indicadores que mejor cuentan como va el mes.
  const resumen = useMemo(() => {
    const items = [
      { key: "pagos", nombre: "Pagos recuperados", sentido: 1 },
      { key: "recuperacion", nombre: "Recuperación", sentido: 1 },
      { key: "contactabilidad", nombre: "Contactabilidad", sentido: 1 },
      // Alcance: los meses anteriores van completos (sin corte equivalente).
      { key: "avance_alcance", nombre: "Alcance de contacto", sentido: 1, ref: `el cierre de ${prevMonth}` },
      { key: "cobertura", nombre: "Cobertura de gestión", sentido: 1 },
      { key: "pct_cumplidos", nombre: "Compromisos cumplidos", sentido: 1 },
    ];
    const out = items
      .filter((it) => kpis[it.key])
      .map((it) => ({ ...it, kpi: kpis[it.key], t: trend(kpis[it.key], it.sentido) }));
    const proy = data?.proyeccion;
    if (proy?.proyeccion != null) {
      const kpi = { tipo: "money", valores: [proy.proyeccion], delta: proy.delta_vs_cierre_anterior, delta_tipo: "pct" };
      out.splice(1, 0, { key: "proyeccion", nombre: "Proyección de cierre", sentido: 1, kpi, t: trend(kpi, 1), ref: `el cierre de ${prevMonth}` });
    }
    return out;
  }, [kpis, data, prevMonth]);

  const tipos = useMemo(
    () =>
      (data?.tipos_contacto || [])
        .map((t) => ({ periodo: t.periodo, directo: t.directo, indirecto: t.indirecto, sin_contacto: t.sin_contacto }))
        .reverse(),
    [data],
  );

  const compRows = useMemo(
    () =>
      meses
        .map((mes, i) => ({
          periodo: mes.periodo,
          cumplidos: kpis.cumplidos?.valores[i],
          incumplidos: kpis.incumplidos?.valores[i],
          pendientes: kpis.pendientes?.valores[i],
        }))
        .reverse(),
    [meses, kpis],
  );

  return (
    <div className="kpo">
      <header className="kpo-header">
        <div>
          <div className="kpo-eyebrow">
            <Link to="/kpi">Panel KPI</Link> · Seguimiento operacional
          </div>
          <h1 className="kpo-title">KPI Operacional</h1>
          <p className="kpo-subtitle">
            Cómo va el mes <strong>hoy</strong>, comparado con los 3 meses anteriores <strong>al mismo día hábil</strong> antes
            del cierre{restantes != null && ` (quedan ${restantes} ${restantes === 1 ? "día hábil" : "días hábiles"})`}.
          </p>
        </div>
      </header>

      <section className="kpo-filters" aria-label="Filtros">
        <Select id="kpo-mandante" label="Mandante" value={filters.mandante} options={options.mandantes} allLabel="Todos" multiple={false} onChange={(v) => onFilter("mandante", v)} />
        {visibles.cartera && (
          <Select id="kpo-cartera" label={labels.cartera} value={filters.cartera} options={options.carteras} allLabel="Todas" onChange={(v) => onFilter("cartera", v)} />
        )}
        {visibles.tramo && (
          <Select id="kpo-tramo" label={labels.tramo} value={filters.tramo} options={options.tramos} allLabel="Todos" onChange={(v) => onFilter("tramo", v)} />
        )}
        {visibles.producto && (
          <Select id="kpo-producto" label={labels.producto} value={filters.producto} options={options.productos} allLabel="Todos" onChange={(v) => onFilter("producto", v)} />
        )}
        {visibles.zona && (
          <Select id="kpo-zona" label={labels.zona} value={filters.zona} options={options.zonas} allLabel="Todas" onChange={(v) => onFilter("zona", v)} />
        )}
        {visibles.canal && (
          <Select id="kpo-canal" label={labels.canal} value={filters.canal} options={options.canales} allLabel="Todos" onChange={(v) => onFilter("canal", v)} />
        )}
        <button type="button" className="kpo-btn" onClick={() => setFilters(emptyFilters)}>
          Limpiar filtros
        </button>
        {/* Al cambiar un filtro se siguen viendo los datos anteriores hasta que llega la respuesta. */}
        {loading && data && (
          <span className="kpo-updating" role="status">
            <span className="kpo-updating-dot" aria-hidden="true" />
            Actualizando…
          </span>
        )}
      </section>

      {error && <div className="kpo-error">{error}</div>}

      {!data || data.vacio ? (
        <div className="kpo-empty">
          {loading ? "Cargando KPI Operacional..." : "No hay datos cargados para estos filtros."}
        </div>
      ) : (
        <div className={`kpo-body${loading ? " kpo-is-loading" : ""}`}>
          {data.mes_anterior && (
            <div className="kpo-banner" role="status">
              <strong>Estás viendo {monthName(actual)}, no {monthName(data.periodo_en_curso)}.</strong> Aún no hay asignación
              cargada de {monthName(data.periodo_en_curso)} para estos filtros, así que se muestra el cierre del mes anterior
              comparado con los 3 meses previos.
            </div>
          )}
          {/* Resumen en palabras */}
          <section className="kpo-card kpo-summary" aria-label="Resumen del mes">
            <div className="kpo-summary-head">
              <h2 className="kpo-summary-title">Resumen de {monthName(actual)}</h2>
              <span className="kpo-summary-scope">{alcance}</span>
            </div>
            <ul className="kpo-summary-list">
              {resumen.map((it) => (
                <li key={it.key} className={`is-${it.t.calidad}`}>
                  <span className="kpo-summary-icon" aria-hidden="true">{ARROW[it.t.dir] || "·"}</span>
                  <span className="kpo-summary-name">{it.nombre}</span>
                  <span className="kpo-summary-value">{FORMAT[it.kpi.tipo](it.kpi.valores[0])}</span>
                  <span className="kpo-summary-verdict">
                    {it.t.dir === "none" ? "sin comparación" : `${fDelta(it.kpi.delta, it.kpi.delta_tipo)} · ${verdict(it.t, it.ref || prevRef)}`}
                  </span>
                </li>
              ))}
            </ul>
            {(sinDatos.length > 0 || mandantesSinMes.length > 0 || sinHistoria.length > 0) && (
              <div className="kpo-note" role="note">
                <strong>Ojo al comparar:</strong>{" "}
                {sinDatos.length > 0 && <span>no hay asignación cargada en {sinDatos.map((m) => monthName(m.periodo)).join(", ")}. </span>}
                {mandantesSinMes.length > 0 && (
                  <span>{mandantesSinMes.join(", ")} no tiene datos en {monthName(actual)}, así que el total no es comparable. </span>
                )}
                {sinHistoria.length > 0 && (
                  <span>el alcance de contacto de {sinHistoria.map((m) => monthName(m.periodo)).join(", ")} usa menos de 3 meses de historia. </span>
                )}
              </div>
            )}
          </section>

          <Section num="1" title="Cartera asignada" desc="Cuántos clientes y cuánta deuda nos entregaron para gestionar en el mes.">
            <KpiCard
              label="Casos asignados"
              help="Clientes (RUT únicos) asignados y total de operaciones."
              kpi={kpis.casos}
              meses={meses}
              sentido={0}
              kpi2={kpis.operaciones}
              serie="RUT únicos"
              serie2="Operaciones"
            />
            <KpiCard label="Saldo asignado" help="Deuda total asignada, en millones de pesos." kpi={kpis.saldo} meses={meses} sentido={0} />
          </Section>

          <Section num="2" title="Gestión y contacto" desc="A cuántos clientes llegamos y con cuántos hablamos directamente.">
            <KpiCard label="Cobertura de gestión" help="De cada 100 clientes asignados, cuántos tuvieron al menos una gestión." kpi={kpis.cobertura} meses={meses} />
            <KpiCard
              label="% sin gestión"
              help="De cada 100 clientes asignados, cuántos no tuvieron ninguna gestión en el mes."
              kpi={kpis.sin_gestion}
              meses={meses}
              sentido={-1}
              note={kpis.no_gestionados?.valores[0] != null ? `${fInt(kpis.no_gestionados.valores[0])} clientes sin gestión.` : ""}
            />
            <KpiCard label="Contactabilidad" help="De cada 100 clientes gestionados, con cuántos hablamos directamente (titular)." kpi={kpis.contactabilidad} meses={meses} />
            <KpiCard
              label="Alcance de contacto"
              help="De los clientes asignados con los que hablamos con el titular en los últimos 3 meses, cuántos ya contactamos directamente este mes. Meses anteriores completos, hasta el cierre."
              kpi={kpis.avance_alcance}
              meses={meses}
              refText={`el cierre de ${prevMonth}`}
              note={
                kpis.contactables?.valores[0]
                  ? `Te falta contactar el ${fPct(kpis.contactables_pendientes.valores[0] / kpis.contactables.valores[0])} (${fInt(kpis.contactables_pendientes.valores[0])} de ${fInt(kpis.contactables.valores[0])}) de los RUT asignados que tuvieron gestión titular los últimos 3 meses.`
                  : ""
              }
            />
            <KpiCard
              label="Por contactar (con histórico)"
              help="Clientes asignados con contacto titular en los últimos 3 meses que aún no contactamos directamente este mes. Meses anteriores completos, hasta el cierre."
              kpi={kpis.contactables_pendientes}
              meses={meses}
              sentido={-1}
              refText={`el cierre de ${prevMonth}`}
              note={
                kpis.contactables?.valores[0] != null
                  ? `${fInt(kpis.contactables.valores[0])} asignados (${fPct(kpis.alcance_contacto.valores[0])}) tuvieron contacto titular en los últimos 3 meses.`
                  : ""
              }
            />
            <KpiCard label="Intensidad de gestión" help="Promedio de gestiones por cliente" kpi={kpis.intensidad} meses={meses} />
            <StackedMonths
              title="Tipos de contacto"
              help="Mejor contacto logrado con cada cliente gestionado."
              rows={tipos}
              totalLabel="gestionados"
              series={[
                { key: "directo", label: "Directo (titular)", color: C.directo },
                { key: "indirecto", label: "Indirecto (tercero)", color: C.indirecto },
                { key: "sin_contacto", label: "Sin contacto", color: C.sinContacto, lightInk: true },
              ]}
            />
          </Section>

          <Section num="3" title="Recuperación" desc="Cuánto pagaron los clientes y qué parte de la deuda asignada representa.">
            <KpiCard label="Pagos recuperados" help="Monto pagado o contenido por los clientes asignados." kpi={kpis.pagos} meses={meses} />
            <KpiCard label="% de recuperación" help="Pagos recuperados divididos por el saldo asignado." kpi={kpis.recuperacion} meses={meses} />
            <ProjectionCard proy={data.proyeccion} meses={meses} />
          </Section>

          <Section num="4" title="Compromisos de pago" desc="Promesas de pago que hicieron los clientes y si las cumplieron.">
            <KpiCard
              label="Compromisos generados"
              help="Promesas de pago registradas hasta hoy."
              kpi={kpis.compromisos}
              meses={meses}
              note={`${fInt(kpis.pendientes?.valores[0])} aún no vencen.`}
            />
            <KpiCard
              label="Monto comprometido"
              help="Suma de lo que los clientes prometieron pagar."
              kpi={kpis.monto_comprometido}
              meses={meses}
            />
            <KpiCard label="% cumplidos" help="De los compromisos generados, cuántos se pagaron." kpi={kpis.pct_cumplidos} meses={meses} />
            <KpiCard
              label="% incumplidos"
              help="De los compromisos generados, cuántos vencieron sin pago."
              kpi={kpis.pct_incumplidos}
              meses={meses}
              sentido={-1}
            />
            <StackedMonths
              title="Estado de los compromisos"
              help="Cumplido: el cliente pagó. Incumplido: venció sin pago. Pendiente: aún no vence."
              rows={compRows}
              totalLabel="compromisos"
              series={[
                { key: "cumplidos", label: "Cumplidos", color: C.cumplido },
                { key: "pendientes", label: "Pendientes (aún no vencen)", color: C.pendiente, lightInk: true },
                { key: "incumplidos", label: "Incumplidos", color: C.incumplido },
              ]}
            />
          </Section>

          <section className="kpo-card kpo-detail" aria-labelledby="kpo-detail-title">
            <div className="kpo-detail-head">
              <div>
                <h2 id="kpo-detail-title" className="kpo-section-title">Detalle por {tramoLabel.toLowerCase()}</h2>
                <p className="kpo-section-desc">
                  {monthName(actual) && `${monthName(actual)[0].toUpperCase()}${monthName(actual).slice(1)} al ${cutLabel(meses[0]?.corte)}`}, comparado con {prevRef}.
                </p>
              </div>
            </div>
            {segmentos.length ? (
              <div className="kpo-table-wrap">
                <table className="kpo-table">
                  <thead>
                    <tr>
                      <th>{tramoLabel}</th>
                      <th>Casos</th>
                      <th>Saldo asignado</th>
                      <th>Pagos</th>
                      <th>Pagos vs {monthShort(anterior || actual).toLowerCase()}</th>
                      <th>% recuperación</th>
                      <th>Recup. vs {monthShort(anterior || actual).toLowerCase()}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {segmentos.map((s) => {
                      const cur = s.meses[actual] || {};
                      const prev = s.meses[anterior] || {};
                      const dPagos = { delta: prev.pagos ? (cur.pagos || 0) / prev.pagos - 1 : null, delta_tipo: "pct" };
                      const dRecup = {
                        delta: cur.recuperacion != null && prev.recuperacion != null ? cur.recuperacion - prev.recuperacion : null,
                        delta_tipo: "pp",
                      };
                      const tP = trend(dPagos, 1);
                      const tR = trend(dRecup, 1);
                      const name = mandante ? s.tramo || s.cartera : s.mandante;
                      const detail = mandante && filters.cartera.length !== 1 && s.tramo !== s.cartera ? s.cartera : "";
                      return (
                        <tr key={`${s.mandante}|${s.cartera}|${s.tramo}`}>
                          <td>
                            <strong>{name}</strong>
                            {detail && <span className="kpo-table-sub">{detail}</span>}
                          </td>
                          <td>{fInt(cur.casos)}</td>
                          <td>{fMM(cur.saldo)}</td>
                          <td>{fMM(cur.pagos)}</td>
                          <td className={`is-${tP.calidad}`} title={prev.pagos_cierre != null ? `Cierre de ${prevMonth}: ${fMM(prev.pagos_cierre)}` : undefined}>
                            {tP.dir !== "none" && <span aria-hidden="true">{ARROW[tP.dir]} </span>}
                            {fDelta(dPagos.delta, "pct")}
                          </td>
                          <td>{fPct(cur.recuperacion)}</td>
                          <td className={`is-${tR.calidad}`} title={prev.recuperacion_cierre != null ? `Cierre de ${prevMonth}: ${fPct(prev.recuperacion_cierre)}` : undefined}>
                            {tR.dir !== "none" && <span aria-hidden="true">{ARROW[tR.dir]} </span>}
                            {fDelta(dRecup.delta, "pp")}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="kpo-empty">Sin asignación para los filtros seleccionados.</div>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
