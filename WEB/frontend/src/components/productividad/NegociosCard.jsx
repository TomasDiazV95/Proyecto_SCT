import { useEffect, useState } from "react";
import { fetchNegociosConteo } from "../../api";
import { EmptyRow, LoadingState, SectionCard } from "./ui";

// Pestaña Negocios de una productividad: negocios cerrados del mes por ejecutivo y producto,
// segun los archivos que suben las administrativas (Panel Administrativo > Negocios).
// modulo: "sc-tardia", "sc-temprana" o "gm".
export default function NegociosCard({ modulo, periodo, ejecutivo, exportName }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!periodo) {
      return undefined;
    }
    let vigente = true;
    setLoading(true);
    setError("");
    fetchNegociosConteo(modulo, { periodo, ejecutivo })
      .then((body) => vigente && setData(body))
      .catch((err) => vigente && setError(err.message))
      .finally(() => vigente && setLoading(false));
    return () => {
      vigente = false;
    };
  }, [modulo, periodo, ejecutivo]);

  const productos = data?.productos || [];
  const filas = data?.filas || [];

  return (
    <SectionCard exportName={exportName} bodyClassName="">
      {error && <div className="alert alert-danger m-3">{error}</div>}
      {loading ? (
        <LoadingState />
      ) : (
        <div className="pd-table-scroll">
          <table className="pd-table">
            <thead>
              <tr>
                <th>Ejecutivo</th>
                {productos.map((producto) => (
                  <th key={producto.codigo} className="pd-num">{producto.nombre}</th>
                ))}
                <th className="pd-num pd-th-key">Total</th>
              </tr>
            </thead>
            <tbody>
              {filas.map((fila) => (
                <tr key={fila.ejecutivo}>
                  <td className="pd-cell-ejecutivo">{fila.ejecutivo}</td>
                  {productos.map((producto) => (
                    <td key={producto.codigo} className="pd-num">{fila.conteos[producto.codigo] || 0}</td>
                  ))}
                  <td className="pd-num pd-cell-strong">{fila.total}</td>
                </tr>
              ))}
              {!filas.length && <EmptyRow colSpan={productos.length + 2} text="Aún no se cargan negocios de este mes." />}
              {filas.length > 0 && (
                <tr className="pd-row-total">
                  <td>Total</td>
                  {productos.map((producto) => (
                    <td key={producto.codigo} className="pd-num">{data.totales[producto.codigo] || 0}</td>
                  ))}
                  <td className="pd-num">{data.total}</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </SectionCard>
  );
}
