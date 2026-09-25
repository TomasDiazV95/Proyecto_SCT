import { useEffect, useRef, useState } from "react";
import { addItauMedibles, deleteItauMedible, fetchItauMedibles } from "../../api";

const COLUMNAS = [
  { value: "DETALLE_MARCA", label: "Detalle marca" },
  { value: "CANAL", label: "Canal" },
  { value: "PRODUCTO", label: "Producto" },
  { value: "SEGMENTO", label: "Segmento" },
  { value: "FASE_PROY_MAX", label: "Fase" },
];

function valorLabel(columna, valor) {
  return columna === "FASE_PROY_MAX" ? `Fase ${valor}` : valor;
}

function currentPeriodo() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

function columnaLabel(value) {
  return COLUMNAS.find((item) => item.value === value)?.label || value;
}

export default function MediblesItauCard() {
  const [periodo, setPeriodo] = useState(currentPeriodo());
  const [data, setData] = useState({ filtros: [], valores: {}, periodos_configurados: [] });
  const [form, setForm] = useState({ columna: "DETALLE_MARCA", valores: [] });
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [aviso, setAviso] = useState("");
  const [valoresOpen, setValoresOpen] = useState(false);
  const valoresRef = useRef(null);

  useEffect(() => {
    if (!valoresOpen) {
      return undefined;
    }
    function onClickOutside(event) {
      if (valoresRef.current && !valoresRef.current.contains(event.target)) {
        setValoresOpen(false);
      }
    }
    function onKeyDown(event) {
      if (event.key === "Escape") {
        setValoresOpen(false);
      }
    }
    document.addEventListener("mousedown", onClickOutside);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onClickOutside);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [valoresOpen]);

  useEffect(() => {
    if (!/^\d{4}-\d{2}$/.test(periodo)) {
      return;
    }
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError("");
      try {
        const body = await fetchItauMedibles(periodo);
        if (!cancelled) {
          setData(body);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err.message);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [periodo]);

  async function onAdd(event) {
    event.preventDefault();
    if (!form.valores.length) {
      return;
    }
    setSaving(true);
    setError("");
    setAviso("");
    try {
      const body = await addItauMedibles({ periodo, columna: form.columna, valores: form.valores });
      setData(body);
      setForm((prev) => ({ ...prev, valores: [] }));
      setValoresOpen(false);
      if (body.ya_existian?.length) {
        setAviso(`Ya estaban agregados: ${body.ya_existian.map((valor) => valorLabel(form.columna, valor)).join(", ")}.`);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function onDelete(filtro) {
    if (!window.confirm(`¿Eliminar "${valorLabel(filtro.columna, filtro.valor)}" (${columnaLabel(filtro.columna)}) de ${periodo}?`)) {
      return;
    }
    setSaving(true);
    setError("");
    setAviso("");
    try {
      const body = await deleteItauMedible({ periodo, ...filtro });
      setData(body);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  // Valores de la contención para la columna elegida, sin los que ya están agregados en el periodo.
  const agregados = new Set(
    data.filtros.filter((filtro) => filtro.columna === form.columna).map((filtro) => filtro.valor.toUpperCase())
  );
  const sugerencias = (data.valores?.[form.columna] || []).filter((valor) => !agregados.has(valor.toUpperCase()));

  function toggleValor(valor) {
    setForm((prev) => ({
      ...prev,
      valores: prev.valores.includes(valor) ? prev.valores.filter((item) => item !== valor) : [...prev.valores, valor],
    }));
  }

  const todosSeleccionados = sugerencias.length > 0 && sugerencias.every((valor) => form.valores.includes(valor));
  let resumenSeleccion = "Selecciona uno o más valores";
  if (!sugerencias.length) {
    resumenSeleccion = "Sin valores disponibles en la contención";
  } else if (form.valores.length > 2) {
    resumenSeleccion = `${form.valores.length} valores seleccionados`;
  } else if (form.valores.length) {
    resumenSeleccion = form.valores.map((valor) => valorLabel(form.columna, valor)).join(", ");
  }

  const grupos = COLUMNAS.map((columna) => ({
    ...columna,
    filtros: data.filtros.filter((filtro) => filtro.columna === columna.value),
  })).filter((grupo) => grupo.filtros.length);

  return (
    <div className="card shadow-sm module-card">
      <div className="card-body p-4">
        <div className="d-flex justify-content-between align-items-start flex-wrap gap-3 mb-3">
          <div>
            <h2 className="h5 mb-1">Casos medibles Itaú Vencida</h2>
            <p className="text-muted mb-0">
              Solo los casos que tengan los valores agregados aquí cuentan para el cumplimiento del periodo. Lo que no esté agregado queda como no medible.
            </p>
          </div>
          <div>
            <label className="form-label mb-1" htmlFor="medibles-periodo">Periodo</label>
            <input
              id="medibles-periodo"
              type="month"
              className="form-control"
              value={periodo}
              onChange={(event) => {
                setPeriodo(event.target.value);
                setForm((prev) => ({ ...prev, valores: [] }));
              }}
            />
          </div>
        </div>

        {error && <div className="alert alert-danger py-2">{error}</div>}
        {aviso && <div className="alert alert-info py-2">{aviso}</div>}

        <form className="row g-2 align-items-end mb-4" onSubmit={onAdd}>
          <div className="col-12 col-md-3">
            <label className="form-label mb-1">Columna</label>
            <select
              className="form-select"
              value={form.columna}
              onChange={(event) => {
                setForm({ columna: event.target.value, valores: [] });
                setValoresOpen(false);
              }}
            >
              {COLUMNAS.map((item) => (
                <option key={item.value} value={item.value}>{item.label}</option>
              ))}
            </select>
          </div>
          <div className="col-12 col-md-7">
            <label className="form-label mb-1">Valores</label>
            <div className="position-relative" ref={valoresRef}>
              <button
                type="button"
                className="form-select text-start text-truncate"
                disabled={loading || !sugerencias.length}
                aria-expanded={valoresOpen}
                onClick={() => setValoresOpen((open) => !open)}
              >
                {resumenSeleccion}
              </button>
              {valoresOpen && (
                <div className="medibles-multi-panel shadow">
                  <label className="medibles-multi-option medibles-multi-all">
                    <input
                      type="checkbox"
                      className="form-check-input"
                      checked={todosSeleccionados}
                      onChange={() => setForm((prev) => ({ ...prev, valores: todosSeleccionados ? [] : [...sugerencias] }))}
                    />
                    Seleccionar todos
                  </label>
                  {sugerencias.map((valor) => (
                    <label key={valor} className="medibles-multi-option">
                      <input
                        type="checkbox"
                        className="form-check-input"
                        checked={form.valores.includes(valor)}
                        onChange={() => toggleValor(valor)}
                      />
                      {valorLabel(form.columna, valor)}
                    </label>
                  ))}
                </div>
              )}
            </div>
          </div>
          <div className="col-12 col-md-2 d-grid">
            <button type="submit" className="btn btn-info" disabled={saving || loading || !form.valores.length}>
              {saving ? "Guardando..." : form.valores.length > 1 ? `Agregar (${form.valores.length})` : "Agregar"}
            </button>
          </div>
        </form>

        {loading ? (
          <div className="text-muted">Cargando...</div>
        ) : grupos.length ? (
          <div className="table-responsive">
            <table className="table table-sm align-middle mb-0">
              <thead>
                <tr>
                  <th>Columna</th>
                  <th>Valor medible</th>
                  <th className="text-end" />
                </tr>
              </thead>
              <tbody>
                {grupos.flatMap((grupo) =>
                  grupo.filtros.map((filtro) => (
                    <tr key={`${filtro.columna}-${filtro.valor}`}>
                      <td>{grupo.label}</td>
                      <td>{valorLabel(filtro.columna, filtro.valor)}</td>
                      <td className="text-end">
                        <button type="button" className="btn btn-sm btn-outline-danger" disabled={saving} onClick={() => onDelete(filtro)}>
                          Eliminar
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
            <div className="small text-muted mt-2">
              Si agregas valores en más de una columna, el caso debe cumplir todas (por ejemplo, un canal y un segmento de la lista).
            </div>
          </div>
        ) : (
          <div className="alert alert-warning mb-0">
            {periodo} no tiene casos medibles configurados: no se calcula cumplimiento hasta agregar al menos un valor.
          </div>
        )}
      </div>
    </div>
  );
}
