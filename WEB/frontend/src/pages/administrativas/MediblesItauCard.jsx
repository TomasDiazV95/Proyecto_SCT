import { useEffect, useRef, useState } from "react";
import { addItauMedibles, deleteItauMedible, fetchItauMedibles } from "../../api";
import { LoadingState, SectionCard } from "../../components/productividad/ui";

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
    if (!window.confirm(`¿Quitar "${valorLabel(filtro.columna, filtro.valor)}" (${columnaLabel(filtro.columna)}) de los casos medibles de ${periodo}?`)) {
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
    <SectionCard
      title="Casos medibles"
      className="pd-medibles-card"
      description="Solo los casos con los valores agregados aquí cuentan para el cumplimiento del mes. El resto queda como no medible."
      actions={
        <label className="pd-field pd-medibles-periodo">
          <span className="pd-label">Periodo</span>
          <input
            type="month"
            className="form-control"
            value={periodo}
            onChange={(event) => {
              setPeriodo(event.target.value);
              setForm((prev) => ({ ...prev, valores: [] }));
            }}
          />
        </label>
      }
    >
      {error && <div className="alert alert-danger">{error}</div>}
      {aviso && <div className="alert alert-info">{aviso}</div>}

      <form className="pd-medibles-form" onSubmit={onAdd}>
        <label className="pd-field">
          <span className="pd-label">Columna</span>
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
        </label>
        <div className="pd-field">
          <span className="pd-label" id="medibles-valores-label">Valores</span>
          <div className="position-relative" ref={valoresRef}>
            <button
              type="button"
              className="form-select text-start text-truncate"
              disabled={loading || !sugerencias.length}
              aria-expanded={valoresOpen}
              aria-labelledby="medibles-valores-label"
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
        <button type="submit" className="pd-btn pd-btn-primary" disabled={saving || loading || !form.valores.length}>
          <i className="bi bi-plus-lg" aria-hidden="true" /> {saving ? "Guardando..." : form.valores.length > 1 ? `Agregar ${form.valores.length}` : "Agregar"}
        </button>
      </form>

      {loading ? (
        <LoadingState text="Cargando casos medibles..." />
      ) : grupos.length ? (
        <>
          <dl className="pd-medibles-groups">
            {grupos.map((grupo) => (
              <div className="pd-medibles-group" key={grupo.value}>
                <dt>{grupo.label}</dt>
                <dd>
                  {grupo.filtros.map((filtro) => (
                    <span className="pd-medible-chip" key={`${filtro.columna}-${filtro.valor}`}>
                      {valorLabel(filtro.columna, filtro.valor)}
                      <button
                        type="button"
                        className="pd-medible-remove"
                        disabled={saving}
                        onClick={() => onDelete(filtro)}
                        aria-label={`Quitar ${valorLabel(filtro.columna, filtro.valor)}`}
                        title="Quitar"
                      >
                        <i className="bi bi-x" aria-hidden="true" />
                      </button>
                    </span>
                  ))}
                </dd>
              </div>
            ))}
          </dl>
          <p className="pd-small pd-muted mt-3 mb-0">
            Si agregas valores en más de una columna, el caso debe cumplir todas. Por ejemplo, un canal y un segmento de la lista.
          </p>
        </>
      ) : (
        <div className="alert alert-warning mb-0">
          {periodo} no tiene casos medibles: el cumplimiento de Itaú Vencida no se calcula hasta que agregues al menos un valor.
        </div>
      )}
    </SectionCard>
  );
}
