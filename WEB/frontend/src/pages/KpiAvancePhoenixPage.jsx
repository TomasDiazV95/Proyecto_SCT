import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  fetchKpiAvancePhoenixComparison,
  fetchKpiAvancePhoenixFilters,
} from "../api";

const MONTH_NAMES = {
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

const SERIES_COLORS = [
  "#f59e0b",
  "#60a5fa",
  "#34d399",
  "#f472b6",
  "#a78bfa",
  "#fb7185",
  "#22d3ee",
  "#bef264",
  "#fb923c",
  "#c084fc",
];

const MAX_COMPARE_MONTHS = 2;

function sortPeriods(periodos) {
  return Array.from(new Set(periodos || [])).sort((a, b) =>
    String(b).localeCompare(String(a)),
  );
}

function formatPct(value) {
  return `${Number(value || 0).toFixed(1)}%`;
}

function formatDifference(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return "N/D";
  }
  return `${number >= 0 ? "+" : ""}${number.toFixed(1)} pp`;
}

function formatMonthLabel(periodo) {
  const [year, month] = String(periodo || "").split("-");
  const monthName = MONTH_NAMES[month] || String(periodo || "");
  return year ? `${monthName} ${year}` : monthName;
}

function formatDateLabel(value) {
  const match = String(value || "").match(/^(\d{4})-(\d{2})-(\d{2})/);
  return match ? `${match[3]}-${match[2]}-${match[1]}` : String(value || "");
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
  return `${String(date.getDate()).padStart(2, "0")}-${String(
    date.getMonth() + 1,
  ).padStart(2, "0")} · ${String(date.getHours()).padStart(2, "0")}:${String(
    date.getMinutes(),
  ).padStart(2, "0")}`;
}

function buildSegments(pointsMap, allDays) {
  const segments = [];
  let current = [];

  allDays.forEach((day) => {
    const point = pointsMap.get(day);
    if (point) {
      current.push({ day, point });
      return;
    }
    if (current.length) {
      segments.push(current);
      current = [];
    }
  });

  if (current.length) {
    segments.push(current);
  }
  return segments;
}

function MonthPicker({ options, value, onChange, disabled }) {
  const selected = new Set(value);

  function toggle(periodo) {
    const next = new Set(selected);
    if (next.has(periodo)) {
      next.delete(periodo);
    } else if (selected.size < MAX_COMPARE_MONTHS) {
      next.add(periodo);
    }
    onChange(options.filter((item) => next.has(item)));
  }

  return (
    <div className="phoenix-month-picker">
      <div className="phoenix-month-options" aria-label="Meses a comparar">
        {options.map((periodo) => (
          <label key={periodo} className="phoenix-month-option">
            <input
              type="checkbox"
              checked={selected.has(periodo)}
              onChange={() => toggle(periodo)}
              disabled={
                disabled ||
                (!selected.has(periodo) && selected.size >= MAX_COMPARE_MONTHS)
              }
            />
            <span>{formatMonthLabel(periodo)}</span>
          </label>
        ))}
        {!options.length && (
          <span className="phoenix-month-empty">No hay meses disponibles.</span>
        )}
      </div>
    </div>
  );
}

function PhoenixComparisonChart({ series }) {
  const [hoveredDay, setHoveredDay] = useState(null);
  const width = 960;
  const height = 380;
  const padding = { top: 28, right: 30, bottom: 52, left: 54 };

  const model = useMemo(() => {
    const preparedSeries = (series || []).map((item, index) => {
      const puntos = Array.isArray(item.puntos) ? item.puntos : [];
      return {
        ...item,
        color: SERIES_COLORS[index % SERIES_COLORS.length],
        puntos,
        pointsMap: new Map(
          puntos.map((point) => [Number(point.dia_habil), point]),
        ),
      };
    });
    const allDays = Array.from(
      new Set(
        preparedSeries.flatMap((item) =>
          item.puntos
            .map((point) => Number(point.dia_habil))
            .filter(Number.isFinite),
        ),
      ),
    ).sort((a, b) => a - b);
    const allValues = preparedSeries
      .flatMap((item) => item.puntos.map((point) => Number(point.cumplimiento)))
      .filter(Number.isFinite);
    const maxValue = allValues.length ? Math.max(...allValues) : 0;

    return {
      preparedSeries,
      allDays,
      dayIndexMap: new Map(allDays.map((day, index) => [day, index])),
      valueCeil: Math.max(100, Math.ceil((maxValue + 5) / 5) * 5),
    };
  }, [series]);

  const { preparedSeries, allDays, dayIndexMap, valueCeil } = model;
  const chartHeight = height - padding.top - padding.bottom;
  const xStep =
    allDays.length > 1
      ? (width - padding.left - padding.right) / (allDays.length - 1)
      : 0;
  const hoveredIndex = hoveredDay === null ? null : dayIndexMap.get(hoveredDay);
  const hoveredX =
    hoveredIndex === null || hoveredIndex === undefined
      ? null
      : padding.left + xStep * hoveredIndex;

  function xFor(index) {
    return padding.left + xStep * index;
  }

  function yFor(value) {
    return padding.top + ((valueCeil - Number(value || 0)) / valueCeil) * chartHeight;
  }

  const hoveredRows =
    hoveredDay === null
      ? []
      : preparedSeries
          .map((item) => {
            const point = item.pointsMap.get(hoveredDay);
            return point ? { ...item, point } : null;
          })
          .filter(Boolean);
  const comparison = (() => {
    if (hoveredRows.length !== MAX_COMPARE_MONTHS) {
      return null;
    }
    const orderedRows = [...hoveredRows].sort((a, b) =>
      String(a.periodo).localeCompare(String(b.periodo)),
    );
    const previousValue = Number(orderedRows[0].point.cumplimiento);
    const currentValue = Number(orderedRows[1].point.cumplimiento);
    const difference = currentValue - previousValue;
    return Number.isFinite(difference) ? { difference } : null;
  })();
  const tooltipWidth = 280;
  const tooltipHeight =
    60 + hoveredRows.length * 36 + (comparison ? 28 : 0);
  const tooltipX =
    hoveredX === null
      ? 0
      : Math.min(
          width - padding.right - tooltipWidth,
          Math.max(
            padding.left,
            hoveredX + 16 > width - padding.right - tooltipWidth
              ? hoveredX - tooltipWidth - 16
              : hoveredX + 16,
          ),
        );
  const tooltipY = Math.min(
    height - padding.bottom - tooltipHeight,
    padding.top + 8,
  );

  if (!allDays.length) {
    return (
      <div className="phoenix-empty-state">
        <strong>No hay días hábiles para graficar.</strong>
        <span>Selecciona otros meses o revisa los filtros.</span>
      </div>
    );
  }

  return (
    <div className="phoenix-chart-wrap" onMouseLeave={() => setHoveredDay(null)}>
      <div className="phoenix-chart-head">
        <div>
          <div className="phoenix-chart-title">
            Cumplimiento Phoenix
          </div>
          <div className="phoenix-chart-note">
            Cada línea representa un mes seleccionado y se alinea por día hábil.
          </div>
        </div>
        <div className="phoenix-chart-legend" aria-label="Meses seleccionados">
          {preparedSeries.map((item) => (
            <span key={item.periodo} className="phoenix-chart-legend-item">
              <span
                className="phoenix-chart-legend-dot"
                style={{ backgroundColor: item.color }}
              />
              {formatMonthLabel(item.periodo)}
            </span>
          ))}
        </div>
      </div>

      <svg
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="xMidYMid meet"
        className="phoenix-chart-svg"
        role="img"
        aria-label="Comparación de cumplimiento de Phoenix por día hábil"
      >
        {Array.from({ length: 5 }, (_, index) => (valueCeil / 4) * index).map(
          (tick) => (
            <g key={`tick-${tick}`}>
              <line
                x1={padding.left}
                y1={yFor(tick)}
                x2={width - padding.right}
                y2={yFor(tick)}
                className="phoenix-grid-line"
              />
              <text
                x={padding.left - 8}
                y={yFor(tick) + 4}
                className="phoenix-axis-label phoenix-axis-label-y"
              >
                {Number(tick).toFixed(0)}%
              </text>
            </g>
          ),
        )}

        {allDays.map((day, index) => (
          <text
            key={`day-${day}`}
            x={xFor(index)}
            y={height - 18}
            textAnchor="middle"
            className="phoenix-axis-label"
          >
            {day}
          </text>
        ))}
        <text
          x={(padding.left + width - padding.right) / 2}
          y={height - 2}
          textAnchor="middle"
          className="phoenix-axis-label"
        >
          Día hábil
        </text>

        {preparedSeries.map((item) => {
          const segments = buildSegments(item.pointsMap, allDays);
          return (
            <g key={item.periodo}>
              {segments.map((segment, segmentIndex) => (
                <polyline
                  key={`${item.periodo}-segment-${segmentIndex}`}
                  points={segment
                    .map(
                      ({ day, point }) =>
                        `${xFor(dayIndexMap.get(day))},${yFor(point.cumplimiento)}`,
                    )
                    .join(" ")}
                  fill="none"
                  stroke={item.color}
                  strokeWidth="3"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              ))}
              {item.puntos.map((point) => {
                const day = Number(point.dia_habil);
                const dayIndex = dayIndexMap.get(day);
                if (dayIndex === undefined) {
                  return null;
                }
                return (
                  <circle
                    key={`${item.periodo}-${day}`}
                    cx={xFor(dayIndex)}
                    cy={yFor(point.cumplimiento)}
                    r={hoveredDay === day ? "6" : "4"}
                    fill={item.color}
                    className={
                      hoveredDay === day ? "phoenix-series-point-hover" : ""
                    }
                  />
                );
              })}
            </g>
          );
        })}

        {allDays.map((day, index) => {
          const currentX = xFor(index);
          const previousX =
            index === 0 ? padding.left : (xFor(index - 1) + currentX) / 2;
          const nextX =
            index === allDays.length - 1
              ? width - padding.right
              : (currentX + xFor(index + 1)) / 2;
          return (
            <rect
              key={`hover-zone-${day}`}
              x={previousX}
              y={padding.top}
              width={Math.max(nextX - previousX, 24)}
              height={chartHeight}
              fill="transparent"
              className="phoenix-hover-zone"
              onMouseEnter={() => setHoveredDay(day)}
              onMouseMove={() => setHoveredDay(day)}
            />
          );
        })}

        {hoveredDay !== null && hoveredX !== null && hoveredRows.length > 0 && (
          <g className="phoenix-tooltip-layer">
            <line
              x1={hoveredX}
              y1={padding.top}
              x2={hoveredX}
              y2={height - padding.bottom}
              className="phoenix-hover-guide"
            />
            <g transform={`translate(${tooltipX}, ${tooltipY})`}>
              <rect
                width={tooltipWidth}
                height={tooltipHeight}
                rx="12"
                className="phoenix-tooltip-box"
              />
              <text x="14" y="21" className="phoenix-tooltip-title">
                Día hábil {hoveredDay}
              </text>
              {hoveredRows.map((row, rowIndex) => {
                const y = 49 + rowIndex * 36;
                return (
                  <g key={row.periodo}>
                    <circle cx="19" cy={y - 4} r="4.3" fill={row.color} />
                    <text x="32" y={y - 8} className="phoenix-tooltip-label">
                      {formatMonthLabel(row.periodo)}
                    </text>
                    <text x="32" y={y + 9} className="phoenix-tooltip-day">
                      {formatDateLabel(row.point.fecha)}
                    </text>
                    <text
                      x={tooltipWidth - 14}
                      y={y}
                      textAnchor="end"
                      className="phoenix-tooltip-value"
                    >
                      {formatPct(row.point.cumplimiento)}
                    </text>
                  </g>
                );
              })}
              {comparison && (
                <g>
                  <text
                    x="14"
                    y={58 + hoveredRows.length * 36}
                    className="phoenix-tooltip-difference-label"
                  >
                    Diferencia vs mes anterior
                  </text>
                  <text
                    x={tooltipWidth - 14}
                    y={58 + hoveredRows.length * 36}
                    textAnchor="end"
                    className={`phoenix-tooltip-difference-value ${
                      comparison.difference >= 0
                        ? "phoenix-tooltip-difference-positive"
                        : "phoenix-tooltip-difference-negative"
                    }`}
                  >
                    {formatDifference(comparison.difference)}
                  </text>
                </g>
              )}
            </g>
          </g>
        )}
      </svg>
    </div>
  );
}

export default function KpiAvancePhoenixPage() {
  const [filters, setFilters] = useState({
    negocio: "",
    segmento: "",
    periodos: [],
  });
  const [options, setOptions] = useState({
    periodos: [],
    negocios: [],
    segmentos: [],
    fecha_actualizacion: "",
  });
  const [data, setData] = useState({ series: [] });
  const [loadingOptions, setLoadingOptions] = useState(false);
  const [loadingData, setLoadingData] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    document.documentElement.classList.add("phoenix-page-active");
    return () => document.documentElement.classList.remove("phoenix-page-active");
  }, []);

  useEffect(() => {
    let active = true;

    async function loadFilters() {
      setLoadingOptions(true);
      try {
        const response = await fetchKpiAvancePhoenixFilters({
          negocio: filters.negocio,
          segmento: filters.segmento,
        });
        if (!active) {
          return;
        }

        const availablePeriodos = sortPeriods(response.periodos || []);
        const availableNegocios = response.negocios || [];
        const availableSegmentos = response.segmentos || [];
        setOptions({
          periodos: availablePeriodos,
          negocios: availableNegocios,
          segmentos: availableSegmentos,
          fecha_actualizacion: response.fecha_actualizacion || "",
        });
        setFilters((previous) => {
          const nextNegocio = availableNegocios.includes(previous.negocio)
            ? previous.negocio
            : availableNegocios[0] || "";
          const currentPeriodos = Array.isArray(previous.periodos)
            ? previous.periodos
            : [];
          const validPeriodos = currentPeriodos.filter((periodo) =>
            availablePeriodos.includes(periodo),
          );
          const nextPeriodos = validPeriodos.length
            ? validPeriodos.slice(0, MAX_COMPARE_MONTHS)
            : availablePeriodos.slice(0, MAX_COMPARE_MONTHS);
          const negocioChanged = nextNegocio !== previous.negocio;
          const nextSegmento = negocioChanged
            ? ""
            : availableSegmentos.includes(previous.segmento)
              ? previous.segmento
              : availableSegmentos[0] || "";

          if (
            nextNegocio === previous.negocio &&
            nextPeriodos.join("|") === currentPeriodos.join("|") &&
            nextSegmento === previous.segmento
          ) {
            return previous;
          }
          return {
            ...previous,
            negocio: nextNegocio,
            periodos: nextPeriodos,
            segmento: nextSegmento,
          };
        });
      } catch (err) {
        if (active) {
          setError(err.message || "No se pudieron cargar los filtros");
        }
      } finally {
        if (active) {
          setLoadingOptions(false);
        }
      }
    }

    loadFilters();
    return () => {
      active = false;
    };
  }, [filters.negocio, filters.segmento]);

  const selectedPeriodsKey = filters.periodos.join("|");

  useEffect(() => {
    if (!selectedPeriodsKey) {
      setData({ series: [] });
      return undefined;
    }

    let active = true;
    async function loadComparison() {
      setLoadingData(true);
      setError("");
      try {
        const response = await fetchKpiAvancePhoenixComparison(filters);
        if (active) {
          setData(response || { series: [] });
        }
      } catch (err) {
        if (active) {
          setError(err.message || "No se pudo cargar la comparación");
        }
      } finally {
        if (active) {
          setLoadingData(false);
        }
      }
    }
    loadComparison();
    return () => {
      active = false;
    };
  }, [filters.negocio, filters.segmento, selectedPeriodsKey]);

  function onNegocioChange(value) {
    setFilters((previous) => ({
      ...previous,
      negocio: value,
      segmento: "",
    }));
  }

  const series = data?.series || [];
  const hasPoints = series.some((item) => (item.puntos || []).length > 0);
  const updatedLabel = formatTimestamp(options.fecha_actualizacion);

  return (
    <div className="container-fluid py-4 app-shell phoenix-kpi-page">
      <div className="phoenix-kpi-shell">
        <div className="bench-header-context phoenix-kpi-context">
          <div className="bench-breadcrumb">
            <Link to="/" className="bench-breadcrumb-link">
              <i className="fi fi-br-home" aria-hidden="true" />
              <span>Inicio</span>
            </Link>
            <span className="bench-breadcrumb-separator">&gt;</span>
            <span className="bench-breadcrumb-current">
              Cumplimiento diario y Ranking
            </span>
          </div>
          <div className="bench-updated-line">
            <i className="fi fi-br-clock-three" aria-hidden="true" />
            <span>Actualizado {updatedLabel}</span>
          </div>
        </div>
        <div className="phoenix-kpi-toolbar">
          <div className="phoenix-kpi-filter">
            <label htmlFor="phoenix-negocio">
              <i className="fi fi-br-briefcase" aria-hidden="true" />
              <span>Negocio</span>
            </label>
            <select
              id="phoenix-negocio"
              className="form-select"
              value={filters.negocio}
              onChange={(event) => onNegocioChange(event.target.value)}
              disabled={loadingOptions}
            >
              {options.negocios.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </div>

          <div className="phoenix-kpi-filter">
            <label htmlFor="phoenix-segmento">
              <i className="fi fi-br-chart-pie-alt" aria-hidden="true" />
              <span>Segmento</span>
            </label>
            <select
              id="phoenix-segmento"
              className="form-select"
              value={filters.segmento}
              onChange={(event) =>
                setFilters((previous) => ({
                  ...previous,
                  segmento: event.target.value,
                }))
              }
              disabled={loadingOptions}
            >
              {options.segmentos.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </div>

          <div className="phoenix-kpi-filter">
            <label>
              <i className="fi fi-br-calendar" aria-hidden="true" />
              <span>Meses a comparar</span>
            </label>
            <MonthPicker
              options={options.periodos}
              value={filters.periodos}
              onChange={(periodos) =>
                setFilters((previous) => ({ ...previous, periodos }))
              }
              disabled={loadingOptions}
            />
          </div>
        </div>

        {error && <div className="alert alert-danger">{error}</div>}

        <div className="phoenix-kpi-card">
          {loadingOptions || loadingData ? (
            <div className="phoenix-empty-state">
              <strong>Cargando comparación...</strong>
              <span>Estamos preparando los meses y el gráfico.</span>
            </div>
          ) : hasPoints ? (
            <PhoenixComparisonChart series={series} />
          ) : (
            <div className="phoenix-empty-state">
              <strong>No hay datos para graficar.</strong>
              <span>Selecciona otros meses o ajusta los filtros.</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
