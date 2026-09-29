import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { fetchKpiOperacionalDashboard, fetchKpiOperacionalFilters } from "../api";
import "./kpiOperacional.css";

const MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];
const MONTHS_SHORT = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];

const COLORS = {
  navy: "#1F4E79",
  navySoft: "#8FB0D0",
  navyMid: "#6F9BC7",
  orange: "#D9822B",
  green: "#2F6F63",
  greenSoft: "#9CC3B9",
  red: "#C2410C",
  neutral: "#CFC8BA",
};

const emptyFilters = { periodo: "", mandante: "", cartera: "", tramo: "", producto: "" };

// ------------------------------------------------------------
// Formato
// ------------------------------------------------------------
function nf(value, digits = 0) {
  return Number(value || 0).toLocaleString("es-CL", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

function fInt(value) {
  return nf(Math.round(Number(value || 0)));
}

// Millones de pesos: sin decimales desde 1.000 MM, con uno bajo eso.
function fMM(value) {
  const mm = Number(value || 0) / 1e6;
  return nf(mm, Math.abs(mm) >= 1000 ? 0 : 1);
}

function fPct(value) {
  if (value === null || value === undefined) return "—";
  return `${nf(value * 100, 1)}%`;
}

function periodLabel(periodo) {
  if (!periodo) return "";
  const [year, month] = periodo.split("-");
  return `${MONTHS[Number(month) - 1] || month} ${year}`;
}

function periodShort(periodo) {
  const [year, month] = periodo.split("-");
  return `${MONTHS_SHORT[Number(month) - 1] || month} ${year.slice(2)}`;
}

function formatDate(iso) {
  if (!iso) return "";
  const [year, month, day] = iso.split("-");
  return `${day}-${month}-${year}`;
}

function pct(value, max, scale = 85) {
  return max > 0 ? Math.round((Number(value || 0) / max) * scale) : 0;
}

// ------------------------------------------------------------
// Componentes
// ------------------------------------------------------------
function Kpi({ label, value, caption }) {
  return (
    <div className="kpo-kpi">
      <div className="kpo-kpi-label">{label}</div>
      <div className="kpo-kpi-value kpo-mono">{value}</div>
      <div className="kpo-kpi-caption">{caption}</div>
    </div>
  );
}

function Select({ id, label, value, options, allLabel, onChange }) {
  return (
    <div className="kpo-field">
      <label htmlFor={id}>{label}</label>
      <select id={id} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">{allLabel}</option>
        {options.map((option) => (
          <option key={option} value={option}>{option}</option>
        ))}
      </select>
    </div>
  );
}

// Barras verticales por mes; el mes seleccionado va en el tono fuerte.
function MonthlyColumns({ rows, valueKey, format, color, softColor, periodo, title }) {
  const max = Math.max(0, ...rows.map((row) => Number(row[valueKey] || 0)));
  if (!rows.length || max <= 0) {
    return <div className="kpo-empty">Sin datos para los filtros seleccionados.</div>;
  }
  return (
    <>
      <div className="kpo-cols" role="img" aria-label={title}>
        {rows.map((row) => (
          <div key={row.periodo} className="kpo-col" title={`${periodLabel(row.periodo)}: ${format(row[valueKey])}`}>
            <span className="kpo-mono">{format(row[valueKey])}</span>
            <div
              className="kpo-col-bar"
              style={{ height: `${pct(row[valueKey], max)}%`, background: row.periodo === periodo ? color : softColor }}
            />
          </div>
        ))}
      </div>
      <div className="kpo-col-labels">
        {rows.map((row) => (
          <div key={row.periodo} className={row.periodo === periodo ? "is-current" : ""}>{periodShort(row.periodo)}</div>
        ))}
      </div>
    </>
  );
}

export default function KpiOperacionalPage() {
  const [filters, setFilters] = useState(emptyFilters);
  const [options, setOptions] = useState({ periodos: [], mandantes: [], carteras: [], tramos: [], productos: [] });
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Opciones en cascada: cada filtro solo ofrece lo disponible en el periodo y los filtros superiores.
  useEffect(() => {
    let active = true;
    fetchKpiOperacionalFilters({ periodo: filters.periodo, mandante: filters.mandante, cartera: filters.cartera, tramo: filters.tramo })
      .then((res) => {
        if (!active) return;
        setOptions(res);
        if (!filters.periodo && res.periodo) {
          setFilters((prev) => ({ ...prev, periodo: res.periodo }));
        }
      })
      .catch((err) => active && setError(err.message));
    return () => {
      active = false;
    };
  }, [filters.periodo, filters.mandante, filters.cartera, filters.tramo]);

  useEffect(() => {
    if (!filters.periodo) return undefined;
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
  }, [filters]);

  function onFilter(field, value) {
    const order = ["periodo", "mandante", "cartera", "tramo", "producto"];
    setFilters((prev) => {
      const next = { ...prev, [field]: value };
      // Al cambiar un filtro se limpian los que dependen de el.
      order.slice(order.indexOf(field) + 1).forEach((key) => {
        next[key] = "";
      });
      return next;
    });
  }

  const resumen = data?.resumen;
  const mensual = data?.evolucion_mensual || [];
  const comp = data?.compromisos;

  // Con una cartera elegida se desglosa por tramo; si no, por mandante y cartera (RUT unico por cartera).
  const pairRows = useMemo(() => {
    if (!data) return [];
    if (filters.cartera) {
      return (data.tramos || [])
        .filter((row) => row.casos || row.saldo)
        .map((row) => ({
          key: `${row.mandante}|${row.cartera}|${row.tramo}`,
          name: row.tramo,
          detail: `${row.mandante} · ${row.cartera}`,
          casos: row.casos,
          saldo: row.saldo,
        }));
    }
    return (data.carteras || []).map((row) => ({
      key: `${row.mandante}|${row.cartera}`,
      name: row.cartera,
      detail: row.mandante,
      casos: row.casos,
      saldo: row.saldo,
    }));
  }, [data, filters.cartera]);
  const maxCasos = Math.max(0, ...pairRows.map((row) => row.casos));
  const maxSaldo = Math.max(0, ...pairRows.map((row) => row.saldo));

  // Tipos de contacto sobre los casos asignados: sin contacto incluye a los no gestionados.
  const tipos = useMemo(() => {
    if (!resumen) return [];
    const casos = resumen.casos || 0;
    const directo = resumen.contacto_directo || 0;
    const indirecto = data.tipos_contacto.find((t) => t.tipo === "INDIRECTO")?.ruts || 0;
    const sin = Math.max(casos - directo - indirecto, 0);
    return [
      { name: "Contacto directo", n: directo, color: COLORS.navy },
      { name: "Contacto indirecto", n: indirecto, color: COLORS.navyMid },
      { name: "Sin contacto", n: sin, color: COLORS.neutral },
    ].map((t) => ({ ...t, share: casos ? t.n / casos : 0 }));
  }, [data, resumen]);

  const maxComp = Math.max(0, ...mensual.map((row) => Math.max(row.cumplidos || 0, row.incumplidos || 0)));

  return (
    <div className="kpo">
      <header className="kpo-header">
        <div>
          <div className="kpo-eyebrow">
            <Link to="/kpi">Panel KPI</Link> · Seguimiento operacional
          </div>
          <h1 className="kpo-title">KPI Operacional</h1>
        </div>
        <div className="kpo-header-right">
          <label htmlFor="kpo-periodo">Período:</label>
          <select id="kpo-periodo" value={filters.periodo} onChange={(e) => onFilter("periodo", e.target.value)}>
            {options.periodos.map((p) => (
              <option key={p} value={p}>{periodLabel(p)}</option>
            ))}
          </select>
          {data?.fecha_corte && <span className="kpo-badge">Corte {formatDate(data.fecha_corte)}</span>}
        </div>
      </header>

      <section className="kpo-filters" aria-label="Filtros">
        <Select id="kpo-mandante" label="Mandante" value={filters.mandante} options={options.mandantes} allLabel="Todos" onChange={(v) => onFilter("mandante", v)} />
        <Select id="kpo-cartera" label="Cartera" value={filters.cartera} options={options.carteras} allLabel="Todas" onChange={(v) => onFilter("cartera", v)} />
        <Select id="kpo-tramo" label="Tramo mora" value={filters.tramo} options={options.tramos} allLabel="Todos" onChange={(v) => onFilter("tramo", v)} />
        <Select id="kpo-producto" label="Producto" value={filters.producto} options={options.productos} allLabel="Todos" onChange={(v) => onFilter("producto", v)} />
        <button type="button" className="kpo-btn" onClick={() => setFilters({ ...emptyFilters, periodo: filters.periodo })}>
          Limpiar filtros
        </button>
      </section>

      {error && <div className="kpo-error">{error}</div>}

      {!resumen ? (
        <div className="kpo-empty">{loading ? "Cargando KPI Operacional..." : "No hay datos cargados. Ejecuta dbo.sp_kpi_operacional_cargar."}</div>
      ) : (
        <div className={loading ? "kpo-is-loading" : ""} style={{ display: "flex", flexDirection: "column", gap: 24 }}>
          <div className="kpo-kpis">
            <Kpi label="Asignación" value={fInt(resumen.casos)} caption={`casos asignados · ${fInt(resumen.operaciones)} operaciones`} />
            <Kpi label="Saldo asignado" value={fMM(resumen.saldo_asignado)} caption="MM$ asignados" />
            <Kpi label="Contactabilidad" value={fPct(resumen.contacto_sobre_asignacion)} caption="% contacto directo sobre asignación" />
            <Kpi label="Pagos" value={fMM(resumen.pagos)} caption={`MM$ recuperados · ${fPct(resumen.recuperacion)} del saldo`} />
          </div>

          <div className="kpo-grid-2">
            <section className="kpo-card" style={{ gap: 20 }}>
              <div className="kpo-card-head">
                <h2 className="kpo-card-title">Asignación y saldo por {filters.cartera ? "tramo" : "cartera"}</h2>
                <div className="kpo-legend">
                  <span><span className="kpo-swatch" style={{ background: COLORS.navy }} />Casos</span>
                  <span><span className="kpo-swatch" style={{ background: COLORS.orange }} />Saldo MM$</span>
                </div>
              </div>
              {pairRows.length ? (
                <div className="kpo-pair-list">
                  {pairRows.map((row) => (
                    <div key={row.key} className="kpo-pair-row">
                      <div className="kpo-pair-name">
                        <strong>{row.name}</strong>
                        <span>{row.detail}</span>
                      </div>
                      <div className="kpo-pair-bars">
                        <div className="kpo-pair-bar" title={`${row.name}: ${fInt(row.casos)} casos`}>
                          <div style={{ width: `${pct(row.casos, maxCasos, 70)}%`, background: COLORS.navy }} />
                          <span className="kpo-mono">{fInt(row.casos)} casos</span>
                        </div>
                        <div className="kpo-pair-bar" title={`${row.name}: ${fMM(row.saldo)} MM$`}>
                          <div style={{ width: `${pct(row.saldo, maxSaldo, 70)}%`, background: COLORS.orange }} />
                          <span className="kpo-mono">{fMM(row.saldo)} MM$</span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="kpo-empty">Sin asignación para los filtros seleccionados.</div>
              )}
            </section>

            <section className="kpo-card">
              <div className="kpo-card-head">
                <h2 className="kpo-card-title">Pagos mensuales</h2>
                <span className="kpo-card-meta">MM$ recuperados</span>
              </div>
              <MonthlyColumns
                rows={mensual}
                valueKey="pagos"
                format={fMM}
                color={COLORS.navy}
                softColor={COLORS.navySoft}
                periodo={data.periodo}
                title="Pagos mensuales en millones de pesos"
              />
            </section>
          </div>

          <div className="kpo-grid-2">
            <section className="kpo-card">
              <div className="kpo-card-head">
                <h2 className="kpo-card-title">Contactabilidad mensual</h2>
                <span className="kpo-card-meta">% contacto directo</span>
              </div>
              <MonthlyColumns
                rows={mensual}
                valueKey="contactabilidad_asignacion"
                format={fPct}
                color={COLORS.green}
                softColor={COLORS.greenSoft}
                periodo={data.periodo}
                title="Contactabilidad mensual"
              />
            </section>

            <section className="kpo-card" style={{ gap: 20 }}>
              <div className="kpo-card-head">
                <h2 className="kpo-card-title">Tipos de contacto</h2>
                <span className="kpo-card-meta">casos del mes · {fInt(resumen.casos)} asignados</span>
              </div>
              <div className="kpo-stack" role="img" aria-label="Distribución de tipos de contacto">
                {tipos.filter((t) => t.n > 0).map((t) => (
                  <div key={t.name} style={{ width: `${t.share * 100}%`, background: t.color }} title={`${t.name}: ${fPct(t.share)}`} />
                ))}
              </div>
              <div>
                {tipos.map((t) => (
                  <div key={t.name} className="kpo-type-row">
                    <span className="kpo-type-name"><span className="kpo-swatch" style={{ width: 12, height: 12, borderRadius: 3, background: t.color }} />{t.name}</span>
                    <span className="kpo-type-n kpo-mono">{fInt(t.n)} casos</span>
                    <span className="kpo-type-pct kpo-mono">{fPct(t.share)}</span>
                  </div>
                ))}
              </div>
            </section>
          </div>

          <section className="kpo-card kpo-comp">
            <div className="kpo-comp-tiles">
              <h2 className="kpo-card-title" style={{ marginBottom: 4 }}>Compromisos de pago</h2>
              <div className="kpo-comp-tile">
                <div className="kpo-comp-tile-text">
                  <span className="kpo-comp-tile-label">Compromisos totales</span>
                  <span className="kpo-comp-tile-caption">{fInt(comp.pendientes)} vigentes</span>
                </div>
                <span className="kpo-comp-tile-value kpo-mono">{fInt(comp.total)}</span>
              </div>
              <div className="kpo-comp-tile">
                <div className="kpo-comp-tile-text">
                  <span className="kpo-comp-tile-label"><span className="kpo-swatch" style={{ background: COLORS.navy }} />Cumplidos</span>
                  <span className="kpo-comp-tile-caption">{fPct(comp.total ? comp.cumplidos / comp.total : null)} del total</span>
                </div>
                <span className="kpo-comp-tile-value kpo-mono" style={{ color: COLORS.navy }}>{fInt(comp.cumplidos)}</span>
              </div>
              <div className="kpo-comp-tile">
                <div className="kpo-comp-tile-text">
                  <span className="kpo-comp-tile-label"><span className="kpo-swatch" style={{ background: COLORS.red }} />Incumplidos</span>
                  <span className="kpo-comp-tile-caption">{fPct(comp.total ? comp.incumplidos / comp.total : null)} del total</span>
                </div>
                <span className="kpo-comp-tile-value kpo-mono" style={{ color: "#B23A0A" }}>{fInt(comp.incumplidos)}</span>
              </div>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 16, minWidth: 0 }}>
              <div className="kpo-card-head">
                <span style={{ fontSize: 14, fontWeight: 600 }}>Cumplidos vs incumplidos por mes</span>
                <div className="kpo-legend">
                  <span><span className="kpo-swatch" style={{ background: COLORS.navy }} />Cumplidos</span>
                  <span><span className="kpo-swatch" style={{ background: COLORS.red }} />Incumplidos</span>
                  <span className="kpo-card-meta">n° de compromisos</span>
                </div>
              </div>
              {maxComp > 0 ? (
                <>
                  <div className="kpo-comp-cols" role="img" aria-label="Compromisos cumplidos e incumplidos por mes">
                    {mensual.map((row) => (
                      <div key={row.periodo} className="kpo-comp-group">
                        <div title={`${periodLabel(row.periodo)}: ${fInt(row.cumplidos)} cumplidos`}>
                          <span className="kpo-mono">{fInt(row.cumplidos)}</span>
                          <div className="kpo-col-bar" style={{ height: `${pct(row.cumplidos, maxComp, 82)}%`, background: COLORS.navy }} />
                        </div>
                        <div title={`${periodLabel(row.periodo)}: ${fInt(row.incumplidos)} incumplidos`}>
                          <span className="kpo-mono">{fInt(row.incumplidos)}</span>
                          <div className="kpo-col-bar" style={{ height: `${pct(row.incumplidos, maxComp, 82)}%`, background: COLORS.red }} />
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className="kpo-comp-labels">
                    {mensual.map((row) => (
                      <div key={row.periodo}>{periodShort(row.periodo)}</div>
                    ))}
                  </div>
                </>
              ) : (
                <div className="kpo-empty">Sin compromisos para los filtros seleccionados.</div>
              )}
            </div>
          </section>

          <div className="kpo-footnote">
            Contactabilidad = casos con contacto directo / casos asignados. Recupero = pagos del mes / saldo asignado
            (contención en carteras vigentes y en mora; recupero en castigo). Casos = RUT único por mandante.
            {resumen.pagos_fuera_asignacion > 0 &&
              ` Los pagos incluyen ${fMM(resumen.pagos_fuera_asignacion)} MM$ de RUT fuera de la asignación del mes, que no entran al % de recupero.`}
          </div>
        </div>
      )}
    </div>
  );
}
