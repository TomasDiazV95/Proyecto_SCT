import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import KpiTable from "../components/KpiTable";
import { fetchPorscheDashboard, fetchPorscheFilters } from "../api";

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
  recuperacion: "Recuperacion",
  contenido: "Composicion Recupero Contenido",
  normalizado: "Composicion Recupero Normalizado",
  campana_renegociacion: "Campana Renegociacion",
  tpr: "TPR",
  reiteracion_contacto: "Reiteracion Contacto (RC)",
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
    { key: "asignado", label: "Casos Campana", type: "number" },
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
  return (
    <section className="card shadow-sm kpi-block">
      <div className="card-header porsche-kpi-title">
        <h2 className="h5 mb-0 text-center w-100">KPI: {labelForSection[sectionKey]}</h2>
      </div>
      <div className="card-body p-0">
        <KpiTable columns={columnsForSection[sectionKey]} rows={rows} totalRow={totalRow} />
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
  const [dashboard, setDashboard] = useState({ sections: {} });
  const [months, setMonths] = useState([]);
  const [selectedMonth, setSelectedMonth] = useState("");
  const [loading, setLoading] = useState(true);
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
        const defaultMonth = data.filters?.default_mes || availableMonths.at(-1) || "";
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
        const dashboardData = await fetchPorscheDashboard({ mes: selectedMonth });
        if (!alive) {
          return;
        }
        setDashboard({
          summary: dashboardData.summary || {},
          sections: dashboardData.sections || {},
        });
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

  return (
    <div className="container-fluid py-4 app-shell porsche-page">
      <div className="d-flex justify-content-between align-items-center mb-3">
        <div>
          <h1 className="h3 m-0">Porsche - Dashboard KPI</h1>
          <Link to="/" className="small text-decoration-none">
            Volver al Home
          </Link>
        </div>
        <div className="d-flex align-items-center gap-2">
          <label className="form-label mb-0">Mes</label>
          <select
            className="form-select"
            value={selectedMonth}
            onChange={(e) => setSelectedMonth(e.target.value)}
            style={{ minWidth: 140 }}
          >
            {!months.length && <option value="">Sin meses</option>}
            {months.map((month) => (
              <option key={month} value={month}>
                {month}
              </option>
            ))}
          </select>
        </div>
      </div>

      {error && <div className="alert alert-danger">{error}</div>}

      {loading ? (
        <div className="card shadow-sm">
          <div className="card-body text-center py-5">Cargando dashboard...</div>
        </div>
      ) : (
        <div className="d-grid gap-3">
          {sections.map(({ sectionKey, rows, totalRow }) => (
            <DashboardSection key={sectionKey} sectionKey={sectionKey} rows={rows} totalRow={totalRow} />
          ))}
        </div>
      )}
    </div>
  );
}
