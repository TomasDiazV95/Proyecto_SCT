import { useEffect, useState } from "react";
import { replaceItauMedibles, sugerirItauMedibles } from "../../api";
import { Segmented } from "../../components/productividad/ui";

const PRODUCTOS = [
  { value: "CONSUMO", label: "Consumo" },
  { value: "HIPOTECARIO", label: "Hipotecario" },
];

// Columnas que se buscan. El canal y las fases son fijos y llegan en `fijos`.
const COLUMNAS = [
  { value: "DETALLE_MARCA", label: "Detalle marca" },
  { value: "PRODUCTO", label: "Producto" },
  { value: "SEGMENTO", label: "Segmento" },
];

const FIJOS = [
  { value: "CANAL", label: "Canal" },
  { value: "FASE_PROY_MAX", label: "Fase" },
];

const TOTAL = "total";

function faseLabel(fase) {
  return fase ? `Fase ${fase}` : "Total";
}

const UNIDADES = [
  { value: "millones", label: "Millones" },
  { value: "pesos", label: "Pesos" },
];

function formatDate(value) {
  const [year, month, day] = String(value || "").slice(0, 10).split("-");
  return year && month && day ? `${day}-${month}-${year}` : value;
}

// Formato chileno: punto de miles y coma decimal ("4.964,5").
function parseMonto(text) {
  const limpio = String(text || "").replace(/[$\s]/g, "").replace(/\./g, "").replace(",", ".");
  if (!limpio) {
    return null;
  }
  const numero = Number(limpio);
  return Number.isFinite(numero) && numero >= 0 ? numero : NaN;
}

function formatMonto(pesos, unidad) {
  if (pesos === null || pesos === undefined) {
    return "—";
  }
  if (unidad === "millones") {
    return `${new Intl.NumberFormat("es-CL", { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(pesos / 1e6)} M`;
  }
  return `$${new Intl.NumberFormat("es-CL", { maximumFractionDigits: 0 }).format(pesos)}`;
}

// Busca que valores de la contencion dejan el saldo inicial igual al monto asignado que informa el banco.
export default function MediblesBuscador({ periodo, cargas, fasesMeta, fijos, onApplied }) {
  const [fecha, setFecha] = useState("");
  const [unidad, setUnidad] = useState("millones");
  const [montos, setMontos] = useState({});
  const [resultado, setResultado] = useState(null);
  const [buscando, setBuscando] = useState(false);
  const [aplicando, setAplicando] = useState(false);
  const [error, setError] = useState("");
  const [aviso, setAviso] = useState("");

  useEffect(() => {
    setFecha(cargas[0] || "");
    setMontos({});
    setResultado(null);
    setError("");
    setAviso("");
  }, [periodo, cargas.join(",")]);

  const fases = [...new Set(PRODUCTOS.flatMap((producto) => fasesMeta[producto.value] || []))].sort((a, b) => a - b);

  if (!cargas.length || !fases.length) {
    return (
      <div className="pd-medibles-buscador">
        <h3 className="pd-medibles-buscador-title">Buscar por monto asignado</h3>
        <p className="pd-small pd-muted m-0">
          {cargas.length
            ? `${periodo} no tiene metas cargadas; sin metas no se sabe qué fases se miden.`
            : `${periodo} todavía no tiene cargas de contención Phoenix para comparar.`}
        </p>
      </div>
    );
  }

  function onMonto(producto, fase, value) {
    setMontos((prev) => ({ ...prev, [`${producto}-${fase}`]: value }));
  }

  async function onBuscar(event) {
    event.preventDefault();
    setError("");
    setAviso("");
    const lista = [];
    for (const producto of PRODUCTOS) {
      const filas = (fasesMeta[producto.value] || []).length ? [TOTAL, ...fasesMeta[producto.value]] : [];
      for (const fase of filas) {
        const monto = parseMonto(montos[`${producto.value}-${fase}`]);
        if (Number.isNaN(monto)) {
          setError(`El monto de ${producto.label} (${faseLabel(fase === TOTAL ? null : fase).toLowerCase()}) no es un número válido. Usa coma para los decimales.`);
          return;
        }
        if (monto !== null) {
          lista.push({ producto: producto.value, fase: fase === TOTAL ? null : fase, monto });
        }
      }
    }
    if (!lista.length) {
      setError("Ingresa el monto asignado total de al menos un producto.");
      return;
    }
    setBuscando(true);
    try {
      setResultado(await sugerirItauMedibles({ periodo, fecha_carga: fecha, unidad, montos: lista }));
    } catch (err) {
      setResultado(null);
      setError(err.message);
    } finally {
      setBuscando(false);
    }
  }

  async function onUsar(sugerencia) {
    // El canal y las fases fijos los agrega el backend.
    const filtros = COLUMNAS.flatMap((columna) => (sugerencia.filtros[columna.value] || []).map((valor) => ({ columna: columna.value, valor })));
    if (!window.confirm(`¿Reemplazar los casos medibles de ${periodo} por esta combinación? Los que estén configurados ahora se quitan.`)) {
      return;
    }
    setAplicando(true);
    setError("");
    try {
      onApplied(await replaceItauMedibles({ periodo, filtros }));
      setAviso(`Casos medibles de ${periodo} actualizados.`);
    } catch (err) {
      setError(err.message);
    } finally {
      setAplicando(false);
    }
  }

  return (
    <div className="pd-medibles-buscador">
      <h3 className="pd-medibles-buscador-title">Buscar por monto asignado</h3>
      <p className="pd-small pd-muted">
        Ingresa el monto asignado de Phoenix que informa el banco: basta el total de cada producto. Se prueban todas las combinaciones
        de detalle marca, producto y segmento, siempre en {fijos.filter((fijo) => fijo.columna === "CANAL").map((fijo) => fijo.valor).join(", ")} y
        las fases medibles, y se muestran las que dejan ese mismo saldo inicial. Si hay más de una, agrega el detalle por fase para afinar.
      </p>

      <form className="pd-medibles-buscador-form" onSubmit={onBuscar}>
        <div className="pd-medibles-buscador-opciones">
          <label className="pd-field">
            <span className="pd-label">Carga de contención</span>
            <select className="form-select" value={fecha} onChange={(event) => { setFecha(event.target.value); setResultado(null); }}>
              {cargas.map((value) => (
                <option key={value} value={value}>{formatDate(value)}</option>
              ))}
            </select>
          </label>
          <div className="pd-field">
            <span className="pd-label">Montos en</span>
            <Segmented value={unidad} onChange={(value) => { setUnidad(value); setResultado(null); }} options={UNIDADES} />
          </div>
        </div>

        <table className="pd-table pd-table-plain pd-table-compact pd-table-static pd-medibles-montos">
          <thead>
            <tr>
              <th>Fase</th>
              {PRODUCTOS.map((producto) => (
                <th key={producto.value}>{producto.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {[TOTAL, ...fases].map((fase) => (
              <tr key={fase} className={fase === TOTAL ? "pd-medibles-montos-total" : undefined}>
                <td className="pd-cell-strong">
                  {fase === TOTAL ? "Total" : `Fase ${fase}`}
                  {fase !== TOTAL && <span className="pd-cell-sub">opcional</span>}
                </td>
                {PRODUCTOS.map((producto) => (
                  <td key={producto.value}>
                    {fase === TOTAL || (fasesMeta[producto.value] || []).includes(fase) ? (
                      <input
                        className="form-control"
                        inputMode="decimal"
                        placeholder={unidad === "millones" ? "0,0" : "0"}
                        value={montos[`${producto.value}-${fase}`] || ""}
                        onChange={(event) => onMonto(producto.value, fase, event.target.value)}
                        aria-label={`Monto asignado ${producto.label} ${fase === TOTAL ? "total" : `fase ${fase}`}`}
                      />
                    ) : (
                      <span className="pd-cell-muted">Sin meta</span>
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>

        <button type="submit" className="pd-btn pd-btn-primary" disabled={buscando || aplicando}>
          <i className="bi bi-search" aria-hidden="true" /> {buscando ? "Buscando..." : "Buscar medibles"}
        </button>
      </form>

      {error && <div className="alert alert-danger mt-3 mb-0">{error}</div>}
      {aviso && <div className="alert alert-success mt-3 mb-0">{aviso}</div>}

      {resultado && (
        <div className="pd-medibles-sugerencias">
          <p className="pd-small pd-muted">
            {resultado.sugerencias.some((item) => item.coincide)
              ? "Estas combinaciones coinciden con los montos ingresados, o son las más cercanas."
              : "Ninguna combinación coincide con los montos ingresados. Estas son las más cercanas; revisa la carga elegida y los montos."}
          </p>
          {resultado.sugerencias.map((sugerencia, idx) => {
            const restringidas = COLUMNAS.filter((columna) => sugerencia.filtros[columna.value]);
            return (
              <article className={`pd-medibles-sugerencia${sugerencia.coincide ? " is-match" : ""}`} key={idx}>
                <header className="pd-medibles-sugerencia-head">
                  <span className={`pd-status ${sugerencia.coincide ? "pd-status-success" : "pd-status-warning"}`}>
                    {sugerencia.coincide ? "Coincide" : `Diferencia de ${formatMonto(sugerencia.diferencia_total, resultado.unidad)}`}
                  </span>
                  <button type="button" className="pd-btn pd-btn-secondary pd-btn-sm" disabled={aplicando} onClick={() => onUsar(sugerencia)}>
                    <i className="bi bi-check2" aria-hidden="true" /> Usar estos medibles
                  </button>
                </header>

                <dl className="pd-medibles-groups">
                  {restringidas.map((columna) => (
                    <div className="pd-medibles-group" key={columna.value}>
                      <dt>{columna.label}</dt>
                      <dd>
                        {sugerencia.filtros[columna.value].map((valor) => (
                          <span className="pd-medible-chip" key={valor}>{valor}</span>
                        ))}
                      </dd>
                    </div>
                  ))}
                  {FIJOS.map((columna) => (
                    <div className="pd-medibles-group" key={columna.value}>
                      <dt>{columna.label}</dt>
                      <dd>
                        {resultado.fijos.filter((fijo) => fijo.columna === columna.value).map((fijo) => (
                          <span className="pd-medible-chip is-fijo" key={fijo.valor} title="Fijo: se mide todos los meses">
                            {columna.value === "FASE_PROY_MAX" ? `Fase ${fijo.valor}` : fijo.valor}
                          </span>
                        ))}
                      </dd>
                    </div>
                  ))}
                </dl>
                {!restringidas.length && (
                  <p className="pd-small pd-muted">Sin más filtros: todos los casos de ese canal y esas fases son medibles.</p>
                )}

                <table className="pd-table pd-table-plain pd-table-compact pd-table-static">
                  <thead>
                    <tr>
                      <th>Producto</th>
                      <th>Fase</th>
                      <th className="pd-num">Ingresado</th>
                      <th className="pd-num">Saldo inicial</th>
                      <th className="pd-num">Diferencia</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sugerencia.celdas.map((celda) => (
                      <tr key={`${celda.producto}-${celda.fase}`} className={celda.fase ? undefined : "pd-row-subtotal"}>
                        <td>{PRODUCTOS.find((producto) => producto.value === celda.producto)?.label || celda.producto}</td>
                        <td>{faseLabel(celda.fase)}</td>
                        <td className="pd-num">{formatMonto(celda.ingresado, resultado.unidad)}</td>
                        <td className="pd-num">{formatMonto(celda.calculado, resultado.unidad)}</td>
                        <td className="pd-num">{formatMonto(celda.diferencia, resultado.unidad)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
