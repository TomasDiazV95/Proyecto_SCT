import { useEffect, useState } from "react";
import { EjecutivoDetalleFilter, EmptyRow, LoadingState, SectionCard, Segmented } from "./ui";
import useDataVersion from "../../hooks/useDataVersion";

function formatPesos(value) {
  return `$${new Intl.NumberFormat("es-CL", { maximumFractionDigits: 0 }).format(Number(value || 0))}`;
}

const PRODUCTO_LABEL = { CONSUMO: "Consumo", HIPOTECARIO: "Hipotecario" };

// Pestaña Negocios de Itaú Vencida / Vigente: operaciones renegociadas en el mes (RENE_MES = 1 en la contención),
// asignadas al mismo ejecutivo que el resumen. fetcher: fetchItauVencidaNegocios o fetchItauVigenteNegocios.
// compacto: el resumen muestra solo Ejecutivo y Renegociados (PHOENIX incluido).
// Dentro de la tarjeta, sub-pestañas Resumen (por ejecutivo) y Detalle (por operación).
// vistaFija ("resumen" | "detalle"): la pagina lo maneja con sus propias pestañas (como SC Tardia) y se oculta el selector.
export default function ItauNegociosCard({ fetcher, fechaCarga, ejecutivo, exportName, universo, compacto = false, vistaFija }) {
  const dataVersion = useDataVersion();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [vistaInterna, setVista] = useState("resumen");
  const vista = vistaFija || vistaInterna;
  const [ejecutivoTabla, setEjecutivoTabla] = useState("");

  useEffect(() => {
    if (!fechaCarga) {
      return undefined;
    }
    let vigente = true;
    setLoading(true);
    setError("");
    fetcher({ fecha_carga: fechaCarga, ejecutivo })
      .then((body) => vigente && setData(body))
      .catch((err) => vigente && setError(err.message))
      .finally(() => vigente && setLoading(false));
    return () => {
      vigente = false;
    };
  }, [fetcher, fechaCarga, ejecutivo, dataVersion]);

  const rows = data?.rows || [];
  const detalleTodo = data?.detalle || [];
  const detalle = detalleTodo.filter((row) => !ejecutivoTabla || row.ejecutivo === ejecutivoTabla);
  const sinNegocios = `No hay renegociaciones en ${universo} a esta fecha.`;

  const selector = vistaFija ? null : (
    <Segmented
      value={vista}
      onChange={setVista}
      options={[
        { value: "resumen", label: "Resumen" },
        { value: "detalle", label: "Detalle" },
      ]}
    />
  );

  if (vista === "resumen") {
    return (
      <SectionCard actions={selector} exportName={exportName} bodyClassName="">
        {error && <div className="alert alert-danger m-3">{error}</div>}
        {loading ? (
          <LoadingState />
        ) : (
          <div className="pd-table-scroll">
            <table className="pd-table">
              <thead>
                <tr>
                  <th>Ejecutivo</th>
                  <th className="pd-num pd-th-key">{compacto ? "Renegociación" : "Negocios"}</th>
                  {!compacto && <th className="pd-num">RUT</th>}
                  {!compacto && <th className="pd-num">Saldo renegociado</th>}
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.ejecutivo}>
                    <td className="pd-cell-ejecutivo">{row.ejecutivo}</td>
                    <td className="pd-num pd-cell-strong">{row.negocios}</td>
                    {!compacto && <td className="pd-num">{row.ruts}</td>}
                    {!compacto && <td className="pd-num">{formatPesos(row.saldo_ini)}</td>}
                  </tr>
                ))}
                {!rows.length && <EmptyRow colSpan={compacto ? 2 : 4} text={sinNegocios} />}
                {rows.length > 0 && data?.total && (
                  <tr className="pd-row-total">
                    <td>Total general</td>
                    <td className="pd-num">{data.total.negocios}</td>
                    {!compacto && <td className="pd-num">{data.total.ruts}</td>}
                    {!compacto && <td className="pd-num">{formatPesos(data.total.saldo_ini)}</td>}
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>
    );
  }

  return (
        <SectionCard
          title={vistaFija ? "Detalle de negocios" : undefined}
          actions={
            <>
              <EjecutivoDetalleFilter filas={detalleTodo} value={ejecutivoTabla} onChange={setEjecutivoTabla} />
              {selector}
            </>
          }
          exportName={vistaFija ? exportName : exportName ? `${exportName}-detalle` : undefined}
          bodyClassName=""
        >
          {error && <div className="alert alert-danger m-3">{error}</div>}
          {loading ? (
            <LoadingState />
          ) : (
          <div className="pd-table-scroll">
            <table className="pd-table pd-table-compact pd-table-plain">
              <thead>
                <tr>
                  <th>Ejecutivo</th>
                  <th>RUT</th>
                  <th>Cliente</th>
                  <th>Operación</th>
                  <th>Producto</th>
                  <th className="pd-center">Fase</th>
                  <th className="pd-num">Saldo inicial</th>
                </tr>
              </thead>
              <tbody>
                {detalle.map((row, idx) => (
                  <tr key={`${row.operacion}-${idx}`}>
                    <td className="pd-cell-ejecutivo">{row.ejecutivo}</td>
                    <td>{row.rut}</td>
                    <td>{row.nombre}</td>
                    <td>{row.operacion}</td>
                    <td>{PRODUCTO_LABEL[row.producto] || row.producto}</td>
                    <td className="pd-center">{row.fase}</td>
                    <td className="pd-num">{formatPesos(row.saldo_ini)}</td>
                  </tr>
                ))}
                {!detalle.length && <EmptyRow colSpan={7} text={sinNegocios} />}
              </tbody>
            </table>
          </div>
          )}
        </SectionCard>
  );
}
