import { useEffect, useState } from "react";

// Piezas compartidas por los simuladores (renegociacion y Veritus).

// ---- Entrada de numeros al estilo chileno: miles con punto y decimales con coma ----
export function soloDigitos(texto) {
  return String(texto ?? "").replace(/\D/g, "");
}

export function miles(texto) {
  const digitos = soloDigitos(texto);
  return digitos ? new Intl.NumberFormat("es-CL").format(Number(digitos)) : "";
}

// Acepta "1,99" o "1.99"; deja escribir la coma final ("1,"). maxDecimales limita los digitos tras la coma.
export function limpiarDecimal(texto, maxDecimales = Infinity) {
  const limpio = String(texto ?? "").replace(/[^\d.,]/g, "").replace(".", ",");
  const [entero, ...resto] = limpio.split(",");
  return resto.length ? `${entero},${resto.join("").replace(/,/g, "").slice(0, maxDecimales)}` : entero;
}

export function decimal(texto) {
  const n = Number(String(texto ?? "").replace(",", "."));
  return Number.isFinite(n) ? n : 0;
}

export function coma(valor) {
  return String(valor).replace(".", ",");
}

export function plural(n, uno, varios) {
  return `${n} ${n === 1 ? uno : varios}`;
}

// Copia al portapapeles; en http (acceso por IP de red) el API moderno no existe y se usa el metodo clasico.
export async function copiarTexto(texto) {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(texto);
    return;
  }
  const area = document.createElement("textarea");
  area.value = texto;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.appendChild(area);
  area.select();
  const ok = document.execCommand("copy");
  area.remove();
  if (!ok) {
    throw new Error("sin portapapeles");
  }
}

// En pantallas angostas, la barra fija con la cuota se muestra mientras la ficha no esta a la vista.
export function useVisibleEnPantalla(ref) {
  const [visible, setVisible] = useState(true);
  useEffect(() => {
    const nodo = ref.current;
    if (!nodo || typeof IntersectionObserver === "undefined") {
      return undefined;
    }
    const obs = new IntersectionObserver(([entrada]) => setVisible(entrada.isIntersecting), { threshold: 0.25 });
    obs.observe(nodo);
    return () => obs.disconnect();
  }, [ref]);
  return visible;
}

export function Seccion({ numero, titulo, extra, children }) {
  return (
    <section className="sim-seccion">
      <div className="sim-seccion-head">
        <span className="sim-num" aria-hidden="true">{numero}</span>
        <h2 className="sim-seccion-titulo">{titulo}</h2>
        {extra && <span className="sim-seccion-extra">{extra}</span>}
      </div>
      {children}
    </section>
  );
}

export function Campo({ label, sufijo, prefijo, hint, error, children }) {
  return (
    <label className={`sim-campo${error ? " is-invalid" : ""}`}>
      <span className="sim-label">{label}</span>
      <span className="sim-input">
        {prefijo && <span className="sim-input-pre">{prefijo}</span>}
        {children}
        {sufijo && <span className="sim-input-suf">{sufijo}</span>}
      </span>
      {error ? <span className="sim-error">{error}</span> : hint && <span className="sim-hint">{hint}</span>}
    </label>
  );
}
