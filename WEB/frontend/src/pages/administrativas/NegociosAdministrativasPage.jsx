import { useEffect, useState } from "react";
import { deleteNegocioCarga, downloadNegociosPlantilla, fetchNegociosCargas, uploadNegocioCarga } from "../../api";
import { PageHeader, SectionCard } from "../../components/productividad/ui";
import { saveDownload } from "../../utils/download";

const BREADCRUMB = [
  { label: "Inicio", to: "/" },
  { label: "Panel Administrativo", to: "/administrativas" },
];

// Un Excel por negocio. negocio es el codigo del backend (negocios_service.NEGOCIOS).
const NEGOCIOS = [
  {
    negocio: "sc-terreno",
    title: "SC Terreno",
    description: "Se cuentan en la productividad SC Tardía. Tipos de negocio: reconducción, refinanciamiento, dación.",
  },
  {
    negocio: "sc-telefonia",
    title: "SC Telefonía",
    description: "Se cuentan en la productividad SC Temprana. Tipos de negocio: reconducción, refinanciamiento, novación, dación.",
  },
  {
    negocio: "gm",
    title: "General Motors",
    description: "Se cuentan en la productividad GM. Tipo de negocio: extensión.",
  },
];

const MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];

function formatPeriodo(periodo) {
  const [anio, mes] = String(periodo || "").split("-");
  return anio && mes ? `${MESES[Number(mes) - 1]} ${anio}` : "";
}

function formatFecha(value) {
  const fecha = new Date(value);
  return Number.isNaN(fecha.getTime()) ? "" : fecha.toLocaleString("es-CL", { dateStyle: "short", timeStyle: "short" });
}

export default function NegociosAdministrativasPage() {
  const [cargas, setCargas] = useState([]);
  const [archivos, setArchivos] = useState({});
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [resumen, setResumen] = useState(null);

  async function loadCargas() {
    try {
      setCargas(await fetchNegociosCargas());
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    loadCargas();
  }, []);

  async function run(key, action) {
    setBusy(key);
    setError("");
    setResumen(null);
    try {
      await action();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy("");
    }
  }

  function onPlantilla(negocio) {
    run(`plantilla-${negocio.negocio}`, async () => {
      const file = await downloadNegociosPlantilla(negocio.negocio);
      saveDownload(file.blob, file.filename);
    });
  }

  function onUpload(negocio) {
    const archivo = archivos[negocio.negocio];
    if (!archivo) {
      return;
    }
    run(`subir-${negocio.negocio}`, async () => {
      const body = await uploadNegocioCarga({ negocio: negocio.negocio, archivo });
      setResumen({ ...body, titulo: negocio.title });
      setArchivos((prev) => ({ ...prev, [negocio.negocio]: null }));
      await loadCargas();
    });
  }

  function onDelete(carga, negocio) {
    if (!window.confirm(`¿Eliminar los negocios de ${negocio.title} de ${formatPeriodo(carga.periodo)}? Dejan de contarse en la productividad.`)) {
      return;
    }
    run(`del-${carga.id_carga}`, async () => {
      await deleteNegocioCarga(carga.id_carga);
      await loadCargas();
    });
  }

  return (
    <div className="pd-page">
      <PageHeader
        title="Negocios"
        subtitle="Sube el Excel de negocios de cada cartera; el conteo por ejecutivo aparece en la pestaña Negocios de su productividad."
        breadcrumb={BREADCRUMB}
      />

      <div className="alert alert-light border">
        Cada Excel lleva las columnas <strong>OP, TIPO NEGOCIO, EJECUTIVO y PERIODO</strong> (mes del negocio como mm-yyyy, por ejemplo
        09-2026). Al subirlo, cada mes que trae el archivo reemplaza lo que ese negocio tenía cargado para ese mes.
      </div>

      {error && <div className="alert alert-danger">{error}</div>}

      {resumen && (
        <div className="alert alert-success">
          <strong>{resumen.titulo}:</strong> {resumen.filas} negocios cargados (
          {resumen.periodos.map((item) => `${formatPeriodo(item.periodo)}: ${item.filas}${item.reemplazo ? ", reemplazó la carga anterior" : ""}`).join("; ")}
          ). {resumen.por_producto.map((item) => `${item.nombre}: ${item.total}`).join(" · ")}
          {resumen.sin_cruce.length > 0 && (
            <div className="mt-2">
              <i className="bi bi-exclamation-triangle" aria-hidden="true" /> No están entre los ejecutivos del mes en la productividad
              (se cuentan igual, con el nombre del archivo): {resumen.sin_cruce.join(", ")}.
            </div>
          )}
          {resumen.sin_tipo > 0 && (
            <div className="mt-2">
              <i className="bi bi-exclamation-triangle" aria-hidden="true" /> {resumen.sin_tipo} filas sin TIPO NEGOCIO.
            </div>
          )}
          {resumen.sin_ejecutivo > 0 && (
            <div className="mt-2">
              <i className="bi bi-exclamation-triangle" aria-hidden="true" /> {resumen.sin_ejecutivo} filas sin EJECUTIVO.
            </div>
          )}
        </div>
      )}

      {NEGOCIOS.map((negocio) => {
        const archivo = archivos[negocio.negocio];
        const cargasNegocio = cargas.filter((item) => item.negocio === negocio.negocio);
        return (
          <SectionCard
            key={negocio.negocio}
            title={negocio.title}
            description={negocio.description}
            bodyClassName=""
            actions={
              <button type="button" className="pd-btn pd-btn-ghost pd-btn-sm" onClick={() => onPlantilla(negocio)} disabled={Boolean(busy)}>
                <i className="bi bi-download" aria-hidden="true" /> Descargar plantilla
              </button>
            }
          >
            <ul className="pd-download-list">
              <li className="pd-download-row pd-upload-row">
                <div className="pd-download-text">
                  <span className="pd-download-title">Subir negocios</span>
                  <span className="pd-download-desc">Excel .xlsx con el formato de la plantilla. Puede traer uno o varios meses.</span>
                </div>
                <label className="pd-download-periodo">
                  <span className="visually-hidden">Archivo de negocios de {negocio.title}</span>
                  <input
                    // Al limpiar el archivo elegido se vuelve a montar el campo, que no se puede vaciar por valor.
                    key={archivo ? "con-archivo" : "sin-archivo"}
                    type="file"
                    accept=".xlsx"
                    className="form-control"
                    onChange={(event) => setArchivos((prev) => ({ ...prev, [negocio.negocio]: event.target.files?.[0] || null }))}
                    disabled={Boolean(busy)}
                  />
                </label>
                <button type="button" className="pd-btn pd-btn-primary" onClick={() => onUpload(negocio)} disabled={!archivo || Boolean(busy)}>
                  <i className="bi bi-upload" aria-hidden="true" /> {busy === `subir-${negocio.negocio}` ? "Subiendo..." : "Subir"}
                </button>
              </li>
            </ul>
            <div className="pd-table-scroll">
              <table className="pd-table pd-table-plain pd-table-compact">
                <thead>
                  <tr>
                    <th>Mes</th>
                    <th className="pd-num">Negocios</th>
                    <th>Archivo</th>
                    <th>Subido por</th>
                    <th>Fecha de carga</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {cargasNegocio.map((carga) => (
                    <tr key={carga.id_carga}>
                      <td>{formatPeriodo(carga.periodo)}</td>
                      <td className="pd-num">{carga.filas}</td>
                      <td>{carga.nombre_archivo}</td>
                      <td>{carga.cargado_por}</td>
                      <td>{formatFecha(carga.fecha_carga)}</td>
                      <td className="pd-num">
                        <button
                          type="button"
                          className="pd-btn pd-btn-ghost pd-btn-sm pd-btn-danger-text"
                          onClick={() => onDelete(carga, negocio)}
                          disabled={Boolean(busy)}
                        >
                          <i className="bi bi-trash" aria-hidden="true" /> Eliminar
                        </button>
                      </td>
                    </tr>
                  ))}
                  {!cargasNegocio.length && (
                    <tr>
                      <td colSpan={6} className="pd-muted">Aún no hay negocios cargados.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </SectionCard>
        );
      })}
    </div>
  );
}
