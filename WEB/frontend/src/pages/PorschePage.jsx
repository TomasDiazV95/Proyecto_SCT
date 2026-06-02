import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import KpiTable from "../components/KpiTable";
import { downloadPorscheExcel, fetchPorscheCuadroContenido, fetchPorscheDashboard, fetchPorscheFilters } from "../api";

const order = [
  "contactabilidad",
  "promesas_pago",
  "promesas_cumplidas",
  "promesas_incumplidas",
  "recuperacion",
  "contenido",
  "normalizado",
  "campana_renegociacion",
  "tpr",
  "reiteracion_contacto",
];

const labelForSection = {
  contactabilidad: "Contactabilidad",
  promesas_pago: "Promesas de pagos",
  promesas_cumplidas: "Promesas cumplidas",
  promesas_incumplidas: "Promesas Incumplidas",
  recuperacion: "Recuperación",
  contenido: "Composición Recupero Contenido",
  normalizado: "Composición Recupero Normalizado",
  campana_renegociacion: "Campaña Renegociación",
  tpr: "TPR",
  reiteracion_contacto: "Reiteración Contacto (RC)",
};

const columnsForSection = {
  contactabilidad: [
    { key: "tramo", label: "Tramo", type: "text" },
    { key: "meta", label: "Meta", type: "percent" },
    { key: "asignado", label: "Asignado", type: "number" },
    { key: "casos_contactados", label: "Casos Contactados", type: "number" },
    { key: "pct_contacto", label: "% Contacto", type: "percent" },
    { key: "brecha", label: "Brecha", type: "percent" },
    { key: "cumplimiento", label: "Cumplimiento", type: "percent" },
  ],
  promesas_pago: [
    { key: "tramo", label: "Tramo", type: "text" },
    { key: "meta", label: "Meta", type: "percent" },
    { key: "asignado", label: "Casos Contactados", type: "number" },
    { key: "casos_con_promesa", label: "Casos con promesa", type: "number" },
    { key: "pct_promesa_pago", label: "% Promesa Pago", type: "percent" },
    { key: "brecha", label: "Brecha", type: "percent" },
    { key: "cumplimiento", label: "Cumplimiento", type: "percent" },
  ],
  promesas_cumplidas: [
    { key: "tramo", label: "Tramo", type: "text" },
    { key: "meta", label: "Meta", type: "percent" },
    { key: "asignado", label: "Casos con promesa", type: "number" },
    { key: "promesas_cumplidas", label: "Pagados", type: "number" },
    { key: "pct_cumplimiento_promesa", label: "% Promesa Pago", type: "percent" },
    { key: "brecha", label: "Brecha", type: "percent" },
    { key: "cumplimiento", label: "Cumplimiento", type: "percent" },
  ],
  promesas_incumplidas: [
    { key: "tramo", label: "Tramo", type: "text" },
    { key: "meta", label: "Meta", type: "percent" },
    { key: "asignado", label: "Casos con promesa", type: "number" },
    { key: "promesas_incumplidas", label: "Incumplidos", type: "number" },
    { key: "pct_incumplido", label: "% Promesa Pago", type: "percent" },
    { key: "brecha", label: "Brecha", type: "percent" },
    { key: "cumplimiento", label: "Cumplimiento", type: "percent" },
  ],
  recuperacion: [
    { key: "tramo", label: "Tramo", type: "text" },
    { key: "meta", label: "Meta", type: "percent" },
    { key: "asignado", label: "Asignado", type: "number" },
    { key: "casos_pagados", label: "Pagados", type: "number" },
    { key: "pct_recupero", label: "% Recupero", type: "percent" },
    { key: "brecha", label: "Brecha", type: "percent" },
    { key: "cumplimiento", label: "Cumplimiento", type: "percent" },
  ],
  contenido: [
    { key: "tramo", label: "Tramo", type: "text" },
    { key: "meta", label: "Meta", type: "percent" },
    { key: "asignado", label: "Asignado", type: "number" },
    { key: "casos_contenidos", label: "Casos Contenidos", type: "number" },
    { key: "pct_contenido", label: "% Contenido", type: "percent" },
    { key: "brecha", label: "Brecha", type: "percent" },
    { key: "cumplimiento", label: "Cumplimiento", type: "percent" },
  ],
  normalizado: [
    { key: "tramo", label: "Tramo", type: "text" },
    { key: "meta", label: "Meta", type: "percent" },
    { key: "asignado", label: "Asignado", type: "number" },
    { key: "casos_normalizados", label: "Casos Normalizados", type: "number" },
    { key: "pct_normalizado", label: "% Contenido", type: "percent" },
    { key: "brecha", label: "Brecha", type: "percent" },
    { key: "cumplimiento", label: "Cumplimiento", type: "percent" },
  ],
  campana_renegociacion: [
    { key: "tramo", label: "Tramo", type: "text" },
    { key: "meta", label: "Meta", type: "percent" },
    { key: "asignado", label: "Casos Campaña", type: "number" },
    { key: "kpi", label: "KPI", type: "number" },
    { key: "pct_kpi", label: "% KPI", type: "percent" },
    { key: "brecha", label: "Brecha", type: "percent" },
    { key: "cumplimiento", label: "Cumplimiento", type: "percent" },
  ],
  tpr: [
    { key: "tramo", label: "Tramo", type: "text" },
    { key: "meta", label: "Meta", type: "number", aggregate: "avg" },
    { key: "asignado", label: "Asignado", type: "number" },
    { key: "TPR", label: "TPR", type: "number", aggregate: "avg" },
    { key: "pct_kpi", label: "% KPI", type: "percent", aggregate: "avg" },
    { key: "brecha", label: "Brecha", type: "percent", aggregate: "avg" },
    { key: "cumplimiento", label: "Cumplimiento", type: "percent", aggregate: "avg" },
  ],
  reiteracion_contacto: [
    { key: "tramo", label: "Tramo", type: "text" },
    { key: "meta", label: "Meta", type: "number" },
    { key: "casos_sin_contacto", label: "Casos sin contacto", type: "number" },
    { key: "RC", label: "RC", type: "number" },
    { key: "pct_kpi", label: "% KPI", type: "percent" },
    { key: "brecha", label: "Brecha", type: "percent" },
    { key: "cumplimiento", label: "Cumplimiento", type: "percent" },
  ],
};

function DashboardSection({ sectionKey, rows, totalRow }) {
  const cumplimientoMode = (sectionKey === "tpr" || sectionKey === "reiteracion_contacto") ? "one" : "meta";
  return (
    <section className="card shadow-sm kpi-block">
      <div className="card-header porsche-kpi-title">
        <h2 className="h5 mb-0 text-center w-100">KPI: {labelForSection[sectionKey]}</h2>
      </div>
      <div className="card-body p-0">
        <KpiTable columns={columnsForSection[sectionKey]} rows={rows} totalRow={totalRow} cumplimientoMode={cumplimientoMode} />
      </div>
    </section>
  );
}

function formatPercent0(value) {
  if (value === null || value === undefined || value === "") {
    return "";
  }
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue)) {
    return "";
  }
  return `${Math.round(numericValue * 100)}%`;
}

function CuadroContenido({ data }) {
  const rows = data?.rows || [];
  const total = data?.resultado_total;
  const row3160 = rows.find((row) => row.negocio_pw === "31-60");
  const row6190 = rows.find((row) => row.negocio_pw === "61-90");
  const rowFinal = rows.find((row) => row.negocio_pw === "121-150");
  return (
    <section className="card shadow-sm porsche-cuadro-box">
      <div className="card-body p-0">
        <table className="table mb-0 porsche-cuadro-table">
          <thead>
            <tr>
              <th>NegocioPW</th>
              <th>Ponderador</th>
              <th>Meta total</th>
              <th>Real Total</th>
              <th>Cumplimiento</th>
              <th>Resultado</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>31-60</td>
              <td>{formatPercent0(row3160?.ponderador)}</td>
              <td>{formatPercent0(row3160?.meta_total)}</td>
              <td>{formatPercent0(row3160?.real_total)}</td>
              <td>{formatPercent0(row3160?.cumplimiento)}</td>
              <td>{formatPercent0(row3160?.resultado)}</td>
            </tr>
            <tr>
              <td>61-90</td>
              <td>{formatPercent0(row6190?.ponderador)}</td>
              <td>{formatPercent0(row6190?.meta_total)}</td>
              <td>{formatPercent0(row6190?.real_total)}</td>
              <td>{formatPercent0(row6190?.cumplimiento)}</td>
              <td>{formatPercent0(row6190?.resultado)}</td>
            </tr>
            <tr>
              <td>91-120</td>
              <td rowSpan={4} className="align-middle">{formatPercent0(rowFinal?.ponderador)}</td>
              <td rowSpan={4} className="align-middle">{formatPercent0(rowFinal?.meta_total)}</td>
              <td rowSpan={4} className="align-middle">{formatPercent0(rowFinal?.real_total)}</td>
              <td rowSpan={4} className="align-middle">{formatPercent0(rowFinal?.cumplimiento)}</td>
              <td rowSpan={4} className="align-middle">{formatPercent0(rowFinal?.resultado)}</td>
            </tr>
            <tr>
              <td>121-150</td>
            </tr>
            <tr>
              <td>151-180</td>
            </tr>
            <tr>
              <td>181-210</td>
            </tr>
            <tr>
              <td colSpan={5}></td>
              <td className="fw-bold">{formatPercent0(total)}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  );
}

function buildContactabilidadTotal(rows) {
  const tramoOrder = ["31-60", "61-90", "91-120", "121-150", "151-180", "181-210", "211-240"];
  const totalAsignado = rows.reduce((acc, row) => acc + Number(row.asignado || 0), 0);
  const totalContactados = rows.reduce((acc, row) => acc + Number(row.casos_contactados || 0), 0);
  const firstFour = tramoOrder.slice(0, 4);
  const metaValues = rows
    .filter((row) => firstFour.includes(row.tramo))
    .map((row) => Number(row.meta || 0))
    .filter((value) => Number.isFinite(value));

  const meta = metaValues.length ? metaValues.reduce((acc, value) => acc + value, 0) / metaValues.length : 0;
  const pctContacto = totalAsignado ? totalContactados / totalAsignado : 0;

  return {
    tramo: "TOTAL",
    meta,
    asignado: totalAsignado,
    casos_contactados: totalContactados,
    pct_contacto: pctContacto,
    brecha: pctContacto - meta,
    cumplimiento: "",
  };
}

function buildPromesasPagoTotal(rows) {
  const tramoOrder = ["31-60", "61-90", "91-120", "121-150", "151-180", "181-210", "211-240"];
  const totalContactados = rows.reduce((acc, row) => acc + Number(row.asignado || 0), 0);
  const totalPromesas = rows.reduce((acc, row) => acc + Number(row.casos_con_promesa || 0), 0);
  const firstFour = tramoOrder.slice(0, 4);
  const metaValues = rows
    .filter((row) => firstFour.includes(row.tramo))
    .map((row) => Number(row.meta || 0))
    .filter((value) => Number.isFinite(value));

  const meta = metaValues.length ? metaValues.reduce((acc, value) => acc + value, 0) / metaValues.length : 0;
  const pctPromesa = totalContactados ? totalPromesas / totalContactados : 0;

  return {
    tramo: "TOTAL",
    meta,
    asignado: totalContactados,
    casos_con_promesa: totalPromesas,
    pct_promesa_pago: pctPromesa,
    brecha: pctPromesa - meta,
    cumplimiento: "",
  };
}

function buildPromesasCumplidasTotal(rows) {
  const totalCasosConPromesa = rows.reduce((acc, row) => acc + Number(row.asignado || 0), 0);
  const totalPagados = rows.reduce((acc, row) => acc + Number(row.promesas_cumplidas || 0), 0);
  const metaValues = rows
    .slice(0, 4)
    .map((row) => Number(row.meta || 0))
    .filter((value) => Number.isFinite(value));

  const meta = metaValues.length ? metaValues.reduce((acc, value) => acc + value, 0) / metaValues.length : 0;
  const pctCumplimiento = totalCasosConPromesa ? totalPagados / totalCasosConPromesa : 0;

  return {
    tramo: "TOTAL",
    meta,
    asignado: totalCasosConPromesa,
    promesas_cumplidas: totalPagados,
    pct_cumplimiento_promesa: pctCumplimiento,
    brecha: pctCumplimiento - meta,
    cumplimiento: "",
  };
}

function buildPromesasIncumplidasTotal(rows) {
  const totalCasosConPromesa = rows.reduce((acc, row) => acc + Number(row.asignado || 0), 0);
  const totalIncumplidos = rows.reduce((acc, row) => acc + Number(row.promesas_incumplidas || 0), 0);
  const metaValues = rows
    .slice(0, 4)
    .map((row) => Number(row.meta || 0))
    .filter((value) => Number.isFinite(value));

  const meta = metaValues.length ? metaValues.reduce((acc, value) => acc + value, 0) / metaValues.length : 0;
  const pctIncumplido = totalCasosConPromesa ? totalIncumplidos / totalCasosConPromesa : 0;

  return {
    tramo: "TOTAL",
    meta,
    asignado: totalCasosConPromesa,
    promesas_incumplidas: totalIncumplidos,
    pct_incumplido: pctIncumplido,
    brecha: pctIncumplido - meta,
    cumplimiento: "",
  };
}

function buildRecuperacionTotal(rows) {
  const totalAsignado = rows.reduce((acc, row) => acc + Number(row.asignado || 0), 0);
  const totalPagados = rows.reduce((acc, row) => acc + Number(row.casos_pagados || 0), 0);
  const metaValues = rows
    .slice(0, 4)
    .map((row) => Number(row.meta || 0))
    .filter((value) => Number.isFinite(value));

  const meta = metaValues.length ? metaValues.reduce((acc, value) => acc + value, 0) / metaValues.length : 0;
  const pctRecupero = totalAsignado ? totalPagados / totalAsignado : 0;

  return {
    tramo: "TOTAL",
    meta,
    asignado: totalAsignado,
    casos_pagados: totalPagados,
    pct_recupero: pctRecupero,
    brecha: pctRecupero - meta,
    cumplimiento: "",
  };
}

function buildContenidoTotal(rows) {
  const totalAsignado = rows.reduce((acc, row) => acc + Number(row.asignado || 0), 0);
  const totalContenidos = rows.reduce((acc, row) => acc + Number(row.casos_contenidos || 0), 0);
  const metaValues = rows
    .slice(0, 4)
    .map((row) => Number(row.meta || 0))
    .filter((value) => Number.isFinite(value));

  const meta = metaValues.length ? metaValues.reduce((acc, value) => acc + value, 0) / metaValues.length : 0;
  const pctContenido = totalAsignado ? totalContenidos / totalAsignado : 0;

  return {
    tramo: "TOTAL",
    meta,
    asignado: totalAsignado,
    casos_contenidos: totalContenidos,
    pct_contenido: pctContenido,
    brecha: pctContenido - meta,
    cumplimiento: "",
  };
}

function buildNormalizadoTotal(rows) {
  const totalAsignado = rows.reduce((acc, row) => acc + Number(row.asignado || 0), 0);
  const totalNormalizados = rows.reduce((acc, row) => acc + Number(row.casos_normalizados || 0), 0);
  const metaValues = rows
    .slice(0, 4)
    .map((row) => Number(row.meta || 0))
    .filter((value) => Number.isFinite(value));

  const meta = metaValues.length ? metaValues.reduce((acc, value) => acc + value, 0) / metaValues.length : 0;
  const pctContenido = totalAsignado ? totalNormalizados / totalAsignado : 0;

  return {
    tramo: "TOTAL",
    meta,
    asignado: totalAsignado,
    casos_normalizados: totalNormalizados,
    pct_normalizado: pctContenido,
    brecha: pctContenido - meta,
    cumplimiento: "",
  };
}

function buildCampanaRenegociacionTotal(rows) {
  const totalCasosCampana = rows.length
    ? rows.reduce((acc, row) => acc + Number(row.asignado || 0), 0) / rows.length
    : 0;
  const totalKpi = rows.reduce((acc, row) => acc + Number(row.kpi || 0), 0);
  const metaValues = rows
    .map((row) => Number(row.meta || 0))
    .filter((value) => Number.isFinite(value));

  const meta = metaValues.length ? metaValues.reduce((acc, value) => acc + value, 0) / metaValues.length : 0;
  const pctKpi = totalCasosCampana ? totalKpi / totalCasosCampana : 0;

  return {
    tramo: "TOTAL",
    meta,
    asignado: totalCasosCampana,
    kpi: totalKpi,
    pct_kpi: pctKpi,
    brecha: pctKpi - meta,
    cumplimiento: "",
  };
}

function buildTprTotal(rows) {
  const totalAsignado = rows.reduce((acc, row) => acc + Number(row.asignado || 0), 0);
  const avgTpr = rows.length ? rows.reduce((acc, row) => acc + Number(row.TPR || 0), 0) / rows.length : 0;
  const metaValues = rows
    .slice(0, 4)
    .map((row) => Number(row.meta || 0))
    .filter((value) => Number.isFinite(value));

  const meta = metaValues.length ? metaValues.reduce((acc, value) => acc + value, 0) / metaValues.length : 0;
  const pctKpi = meta ? avgTpr / meta : 0;

  return {
    tramo: "TOTAL",
    meta,
    asignado: totalAsignado,
    TPR: avgTpr,
    pct_kpi: pctKpi,
    brecha: "",
    cumplimiento: "",
  };
}

function buildReiteracionTotal(rows) {
  const totalCasosSinContacto = rows.reduce((acc, row) => acc + Number(row.casos_sin_contacto || 0), 0);
  const totalRc = rows.length ? rows.reduce((acc, row) => acc + Number(row.RC || 0), 0) / rows.length : 0;
  const metaValues = rows
    .slice(0, 4)
    .map((row) => Number(row.meta || 0))
    .filter((value) => Number.isFinite(value));

  const meta = metaValues.length ? metaValues.reduce((acc, value) => acc + value, 0) / metaValues.length : 0;

  return {
    tramo: "TOTAL",
    meta,
    casos_sin_contacto: totalCasosSinContacto,
    RC: totalRc,
    pct_kpi: meta ? totalRc / meta : 0,
    brecha: "",
    cumplimiento: "",
  };
}

export default function PorschePage() {
  const [view, setView] = useState("general");
  const [dashboard, setDashboard] = useState({ sections: {} });
  const [cuadroContenido, setCuadroContenido] = useState({ rows: [], resultado_total: 0 });
  const [months, setMonths] = useState([]);
  const [selectedMonth, setSelectedMonth] = useState("");
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;

    async function loadFilters() {
      try {
        const data = await fetchPorscheFilters();
        if (!alive) {
          return;
        }

        const availableMonths = data.filters?.meses || [];
        const defaultMonth = data.filters?.default_mes || (availableMonths.length ? availableMonths[availableMonths.length - 1] : "") || "";
        setMonths(availableMonths);
        setSelectedMonth(defaultMonth);
      } catch (err) {
        if (!alive) {
          return;
        }
        setError(err.message);
        setLoading(false);
      }
    }

    loadFilters();

    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    if (!selectedMonth) {
      return;
    }

    let alive = true;

    async function load() {
      setLoading(true);
      setError("");
      try {
        const [dashboardData, cuadroData] = await Promise.all([
          fetchPorscheDashboard({ mes: selectedMonth }),
          fetchPorscheCuadroContenido({ mes: selectedMonth }),
        ]);
        if (!alive) {
          return;
        }
        setDashboard({
          summary: dashboardData.summary || {},
          sections: dashboardData.sections || {},
        });
        setCuadroContenido(cuadroData.cuadro || { rows: [], resultado_total: 0 });
      } catch (err) {
        if (!alive) {
          return;
        }
        setError("No se pudo cargar el dashboard de Porsche desde la view.");
      } finally {
        if (alive) {
          setLoading(false);
        }
      }
    }

    load();

    return () => {
      alive = false;
    };
  }, [selectedMonth]);

  const sections = useMemo(() => {
    return order
      .filter((sectionKey) => dashboard.sections?.[sectionKey]?.length)
      .map((sectionKey) => ({
        sectionKey,
        rows: dashboard.sections[sectionKey],
        totalRow:
          sectionKey === "contactabilidad"
            ? buildContactabilidadTotal(dashboard.sections[sectionKey])
            : sectionKey === "promesas_pago"
              ? buildPromesasPagoTotal(dashboard.sections[sectionKey])
              : sectionKey === "promesas_cumplidas"
              ? buildPromesasCumplidasTotal(dashboard.sections[sectionKey])
              : sectionKey === "promesas_incumplidas"
                  ? buildPromesasIncumplidasTotal(dashboard.sections[sectionKey])
                  : sectionKey === "recuperacion"
                    ? buildRecuperacionTotal(dashboard.sections[sectionKey])
                    : sectionKey === "contenido"
                      ? buildContenidoTotal(dashboard.sections[sectionKey])
                    : sectionKey === "normalizado"
                        ? buildNormalizadoTotal(dashboard.sections[sectionKey])
                        : sectionKey === "campana_renegociacion"
                          ? buildCampanaRenegociacionTotal(dashboard.sections[sectionKey])
                        : sectionKey === "tpr"
                            ? buildTprTotal(dashboard.sections[sectionKey])
                            : sectionKey === "reiteracion_contacto"
                              ? buildReiteracionTotal(dashboard.sections[sectionKey])
               : undefined,
      }));
  }, [dashboard.sections]);

  async function onDownload() {
    if (!selectedMonth) {
      return;
    }

    setDownloading(true);
    setError("");
    try {
      const { blob, filename } = await downloadPorscheExcel(selectedMonth);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err.message || "No se pudo descargar el Excel de Porsche.");
    } finally {
      setDownloading(false);
    }
  }

  return (
    <div className="container-fluid py-4 app-shell porsche-page">
      <div className="d-flex justify-content-between align-items-center mb-3">
        <div>
          <h1 className="h3 m-0">Seguimiento Porsche</h1>
          <Link to="/" className="small text-decoration-none">
            Volver al Home
          </Link>
        </div>
        <div className="btn-group">
          <button
            className={`btn btn-${view === "general" ? "primary" : "outline-primary"}`}
            onClick={() => setView("general")}
          >
            Vista General
          </button>
          <button
            className={`btn btn-${view === "cierre" ? "primary" : "outline-primary"}`}
            onClick={() => setView("cierre")}
          >
            Cierre
          </button>
        </div>
      </div>

      <div className="card shadow-sm mb-3">
        <div className="card-body">
          <div className="row g-2">
            <div className="col-12 col-md-2">
              <label className="form-label">Periodo</label>
              <select className="form-select" value={selectedMonth} onChange={(e) => setSelectedMonth(e.target.value)}>
                {!months.length && <option value="">Sin meses</option>}
                {months.map((month) => (
                  <option key={month} value={month}>
                    {month}
                  </option>
                ))}
              </select>
            </div>
            <div className="col-12 col-md-auto d-flex align-items-end">
              <button className="btn btn-success w-100" onClick={onDownload} disabled={!selectedMonth || downloading}>
                {downloading ? "Descargando..." : "Descargar Excel PW"}
              </button>
            </div>
          </div>
        </div>
      </div>

      {error && <div className="alert alert-danger">{error}</div>}

      {loading ? (
        <div className="card shadow-sm">
          <div className="card-body text-center py-5">Cargando dashboard...</div>
        </div>
      ) : (
        <div className="d-grid gap-3">
          {view === "cierre" ? (
            <CuadroContenido data={cuadroContenido} />
          ) : (
            sections.map(({ sectionKey, rows, totalRow }) => (
              <DashboardSection key={sectionKey} sectionKey={sectionKey} rows={rows} totalRow={totalRow} />
            ))
          )}
        </div>
      )}
    </div>
  );
}
