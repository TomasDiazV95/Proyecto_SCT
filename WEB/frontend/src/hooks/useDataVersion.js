import { useSyncExternalStore } from "react";
import { fetchDataVersion } from "../api";

// Cada cuanto se pregunta al backend si cambiaron los datos (solo con la pestaña visible).
const INTERVALO_MS = 5000;

// Un solo sondeo compartido por todas las paginas y tarjetas montadas.
let version = 0;
let versionServidor = null;
let timer = null;
const suscriptores = new Set();

async function revisar() {
  if (document.hidden) return;
  try {
    const actual = await fetchDataVersion();
    // La primera respuesta solo fija la base: no hay nada que recargar.
    if (versionServidor !== null && actual !== versionServidor) {
      version += 1;
      suscriptores.forEach((avisar) => avisar());
    }
    versionServidor = actual;
  } catch {
    // Sin red o sesion vencida: se reintenta en el proximo ciclo.
  }
}

function alVolverAPestana() {
  if (!document.hidden) revisar();
}

function suscribir(avisar) {
  suscriptores.add(avisar);
  if (suscriptores.size === 1) {
    revisar();
    timer = setInterval(revisar, INTERVALO_MS);
    document.addEventListener("visibilitychange", alVolverAPestana);
  }
  return () => {
    suscriptores.delete(avisar);
    if (!suscriptores.size) {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", alVolverAPestana);
    }
  };
}

/** Numero que sube cada vez que cambian los datos en la base. Agregarlo a las dependencias
 * de los efectos que piden datos hace que la pagina se recargue sola, sin perder los filtros. */
export default function useDataVersion() {
  return useSyncExternalStore(suscribir, () => version);
}

/** Fecha a mostrar cuando se recarga la lista de fechas: si se estaba en la mas reciente
 * (o no habia ninguna elegida) pasa a la nueva mas reciente; si se eligio otra, se mantiene. */
export function fechaVigente(actual, anteriores, nuevas) {
  const lista = nuevas || [];
  if (!actual || !lista.includes(actual) || actual === anteriores?.[0]) {
    return lista[0] || "";
  }
  return actual;
}

/** Valor elegido si sigue disponible en la nueva lista; si no, el valor por defecto. */
export function mantenerSiExiste(actual, nuevas, porDefecto = "") {
  return actual && (nuevas || []).includes(actual) ? actual : porDefecto;
}
