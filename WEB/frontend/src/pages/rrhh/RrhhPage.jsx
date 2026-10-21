import { useEffect, useRef, useState } from "react";
import { downloadRrhhConsolidado, downloadRrhhPlanilla, fetchRrhhNegocios, fetchRrhhPeriodos, fetchRrhhPlanilla } from "../../api";
import { EmptyRow, Field, FilterBar, LoadingState, PageHeader, SectionCard, ViewTabs } from "../../components/productividad/ui";
import { saveDownload } from "../../utils/download";
import useDataVersion, { mantenerSiExiste } from "../../hooks/useDataVersion";

const BREADCRUMB = [
  { label: "Inicio", to: "/" },
  { label: "Panel RRHH", to: "/rrhh" },
];

// Mismas columnas que la planilla de RRHH. type define como se muestra el valor en la vista previa.
const COLUMNS = [
  { key: "CLIENTE", label: "Cliente" },
  { key: "CAMPAÑA", label: "Campaña" },
  { key: "VARIABLE A EVALUAR", label: "Variable a evaluar" },
  { key: "COLABORADOR", label: "Colaborador" },
  { key: "CUMPLIMIENTO TOTAL INDIVIDUAL", label: "Cumpl. total individual", type: "pct" },
  { key: "APORTE INDIVIDUAL", label: "Aporte individual", type: "pct" },
  { key: "CUMPLIMIENTOS GRUPALES", label: "Cumpl. grupales", type: "pct" },
  { key: "INSERTAR Q VARIABLES", label: "Q variables", type: "num" },
];

// Detalle de los negocios cursados (hoja NEGOCIOS del Excel).
const NEGOCIO_COLUMNS = [
  { key: "CAMPAÑA", label: "Campaña" },
  { key: "TIPO NEGOCIO", label: "Tipo de negocio" },
  { key: "N° OPERACIÓN", label: "N° operación" },
  { key: "EJECUTIVO", label: "Ejecutivo" },
  { key: "MONTO DEUDA", label: "Monto deuda", type: "num" },
  { key: "ABONO INICIAL", label: "Abono inicial", type: "num" },
  { key: "TRAMO", label: "Tramo" },
  { key: "FECHA", label: "Fecha" },
];

// Efectivo recuperado por ejecutivo (hoja EFECTIVO RECUPERADO del Excel).
const EFECTIVO_COLUMNS = [
  { key: "CAMPAÑA", label: "Campaña" },
  { key: "EJECUTIVO", label: "Ejecutivo" },
  { key: "CONCEPTO", label: "Concepto" },
  { key: "Q CUOTAS PAGADAS", label: "Q cuotas pagadas", type: "num" },
  { key: "EFECTIVO RECUPERADO", label: "Efectivo recuperado", type: "num" },
];

// Detalle por operacion (hoja EFECTIVO POR OPERACION). Itau Castigo viene por RUT: sin N° de operacion.
const EFECTIVO_DETALLE_COLUMNS = [
  { key: "EJECUTIVO", label: "Ejecutivo" },
  { key: "CONCEPTO", label: "Concepto" },
  { key: "N° OPERACIÓN", label: "N° operación" },
  { key: "RUT CLIENTE", label: "RUT cliente" },
  { key: "NOMBRE CLIENTE", label: "Nombre cliente" },
  { key: "MONTO DEUDA", label: "Monto deuda", type: "num" },
  { key: "Q CUOTAS PAGADAS", label: "Q cuotas pagadas", type: "num" },
  { key: "EFECTIVO RECUPERADO", label: "Efectivo recuperado", type: "num" },
  { key: "FECHA RECUPERO", label: "Fecha recupero" },
];

function DetalleTable({ columns, rows, rowKey }) {
  return (
    <div className="pd-table-scroll">
      <table className="pd-table pd-table-compact">
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column.key} className={column.type ? "pd-num" : undefined}>{column.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, idx) => (
            <tr key={`${rowKey(row)}-${idx}`}>
              {columns.map((column) => (
                <td key={column.key} className={column.type ? "pd-num" : column.key === "EJECUTIVO" ? "pd-cell-ejecutivo" : undefined}>
                  {formatValue(row[column.key], column.type)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function formatPeriodo(periodo) {
  if (!periodo) {
    return "";
  }
  const [year, month] = String(periodo).split("-");
  const text = new Intl.DateTimeFormat("es-CL", { month: "long", year: "numeric" }).format(new Date(Number(year), Number(month) - 1, 1));
  return text.charAt(0).toUpperCase() + text.slice(1);
}

// Las columnas que no aplican a la variable vienen como "N/A", igual que en la planilla.
function formatValue(value, type) {
  if (typeof value !== "number") {
    return value ?? "";
  }
  if (type === "pct") {
    return `${(value * 100).toLocaleString("es-CL", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`;
  }
  return value.toLocaleString("es-CL", { maximumFractionDigits: 0 });
}

export default function RrhhPage() {
  const dataVersion = useDataVersion();
  const [periodos, setPeriodos] = useState([]);
  const [periodo, setPeriodo] = useState("");
  const [negocios, setNegocios] = useState([]);
  const [loadingNegocios, setLoadingNegocios] = useState(false);
  const [preview, setPreview] = useState(null);
  const [loadingPreview, setLoadingPreview] = useState("");
  const [view, setView] = useState("cumplimientos");
  const [downloading, setDownloading] = useState("");
  const [error, setError] = useState("");
  const previewRef = useRef(null);

  // La vista previa queda bajo la lista de negocios: al cargarla se lleva la pantalla hasta ella.
  useEffect(() => {
    if (preview) {
      previewRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [preview]);

  useEffect(() => {
    fetchRrhhPeriodos()
      .then((data) => {
        setPeriodos(data);
        // Por defecto el mes anterior: es el que se cierra y se paga.
        setPeriodo((prev) => mantenerSiExiste(prev, data, data[1] || data[0] || ""));
      })
      .catch((err) => setError(err.message));
  }, [dataVersion]);

  useEffect(() => {
    if (!periodo) {
      return;
    }
    setLoadingNegocios(true);
    setError("");
    setPreview(null);
    fetchRrhhNegocios(periodo)
      .then(setNegocios)
      .catch((err) => setError(err.message))
      .finally(() => setLoadingNegocios(false));
  }, [periodo, dataVersion]);

  async function onPreview(negocio) {
    setLoadingPreview(negocio.codigo);
    setError("");
    try {
      const data = await fetchRrhhPlanilla(periodo, negocio.codigo);
      setView("cumplimientos");
      setPreview(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoadingPreview("");
    }
  }

  // key identifica el boton en curso: el codigo del negocio o "consolidado".
  async function onDownload(key, download) {
    setDownloading(key);
    setError("");
    try {
      const file = await download();
      saveDownload(file.blob, file.filename);
    } catch (err) {
      setError(err.message || "No se pudo descargar la planilla.");
    } finally {
      setDownloading("");
    }
  }

  const tieneNegocios = Boolean(preview?.negocios?.length);
  const tieneEfectivo = Boolean(preview?.efectivo?.length);
  const tieneDetalle = tieneNegocios || tieneEfectivo;
  const vistaNegocios = tieneNegocios && view === "negocios";
  const vistaEfectivo = tieneEfectivo && view === "efectivo";
  const vistaEfectivoDetalle = tieneEfectivo && view === "efectivo-detalle";
  const hayDisponibles = negocios.some((negocio) => negocio.disponible);

  return (
    <div className="pd-page">
      <PageHeader
        title="Cumplimientos de Campañas"
        subtitle="Variables y cumplimiento por ejecutivo de cada negocio, en el formato de la planilla de RRHH."
        breadcrumb={BREADCRUMB}
      />

      <FilterBar
        actions={
          <button
            type="button"
            className="pd-btn pd-btn-primary"
            onClick={() => onDownload("consolidado", () => downloadRrhhConsolidado(periodo))}
            disabled={!hayDisponibles || Boolean(downloading)}
          >
            <i className="bi bi-file-earmark-spreadsheet" aria-hidden="true" />{" "}
            {downloading === "consolidado" ? "Generando consolidado..." : "Exportar consolidado"}
          </button>
        }
        note="Cada negocio usa su último corte disponible del mes. Solo se incluyen las variables que calcula la plataforma; el RUT queda en blanco. El Excel trae además la hoja NEGOCIOS con el detalle de cada operación y el efectivo recuperado en dos hojas: por ejecutivo y por operación."
      >
        <Field label="Mes">
          <select className="form-select" value={periodo} onChange={(event) => setPeriodo(event.target.value)} disabled={Boolean(downloading)}>
            {periodos.map((value) => (
              <option key={value} value={value}>
                {formatPeriodo(value)}
              </option>
            ))}
          </select>
        </Field>
      </FilterBar>

      {error && <div className="alert alert-danger">{error}</div>}

      <SectionCard title="Planillas por negocio" description={`Exporta la planilla de cada negocio para ${formatPeriodo(periodo) || "el mes elegido"}.`} bodyClassName="">
        {loadingNegocios ? (
          <LoadingState text="Buscando el corte de cada negocio..." />
        ) : (
          <ul className="pd-download-list">
            {negocios.map((negocio) => (
              <li className="pd-download-row" key={negocio.codigo}>
                <div className="pd-download-text">
                  <span className="pd-download-title">{negocio.campana}</span>
                  <span className="pd-download-desc">{negocio.cliente}</span>
                </div>
                <span className="pd-small pd-muted">
                  {negocio.disponible ? `Corte ${negocio.corte}` : negocio.error ? "No se pudo consultar" : "Sin datos del mes"}
                </span>
                <div className="d-flex gap-2">
                  <button
                    type="button"
                    className="pd-btn pd-btn-secondary"
                    onClick={() => onPreview(negocio)}
                    disabled={!negocio.disponible || Boolean(loadingPreview)}
                  >
                    <i className="bi bi-eye" aria-hidden="true" /> {loadingPreview === negocio.codigo ? "Cargando..." : "Ver"}
                  </button>
                  <button
                    type="button"
                    className="pd-btn pd-btn-primary"
                    onClick={() => onDownload(negocio.codigo, () => downloadRrhhPlanilla(periodo, negocio.codigo))}
                    disabled={!negocio.disponible || Boolean(downloading)}
                  >
                    <i className="bi bi-download" aria-hidden="true" /> {downloading === negocio.codigo ? "Exportando..." : "Exportar planilla"}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </SectionCard>

      {preview && (
        <div ref={previewRef} className={tieneDetalle ? "pd-tabbed" : undefined}>
        {tieneDetalle && (
          <ViewTabs
            value={view}
            onChange={setView}
            options={[
              { value: "cumplimientos", label: "Cumplimientos" },
              ...(tieneNegocios ? [{ value: "negocios", label: `Detalle de negocios (${preview.negocios.length})` }] : []),
              ...(tieneEfectivo
                ? [
                    { value: "efectivo", label: "Efectivo por ejecutivo" },
                    { value: "efectivo-detalle", label: `Efectivo por operación (${preview.efectivo_detalle?.length || 0})` },
                  ]
                : []),
            ]}
          />
        )}
        {vistaNegocios ? (
          <SectionCard
            title={`${preview.campana} · Detalle de negocios`}
            description={`Corte ${preview.corte || "N/D"} · ${preview.negocios.length} negocios cursados en el mes, con su operación y ejecutivo.`}
            bodyClassName=""
          >
            <DetalleTable columns={NEGOCIO_COLUMNS} rows={preview.negocios} rowKey={(row) => `${row["N° OPERACIÓN"]}-${row["RUT CLIENTE"]}`} />
          </SectionCard>
        ) : vistaEfectivo ? (
          <SectionCard
            title={`${preview.campana} · Efectivo recuperado`}
            description={`Corte ${preview.corte || "N/D"} · efectivo recuperado por ejecutivo, como lo muestra el panel.`}
            bodyClassName=""
          >
            <DetalleTable columns={EFECTIVO_COLUMNS} rows={preview.efectivo} rowKey={(row) => `${row["CAMPAÑA"]}-${row.EJECUTIVO}-${row.CONCEPTO}`} />
          </SectionCard>
        ) : vistaEfectivoDetalle ? (
          <SectionCard
            title={`${preview.campana} · Efectivo por operación`}
            description={`Corte ${preview.corte || "N/D"} · detalle que suma el efectivo de cada ejecutivo. Itaú Castigo viene por RUT: el archivo del banco no trae N° de operación.`}
            bodyClassName=""
          >
            <DetalleTable
              columns={EFECTIVO_DETALLE_COLUMNS}
              rows={preview.efectivo_detalle || []}
              rowKey={(row) => `${row.EJECUTIVO}-${row["N° OPERACIÓN"]}-${row["RUT CLIENTE"]}`}
            />
          </SectionCard>
        ) : (
        <SectionCard title={preview.campana} description={`Corte ${preview.corte || "N/D"} · ${preview.rows.length} filas`} bodyClassName="">
          <div className="pd-table-scroll">
            <table className="pd-table pd-table-compact">
              <thead>
                <tr>
                  {COLUMNS.map((column) => (
                    <th key={column.key} className={column.type ? "pd-num" : undefined}>{column.label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {preview.rows.map((row, idx) => (
                  <tr key={`${row["CAMPAÑA"]}-${row.COLABORADOR}-${row["VARIABLE A EVALUAR"]}-${idx}`}>
                    {COLUMNS.map((column) => (
                      <td key={column.key} className={column.type ? "pd-num" : column.key === "COLABORADOR" ? "pd-cell-ejecutivo" : undefined}>
                        {formatValue(row[column.key], column.type)}
                      </td>
                    ))}
                  </tr>
                ))}
                {!preview.rows.length && <EmptyRow colSpan={COLUMNS.length} text="El panel de este negocio no tiene cumplimientos calculados para el mes." />}
              </tbody>
            </table>
          </div>
        </SectionCard>
        )}
        </div>
      )}
    </div>
  );
}
