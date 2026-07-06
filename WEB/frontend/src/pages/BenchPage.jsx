import { useEffect, useMemo, useState } from "react";
import { fetchBenchFilters, fetchBenchKpi } from "../api";


function formatPct(value) {
  return `${Number(value || 0).toFixed(1)} %`;
}


function formatPp(value) {
  const number = Number(value || 0);
  const sign = number > 0 ? "+" : "";
  return `${sign}${number.toFixed(1)} pp`;
}


function formatMonth(periodo) {
  const [year, month] = String(periodo || "").split("-");
  const monthNames = {
    "01": "Enero",
    "02": "Febrero",
    "03": "Marzo",
    "04": "Abril",
    "05": "Mayo",
    "06": "Junio",
    "07": "Julio",
    "08": "Agosto",
    "09": "Septiembre",
    "10": "Octubre",
    "11": "Noviembre",
    "12": "Diciembre",
  };
  return monthNames[month] || periodo;
}


function formatDateLabel(value) {
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return `${String(date.getDate()).padStart(2, "0")}-${String(date.getMonth() + 1).padStart(2, "0")}`;
}


function formatTimestamp(value) {
  if (!value) {
    return "N/D";
  }
  const normalized = String(value).replace(" ", "T");
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  return `${formatDateLabel(normalized.slice(0, 10))} · ${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
}


function buildCompanyColorMap(series, ranking) {
  const phoenixColor = "#f59e0b";
  const competitorPalette = ["#60a5fa", "#34d399", "#f472b6", "#a78bfa", "#f97316"];
  const names = [];
  ranking.forEach((row) => {
    if (row?.empresa && !names.includes(row.empresa)) {
      names.push(row.empresa);
    }
  });
  series.forEach((item) => {
    Object.keys(item.empresas || {}).forEach((empresa) => {
      if (!names.includes(empresa)) {
        names.push(empresa);
      }
    });
  });
  const colorMap = {};
  let competitorIndex = 0;
  names.forEach((empresa) => {
    if (String(empresa || "").trim().toUpperCase() === "PHOENIX") {
      colorMap[empresa] = phoenixColor;
      return;
    }
    colorMap[empresa] = competitorPalette[competitorIndex % competitorPalette.length];
    competitorIndex += 1;
  });
  return colorMap;
}


function Chart({ series, companyColors }) {
  const width = 860;
  const height = 290;
  const padding = { top: 28, right: 26, bottom: 38, left: 42 };
  const allValues = series.flatMap((item) => Object.values(item.empresas || {})).map((value) => Number(value || 0));
  const minValue = allValues.length ? Math.min(...allValues) : 0;
  const maxValue = allValues.length ? Math.max(...allValues) : 0;
  const valueFloor = Math.max(0, Math.floor((minValue - 1) / 2) * 2);
  const valueCeil = Math.ceil((maxValue + 1) / 2) * 2 || 10;
  const xStep = series.length > 1 ? (width - padding.left - padding.right) / (series.length - 1) : 0;
  const yRange = Math.max(valueCeil - valueFloor, 1);
  const companyNames = Array.from(new Set(series.flatMap((item) => Object.keys(item.empresas || {}))));

  function xFor(index) {
    return padding.left + xStep * index;
  }

  function yFor(value) {
    return padding.top + ((valueCeil - Number(value || 0)) / yRange) * (height - padding.top - padding.bottom);
  }

  const ticks = Array.from({ length: 5 }, (_, index) => valueFloor + (yRange / 4) * index);

  return (
    <div className="bench-chart-block">
      <div className="bench-panel-head">
        <div className="bench-panel-title">Cumplimiento Diario vs. Competencia</div>
        <div className="bench-panel-legend">
          <span className="bench-panel-legend-label">Empresa</span>
          {companyNames.map((company, index) => (
            <span key={company} className="bench-panel-legend-item">
              <span className="bench-panel-legend-dot" style={{ backgroundColor: companyColors[company] }} />
              {company}
            </span>
          ))}
        </div>
      </div>

      <svg viewBox={`0 0 ${width} ${height}`} className="bench-chart-svg-clean" role="img" aria-label="Cumplimiento diario comparado por empresa">
        {ticks.map((tick) => (
          <g key={`tick-${tick}`}>
            <line x1={padding.left} y1={yFor(tick)} x2={width - padding.right} y2={yFor(tick)} className="bench-grid-line-clean" />
            <text x={padding.left - 8} y={yFor(tick) + 4} className="bench-axis-label-clean bench-axis-label-y-clean">
              {Number(tick).toFixed(0)} %
            </text>
          </g>
        ))}

        {series.map((item, index) => (
          <text key={`label-${item.fecha}`} x={xFor(index)} y={height - 12} textAnchor="middle" className="bench-axis-label-clean">
            {formatDateLabel(item.fecha)}
          </text>
        ))}

        {companyNames.map((company) => {
          const color = companyColors[company];
          const points = series
            .map((item, index) => {
              const value = item.empresas?.[company];
              if (value === undefined || value === null) {
                return null;
              }
              return `${xFor(index)},${yFor(value)}`;
            })
            .filter(Boolean)
            .join(" ");

          return (
            <g key={company}>
              <polyline points={points} fill="none" stroke={color} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
              {series.map((item, index) => {
                const value = item.empresas?.[company];
                if (value === undefined || value === null) {
                  return null;
                }
                return <circle key={`${company}-${item.fecha}`} cx={xFor(index)} cy={yFor(value)} r="4.5" fill={color} />;
              })}
            </g>
          );
        })}
      </svg>
    </div>
  );
}


function buildInsight({ comparison, ranking, competitorAverage }) {
  const phoenix = ranking.find((item) => item.is_phoenix);
  const competitorsAhead = ranking.filter((item) => !item.is_phoenix && item.debug_ultimo_dia > (phoenix?.debug_ultimo_dia || 0)).length;
  const totalCompetitors = ranking.filter((item) => !item.is_phoenix).length;
  const leaderName = comparison.competitor_name || "lider";
  const leaderGap = Math.abs(Number(comparison.value || 0)).toFixed(1);
  const averageGap = Math.abs(Number(phoenix?.debug_ultimo_dia || 0) - Number(competitorAverage || 0)).toFixed(1);
  if (!phoenix) {
    return "Phoenix no aparece en el filtro seleccionado.";
  }
  if (!comparison.competitor_name) {
    return "Phoenix no tiene competidores comparables en este filtro.";
  }
  if (Number(phoenix?.ranking || 999) === 1) {
    return `Phoenix lidera, con ${leaderGap} pp sobre ${leaderName} y ${averageGap} pp sobre el promedio de la competencia.`;
  }
  return `Phoenix está ${averageGap} pp ${Number(phoenix?.debug_ultimo_dia || 0) >= Number(competitorAverage || 0) ? "sobre" : "bajo"} el promedio y a ${leaderGap} pp de ${leaderName}.`;
}


function MetricCard({ title, value, subtitle, tone = "neutral", active = false, subtitleIconClass = "" }) {
  return (
    <div className={`bench-metric-card ${active ? "bench-metric-card-active" : ""}`}>
      <div className={`bench-metric-dot bench-metric-dot-${tone}`} />
      <div className="bench-metric-title">{title}</div>
      <div className={`bench-metric-value ${tone === "danger" ? "bench-metric-value-danger" : ""} ${tone === "positive" ? "bench-metric-value-positive" : ""}`}>{value}</div>
      <div className={`bench-metric-subtitle ${tone === "danger" ? "bench-metric-subtitle-danger" : ""} ${tone === "positive" ? "bench-metric-subtitle-positive" : ""}`}>
        {subtitleIconClass ? (
          <i className={subtitleIconClass} aria-hidden="true" />
        ) : (
          <>
            {(tone === "phoenix" || tone === "neutral" || tone === "positive") && <i className="fi fi-br-arrow-small-up" aria-hidden="true" />}
            {tone === "danger" && <i className="fi fi-br-arrow-small-down" aria-hidden="true" />}
            {tone === "leader" && <i className="fi fi-bs-signal-alt-2" aria-hidden="true" />}
          </>
        )}
        <span>{subtitle}</span>
      </div>
    </div>
  );
}


export default function BenchPage() {
  const [filters, setFilters] = useState({ periodo: "", negocio: "", segmento: "" });
  const [options, setOptions] = useState({ periodos: [], negocios: [], segmentos: [] });
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadFilters() {
      try {
        const response = await fetchBenchFilters();
        setOptions(response);
        setFilters({
          periodo: response.periodos?.[0] || "",
          negocio: response.negocios?.[0] || "",
          segmento: response.segmentos?.[0] || "",
        });
      } catch (err) {
        setError(err.message);
      }
    }
    loadFilters();
  }, []);

  useEffect(() => {
    async function refreshFilterOptions() {
      if (!filters.negocio) {
        return;
      }
      try {
        const response = await fetchBenchFilters({
          negocio: filters.negocio,
          periodo: filters.periodo,
        });
        setOptions((prev) => ({
          ...prev,
          periodos: response.periodos || prev.periodos,
          segmentos: response.segmentos || [],
        }));
        setFilters((prev) => {
          const nextPeriodo = (response.periodos || []).includes(prev.periodo) ? prev.periodo : (response.periodos || [])[0] || "";
          const nextSegmento = (response.segmentos || []).includes(prev.segmento) ? prev.segmento : (response.segmentos || [])[0] || "";
          if (nextPeriodo === prev.periodo && nextSegmento === prev.segmento) {
            return prev;
          }
          return { ...prev, periodo: nextPeriodo, segmento: nextSegmento };
        });
      } catch (err) {
        setError(err.message);
      }
    }
    refreshFilterOptions();
  }, [filters.negocio, filters.periodo]);

  useEffect(() => {
    async function loadData() {
      if (!filters.periodo) {
        return;
      }
      setLoading(true);
      setError("");
      try {
        const response = await fetchBenchKpi(filters);
        setData(response);
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

  const ranking = data?.ranking || [];
  const series = data?.serie_diaria || [];
  const sourceInfo = data?.source_info || {};
  const summary = data?.summary || {};
  const comparison = data?.phoenix_vs_competencia || {};
  const phoenixItem = ranking.find((item) => item.is_phoenix);
  const leaderItem = ranking.find((item) => !item.is_phoenix);
  const competitorRows = ranking.filter((item) => !item.is_phoenix);
  const competitorAverage = competitorRows.length
    ? competitorRows.reduce((acc, item) => acc + Number(item.debug_ultimo_dia || 0), 0) / competitorRows.length
    : 0;
  const avgDelta = Number(phoenixItem?.debug_ultimo_dia || 0) - competitorAverage;
  const isPhoenixLeader = Number(phoenixItem?.ranking || 999) === 1;
  const updatedLabel = useMemo(() => {
    if (!sourceInfo.fecha_actualizacion) {
      return "N/D";
    }
    return formatTimestamp(sourceInfo.fecha_actualizacion);
  }, [sourceInfo.fecha_actualizacion]);
  const insight = useMemo(() => buildInsight({ comparison, ranking, competitorAverage }), [comparison, ranking, competitorAverage]);
  const companyColors = useMemo(() => buildCompanyColorMap(series, ranking), [series, ranking]);

  return (
    <div className="container-fluid py-4 app-shell bench-page bench-page-dark">
      <div className="bench-clean-header">
        <div className="bench-clean-title">
          <div className="bench-clean-logo">
            <i className="fi fi-br-dashboard-monitor bench-dashboard-monitor-icon" aria-hidden="true" />
          </div>
          <div>
            <h1>Cumplimiento diario y Ranking</h1>
            <p>Actualizado {updatedLabel}</p>
          </div>
        </div>

        <div className="bench-clean-badges">
          <span className="bench-clean-badge">{ranking.length ? `${phoenixItem?.ranking || "-"}° de ${ranking.length}` : "Sin ranking"}</span>
        </div>
      </div>

      <div className="bench-clean-toolbar">
        <div className="bench-clean-filter">
          <label><i className="fi fi-br-briefcase" aria-hidden="true" /> Negocio</label>
          <select value={filters.negocio} onChange={(e) => onFilter("negocio", e.target.value)}>
            {options.negocios.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
        </div>

        <div className="bench-clean-filter">
          <label><i className="fi fi-br-chart-pie-alt" aria-hidden="true" /> Segmento</label>
          <select value={filters.segmento} onChange={(e) => onFilter("segmento", e.target.value)}>
            {options.segmentos.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
        </div>

        <div className="bench-clean-filter">
          <label><i className="fi fi-br-calendar-day" aria-hidden="true" /> Mes</label>
          <select value={filters.periodo} onChange={(e) => onFilter("periodo", e.target.value)}>
            {options.periodos.map((item) => (
              <option key={item} value={item}>{formatMonth(item)}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="bench-clean-metrics">
        <MetricCard
          title="Phoenix · nosotros"
          value={formatPct(phoenixItem?.debug_ultimo_dia || comparison.phoenix)}
          subtitle={`${avgDelta >= 0 ? "+" : ""}${avgDelta.toFixed(1)} pp vs promedio`}
          tone="phoenix"
          active
        />
        <MetricCard
          title={`${isPhoenixLeader ? "Competidor más cercano" : "Líder"} · ${leaderItem?.empresa || "N/D"}`}
          value={formatPct(leaderItem?.debug_ultimo_dia || comparison.competitor)}
          subtitle={isPhoenixLeader ? `a ${Math.abs(Number(comparison.value || 0)).toFixed(1)} pp de Phoenix` : "a superar"}
          tone="leader"
          subtitleIconClass="none"
        />
        <MetricCard
          title="Promedio competencia"
          value={formatPct(competitorAverage)}
          subtitle={`${avgDelta >= 0 ? "+" : ""}${avgDelta.toFixed(1)} pp Phoenix`}
          tone={avgDelta < 0 ? "danger" : "neutral"}
        />
        <MetricCard
          title="Brecha vs líder"
          value={formatPp(comparison.value)}
          subtitle={isPhoenixLeader ? "liderando" : "para liderar"}
          tone={Number(comparison.value || 0) < 0 ? "danger" : "positive"}
        />
      </div>

      <div className="bench-clean-insight">
        <i className="fi fi-bs-dot-circle" aria-hidden="true" />
        <span>{insight}</span>
      </div>

      {error && <div className="alert alert-danger mt-3">{error}</div>}

      <div className="bench-clean-grid">
        <section className="bench-clean-panel">
          {loading ? (
            <div className="text-center py-5 text-light">Cargando panel BENCH...</div>
          ) : series.length ? (
            <Chart series={series} companyColors={companyColors} />
          ) : (
            <div className="text-center py-5 text-light">No hay datos disponibles para los filtros seleccionados.</div>
          )}
        </section>

        <aside className="bench-clean-panel">
          <div className="bench-panel-title">
            <i className="fi fi-bs-signal-alt-2" aria-hidden="true" />
            <span> Ranking de empresas</span>
          </div>
          <table className="table bench-ranking-table-dark mb-0">
            <thead>
              <tr>
                <th>Empresa</th>
                <th>Ranking</th>
                <th>Cumplimiento</th>
              </tr>
            </thead>
            <tbody>
              {ranking.map((row) => (
                <tr key={row.empresa} className={row.is_phoenix ? "bench-ranking-highlight-phoenix" : ""}>
                  <td>
                    <span className="bench-company-dot" style={{ backgroundColor: companyColors[row.empresa] }} />
                    {row.empresa}
                  </td>
                  <td>{row.ranking}</td>
                  <td>{formatPct(row.debug_ultimo_dia)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </aside>
      </div>

    </div>
  );
}
