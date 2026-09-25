import React, { useEffect, useState } from "react";
import { useAuth } from "../auth/AuthContext";

import { downloadLaAraucanaExcel, fetchLaAraucanaFilters, fetchLaAraucanaResumen } from "../api";
import { Field, FilterBar, LoadingState, PageHeader, SectionCard } from "../components/productividad/ui";

function formatMoney(value) {
  return new Intl.NumberFormat("es-CL", { maximumFractionDigits: 0 }).format(Number(value || 0));
}

function formatRecovero(value) {
  const n = Number(value || 0);
  return n === 0 ? "-" : formatMoney(n);
}

function formatPct(value) {
  if (value === null || value === undefined) {
    return "";
  }
  return `${(Number(value || 0) * 100).toFixed(2)}%`;
}

function groupRows(rows) {
  const order = ["VIGENTE", "CASTIGO", "+365"];
  const grouped = new Map();

  rows.forEach((row) => {
    const tipo = row.tipo_cartera || "SIN CARTERA";
    if (!grouped.has(tipo)) {
      grouped.set(tipo, { tipo, rows: [], deuda: 0, q_folios: 0, recupero: 0 });
    }
    const group = grouped.get(tipo);
    group.rows.push(row);
    group.deuda += Number(row.deuda || 0);
    group.q_folios += Number(row.q_folios || 0);
    group.recupero += Number(row.recupero || 0);
  });

  return Array.from(grouped.values()).sort((a, b) => {
    const ai = order.indexOf(a.tipo);
    const bi = order.indexOf(b.tipo);
    return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi) || a.tipo.localeCompare(b.tipo);
  });
}

export default function LaAraucanaPage() {
  const { user } = useAuth();
  const [filters, setFilters] = useState({ periodos: [], tipo_cartera: [], ejecutivos: [] });
  const [selected, setSelected] = useState({ periodo: "", cartera_crm: 531, tipo_cartera: "", ejecutivo: "" });
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(null);
  const [loadingFilters, setLoadingFilters] = useState(true);
  const [loading, setLoading] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState("");
  const canDownload = ["super_admin", "admin", "coordinador"].includes(user?.role || "");
  const groupedRows = groupRows(rows);
  const ejecutivoOptions = Array.from(new Set([...(filters.ejecutivos || []), "PHOENIX"]));

  useEffect(() => {
    async function loadFilters() {
      setLoadingFilters(true);
      try {
        const data = await fetchLaAraucanaFilters();
        setFilters(data);
        const periodo = data.periodos?.[0] || "";
        setSelected((prev) => ({ ...prev, periodo }));
      } catch (err) {
        setError(err.message);
      } finally {
        setLoadingFilters(false);
      }
    }
    loadFilters();
  }, []);

  useEffect(() => {
    if (!selected.periodo) {
      return;
    }

    async function loadPeriodFilters() {
      try {
        const data = await fetchLaAraucanaFilters(selected.periodo);
        setFilters(data);
        setSelected((prev) => {
          const next = { ...prev };
          if (next.tipo_cartera && !(data.tipo_cartera || []).includes(next.tipo_cartera)) {
            next.tipo_cartera = "";
          }
          if (next.ejecutivo && next.ejecutivo !== "PHOENIX" && !(data.ejecutivos || []).includes(next.ejecutivo)) {
            next.ejecutivo = "";
          }
          return next;
        });
      } catch (err) {
        setError(err.message);
      }
    }

    loadPeriodFilters();
  }, [selected.periodo]);

  useEffect(() => {
    if (!selected.periodo) {
      return;
    }
    async function loadResumen() {
      setLoading(true);
      setError("");
      try {
        const data = await fetchLaAraucanaResumen(selected);
        setRows(data.rows || []);
        setTotal(data.total || null);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }
    loadResumen();
  }, [selected]);

  function onFilter(name, value) {
    setSelected((prev) => ({ ...prev, [name]: value }));
  }

  function onPeriodo(value) {
    setSelected((prev) => ({ ...prev, periodo: value, tipo_cartera: "" }));
  }

  async function onDownload() {
    if (!selected.periodo) {
      return;
    }
    setDownloading(true);
    setError("");
    try {
      const { blob, filename } = await downloadLaAraucanaExcel(selected.periodo, selected.tipo_cartera || "");
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      setError(err.message || "No se pudo descargar el Excel");
    } finally {
      setDownloading(false);
    }
  }

  return (
    <div className="pd-page">
      <PageHeader
        title="La Araucana"
        subtitle="Productividad Caja La Araucana por tipo de cartera."
        actions={
          canDownload && (
            <button type="button" className="pd-btn pd-btn-secondary" onClick={onDownload} disabled={!selected.periodo || downloading}>
              <i className="bi bi-download" aria-hidden="true" /> {downloading ? "Descargando..." : "Descargar Excel"}
            </button>
          )
        }
      />

      <FilterBar>
        <Field label="Periodo">
          <select className="form-select" value={selected.periodo} onChange={(e) => onPeriodo(e.target.value)} disabled={loadingFilters}>
            {!filters.periodos.length && <option value="">{loadingFilters ? "Cargando..." : "Sin meses"}</option>}
            {filters.periodos.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Tipo cartera">
          <select className="form-select" value={selected.tipo_cartera} onChange={(e) => onFilter("tipo_cartera", e.target.value)}>
            <option value="">Todas</option>
            {filters.tipo_cartera.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Ejecutivo">
          <select className="form-select" value={selected.ejecutivo} onChange={(e) => onFilter("ejecutivo", e.target.value)}>
            <option value="">Todos</option>
            {ejecutivoOptions.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </Field>
      </FilterBar>

      {error && <div className="alert alert-danger">{error}</div>}

      <SectionCard bodyClassName="">
        {loading ? (
          <LoadingState />
        ) : (
          <div className="pd-table-scroll">
            <table className="pd-table">
              <colgroup>
                <col style={{ width: "26%" }} />
                <col style={{ width: "16%" }} />
                <col style={{ width: "13%" }} />
                <col style={{ width: "15%" }} />
                <col style={{ width: "15%" }} />
                <col style={{ width: "15%" }} />
              </colgroup>
              <thead>
                <tr>
                  <th>Ejecutivo</th>
                  <th className="pd-num">Deuda</th>
                  <th className="pd-num">Q Folios</th>
                  <th className="pd-num">Recupero</th>
                  <th className="pd-num">% Contacto Titular</th>
                  <th className="pd-num pd-th-key">% Aporte</th>
                </tr>
              </thead>
              <tbody>
                {groupedRows.map((group) => (
                  <React.Fragment key={group.tipo}>
                    <tr className="pd-row-group">
                      <td colSpan={6}>{group.tipo}</td>
                    </tr>
                    {group.rows.map((row) => (
                      <tr key={`${row.tipo_cartera}-${row.ejecutivo}`}>
                        <td className="pd-cell-indent">{row.ejecutivo}</td>
                        <td className="pd-num">{formatMoney(row.deuda)}</td>
                        <td className="pd-num">{formatMoney(row.q_folios)}</td>
                        <td className="pd-num">{formatRecovero(row.recupero)}</td>
                        <td className="pd-num">{formatPct(row.pct_contacto_titular)}</td>
                        <td className="pd-num pd-cell-strong">{formatPct(row.pct_aporte)}</td>
                      </tr>
                    ))}
                  </React.Fragment>
                ))}
                {total && (
                  <tr className="pd-row-total">
                    <td>{total.ejecutivo}</td>
                    <td className="pd-num">{formatMoney(total.deuda)}</td>
                    <td className="pd-num">{formatMoney(total.q_folios)}</td>
                    <td className="pd-num">{formatRecovero(total.recupero)}</td>
                    <td className="pd-num">{formatPct(total.pct_contacto_titular)}</td>
                    <td className="pd-num">{formatPct(total.pct_aporte)}</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>
    </div>
  );
}
