import { useEffect, useMemo, useState } from "react";
import { fetchNegociosDetalle } from "../../api";
import { EmptyRow, LoadingState, SectionCard } from "./ui";
import useDataVersion from "../../hooks/useDataVersion";

// Pestaña Detalle negocios: una fila por operacion del mes (OP, ejecutivo, tipo de negocio),
// con filtros propios por tipo de negocio y ejecutivo.
// modulo: "sc-tardia", "sc-temprana" o "gm".
export default function NegociosDetalleCard({ modulo, periodo, ejecutivo, exportName }) {
  const dataVersion = useDataVersion();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [tipo, setTipo] = useState("");
  const [ejecutivoTabla, setEjecutivoTabla] = useState("");

  useEffect(() => {
    if (!periodo) {
      return undefined;
    }
    let vigente = true;
    setLoading(true);
    setError("");
    fetchNegociosDetalle(modulo, { periodo, ejecutivo })
      .then((body) => vigente && setData(body))
      .catch((err) => vigente && setError(err.message))
      .finally(() => vigente && setLoading(false));
    return () => {
      vigente = false;
    };
  }, [modulo, periodo, ejecutivo, dataVersion]);

  const filas = data?.filas || [];
  const tipos = useMemo(() => {
    const vistos = new Map();
    filas.forEach((fila) => vistos.set(fila.producto, fila.producto_nombre));
    return Array.from(vistos, ([codigo, nombre]) => ({ codigo, nombre }));
  }, [filas]);
  const ejecutivos = useMemo(() => Array.from(new Set(filas.map((fila) => fila.ejecutivo))).sort(), [filas]);

  // Si el filtro elegido ya no existe en el mes consultado, se limpia.
  useEffect(() => {
    if (tipo && !tipos.some((t) => t.codigo === tipo)) setTipo("");
    if (ejecutivoTabla && !ejecutivos.includes(ejecutivoTabla)) setEjecutivoTabla("");
  }, [tipos, ejecutivos, tipo, ejecutivoTabla]);

  const visibles = filas.filter(
    (fila) => (!tipo || fila.producto === tipo) && (!ejecutivoTabla || fila.ejecutivo === ejecutivoTabla)
  );

  const filtros = (
    <div className="pd-negocios-filtros pd-no-export">
      <select className="form-select form-select-sm" value={tipo} onChange={(e) => setTipo(e.target.value)} aria-label="Tipo de negocio">
        <option value="">Todos los tipos</option>
        {tipos.map((t) => <option key={t.codigo} value={t.codigo}>{t.nombre}</option>)}
      </select>
      <select className="form-select form-select-sm" value={ejecutivoTabla} onChange={(e) => setEjecutivoTabla(e.target.value)} aria-label="Ejecutivo">
        <option value="">Todos los ejecutivos</option>
        {ejecutivos.map((nombre) => <option key={nombre} value={nombre}>{nombre}</option>)}
      </select>
    </div>
  );

  return (
    <SectionCard title="Detalle de negocios" description={`${visibles.length} de ${filas.length} operaciones`} actions={filtros} exportName={exportName} bodyClassName="">
      {error && <div className="alert alert-danger m-3">{error}</div>}
      {loading ? (
        <LoadingState />
      ) : (
        <div className="pd-table-scroll">
          <table className="pd-table">
            <thead>
              <tr>
                <th>N° OP</th>
                <th>Ejecutivo</th>
                <th>Tipo de negocio</th>
              </tr>
            </thead>
            <tbody>
              {visibles.map((fila, idx) => (
                <tr key={`${fila.operacion}-${fila.producto}-${idx}`}>
                  <td>{fila.operacion}</td>
                  <td className="pd-cell-ejecutivo">{fila.ejecutivo}</td>
                  <td>{fila.producto_nombre}</td>
                </tr>
              ))}
              {!visibles.length && (
                <EmptyRow colSpan={3} text={filas.length ? "No hay negocios con estos filtros." : "Aún no se cargan negocios de este mes."} />
              )}
            </tbody>
          </table>
        </div>
      )}
    </SectionCard>
  );
}
