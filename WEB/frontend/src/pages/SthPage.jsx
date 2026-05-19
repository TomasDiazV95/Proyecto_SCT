import { Fragment, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { fetchSthDetail, fetchSthFilters, fetchSthGeneral } from "../api";

const initialFilters = {
  periodo: "",
  ejecutivo: "",
};

const productLabel = {
  hipotecario: "Hipotecario",
  consumo: "Consumo",
  pyme: "Pyme",
  tarjeta: "TC",
};

function formatPct(value) {
  if (value === null || value === undefined) {
    return "-";
  }
  return `${Number(value || 0).toFixed(1)}%`;
}

function formatMoney(value) {
  return new Intl.NumberFormat("es-CL", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(Number(value || 0));
}

function formatMM(value) {
  return formatMoney(Number(value || 0) / 1000000);
}

function percentile(sortedValues, p) {
  if (!sortedValues.length) {
    return 0;
  }
  const idx = (sortedValues.length - 1) * p;
  const lower = Math.floor(idx);
  const upper = Math.ceil(idx);
  if (lower === upper) {
    return sortedValues[lower];
  }
  const weight = idx - lower;
  return sortedValues[lower] * (1 - weight) + sortedValues[upper] * weight;
}

function dotClassByThresholds(value, thresholds) {
  const n = Number(value || 0);
  if (n >= thresholds.p66) {
    return "gm-dot gm-dot-ok";
  }
  if (n >= thresholds.p33) {
    return "gm-dot gm-dot-warn";
  }
  return "gm-dot gm-dot-bad";
}

export default function SthPage() {
  const [view, setView] = useState("general");
  const [filters, setFilters] = useState(initialFilters);
  const [options, setOptions] = useState({ periodos: [], ejecutivos: [] });
  const [generalRows, setGeneralRows] = useState([]);
  const [detailBlocks, setDetailBlocks] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadFilters() {
      try {
        const data = await fetchSthFilters();
        setOptions(data);
        setFilters((prev) => ({
          ...prev,
          periodo: data.periodos?.[0] || "",
        }));
      } catch (err) {
        setError(err.message);
      }
    }
    loadFilters();
  }, []);

  useEffect(() => {
    async function loadData() {
      if (!filters.periodo) {
        return;
      }
      setLoading(true);
      setError("");
      try {
        const [general, detail] = await Promise.all([fetchSthGeneral(filters), fetchSthDetail(filters)]);
        setGeneralRows(general);
        setDetailBlocks(detail);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, [filters]);

  const generalHeaders = useMemo(
    () => [
      { key: "hipotecario", label: "Cump Hip" },
      { key: "consumo", label: "Cump Cons" },
      { key: "pyme", label: "Cump Pyme" },
      { key: "tarjeta", label: "Cump TC" },
    ],
    []
  );

  const thresholdsByProduct = useMemo(() => {
    const out = {};
    detailBlocks.forEach((block) => {
      const values = [];
      (block.pivot_rows || []).forEach((row) => {
        if (String(row.ejecutivo || "").trim().toLowerCase() === "grupal") {
          return;
        }
        values.push(Number(row.cumplimiento_final || 0));
        (block.ciclos || []).forEach((ciclo) => {
          const item = row.ciclos?.[String(ciclo)];
          if (item) {
            values.push(Number(item.cumplimiento_meta || 0));
          }
        });
      });
      const sorted = values.filter((v) => Number.isFinite(v)).sort((a, b) => a - b);
      out[block.producto] = {
        p33: percentile(sorted, 0.33),
        p66: percentile(sorted, 0.66),
      };
    });
    return out;
  }, [detailBlocks]);

  const generalThresholds = useMemo(() => {
    const values = (generalRows || [])
      .filter((row) => row.ejecutivo !== "Total general")
      .filter((row) => String(row.ejecutivo || "").trim().toLowerCase() !== "grupal")
      .map((row) => Number(row.cumplimiento_final || 0))
      .filter((v) => Number.isFinite(v))
      .sort((a, b) => a - b);

    return {
      p33: percentile(values, 0.33),
      p66: percentile(values, 0.66),
    };
  }, [generalRows]);

  function productDotClass(producto, value) {
    const thresholds = thresholdsByProduct[producto] || { p33: 0, p66: 0 };
    return dotClassByThresholds(value, thresholds);
  }

  function onChange(name, value) {
    setFilters((prev) => ({ ...prev, [name]: value }));
  }

  return (
    <div className="container-fluid py-4 app-shell sth-page">
      <div className="d-flex justify-content-between align-items-center mb-3">
        <div>
          <h1 className="h3 m-0">STH - KPI Hipotecario</h1>
          <Link to="/" className="small text-decoration-none">
            Volver al Home
          </Link>
        </div>
        <div className="btn-group">
          <button className={`btn btn-${view === "general" ? "primary" : "outline-primary"}`} onClick={() => setView("general")}>
            Vista General
          </button>
          <button className={`btn btn-${view === "desglosada" ? "primary" : "outline-primary"}`} onClick={() => setView("desglosada")}>
            Vista Desglosada
          </button>
        </div>
      </div>

      <div className="card shadow-sm mb-3">
        <div className="card-body">
          <div className="row g-2">
            <div className="col-12 col-md-2">
              <label className="form-label">Periodo</label>
              <select className="form-select" value={filters.periodo} onChange={(e) => onChange("periodo", e.target.value)}>
                {options.periodos.map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
              </select>
            </div>
            <div className="col-12 col-md-3">
              <label className="form-label">Ejecutivo</label>
              <select className="form-select" value={filters.ejecutivo} onChange={(e) => onChange("ejecutivo", e.target.value)}>
                <option value="">Todos</option>
                {options.ejecutivos.map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>
      </div>

      {error && <div className="alert alert-danger">{error}</div>}

      <div className="card shadow-sm">
        <div className="card-body table-responsive sth-table-shell">
          {loading ? (
            <div className="text-center py-4">Cargando...</div>
          ) : view === "general" ? (
            <table className="table table-striped table-hover align-middle sth-general-table sth-compact-table">
              <thead>
                <tr>
                  <th>Ejecutivo</th>
                  {generalHeaders.map((h) => (
                    <th key={h.key}>{h.label}</th>
                  ))}
                  <th>Producto Trabajado</th>
                  <th>Tramo</th>
                  <th>Cum Final</th>
                </tr>
              </thead>
              <tbody>
                {generalRows.map((row, idx) => (
                  <tr key={`${row.ejecutivo}-${idx}`} className={row.ejecutivo === "Total general" ? "table-primary fw-semibold" : ""}>
                    <td>{row.ejecutivo}</td>
                    {generalHeaders.map((h) => (
                      <td key={`${row.ejecutivo}-${h.key}`}>{formatPct(row[h.key])}</td>
                    ))}
                    <td>{row.producto_trabajado ? productLabel[row.producto_trabajado] || row.producto_trabajado : "-"}</td>
                    <td>{row.tramo_trabajado || "-"}</td>
                    <td className="fw-semibold">
                      <span className={dotClassByThresholds(row.cumplimiento_final, generalThresholds)} /> {formatPct(row.cumplimiento_final)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="sth-detail-wrap">
              {detailBlocks.map((block) => (
                <div className="mb-4" key={block.producto}>
                  <div className="sth-section-title">{productLabel[block.producto] || block.producto}</div>
                  <div className="small text-muted mb-1">
                    Meta: {block.totales_por_ciclo.map((tot) => `${tot.tramo} ${formatPct(tot.meta_contenido_pct)}`).join(" | ")}
                  </div>
                  <table className="table table-striped table-hover align-middle sth-detail-table sth-compact-table">
                    <thead>
                      <tr>
                        <th rowSpan={2}>Ejecutivo</th>
                        {block.ciclos.map((ciclo) => (
                          <th key={`${block.producto}-h-${ciclo}`} colSpan={4} className="text-center">
                            {block.producto === "tarjeta" ? "Multiciclo" : `Ciclo ${ciclo}`}
                          </th>
                        ))}
                        <th rowSpan={2}>Cumplimiento Final</th>
                      </tr>
                      <tr>
                        {block.ciclos.map((ciclo) => (
                          <Fragment key={`${block.producto}-sub-${ciclo}`}>
                            <th>Deuda Asignada</th>
                            <th>Saldo Contenido</th>
                            <th>% Contenido</th>
                            <th>Cump Meta</th>
                          </Fragment>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {block.pivot_rows.map((row) => (
                        <tr key={`${block.producto}-${row.ejecutivo}`}>
                          <td>{row.ejecutivo}</td>
                          {block.ciclos.map((ciclo) => {
                            const item = row.ciclos?.[String(ciclo)];
                            return (
                              <Fragment key={`${block.producto}-${row.ejecutivo}-cset-${ciclo}`}>
                                <td>{item ? `$${formatMM(item.deuda_asignada)} MM` : ""}</td>
                                <td>{item ? `$${formatMM(item.saldo_contenido)} MM` : ""}</td>
                                <td>{item ? formatPct(item.porcentaje_contenido) : ""}</td>
                                <td className="fw-semibold">
                                  {item ? (
                                    <>
                                      <span className={productDotClass(block.producto, item.cumplimiento_meta)} /> {formatPct(item.cumplimiento_meta)}
                                    </>
                                  ) : (
                                    ""
                                  )}
                                </td>
                              </Fragment>
                            );
                          })}
                          <td className="fw-semibold">
                            <span className={productDotClass(block.producto, row.cumplimiento_final)} /> {formatPct(row.cumplimiento_final)}
                          </td>
                        </tr>
                      ))}
                      <tr className="table-primary fw-semibold">
                        <td>Total general</td>
                        {block.ciclos.map((ciclo) => {
                          const tot = block.totales_por_ciclo.find((x) => x.ciclo === ciclo);
                          return (
                            <Fragment key={`${block.producto}-tot-set-${ciclo}`}>
                              <td>{tot ? `$${formatMM(tot.deuda_asignada)} MM` : ""}</td>
                              <td>{tot ? `$${formatMM(tot.saldo_contenido)} MM` : ""}</td>
                              <td>{tot ? formatPct(tot.porcentaje_contenido) : ""}</td>
                              <td>
                                {tot ? (
                                  <>
                                    <span className={productDotClass(block.producto, tot.cumplimiento_meta)} /> {formatPct(tot.cumplimiento_meta)}
                                  </>
                                ) : (
                                  ""
                                )}
                              </td>
                            </Fragment>
                          );
                        })}
                        <td>
                          <span className={productDotClass(block.producto, block.cumplimiento_final_bloque)} /> {formatPct(block.cumplimiento_final_bloque)}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
