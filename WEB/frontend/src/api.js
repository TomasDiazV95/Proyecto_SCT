const API_BASE = import.meta.env.VITE_API_URL || `${window.location.protocol}//${window.location.hostname}:8000`;

function withQuery(url, params = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      query.set(key, value);
    }
  });

  const qs = query.toString();
  return qs ? `${url}?${qs}` : url;
}

export async function fetchFilters() {
  const res = await fetch(`${API_BASE}/api/sc-tardia/filtros`);
  if (!res.ok) {
    throw new Error("No se pudieron cargar los filtros");
  }
  return res.json();
}

export async function fetchGeneral(filters) {
  const res = await fetch(withQuery(`${API_BASE}/api/sc-tardia/productividad/general`, filters));
  if (!res.ok) {
    throw new Error("No se pudo cargar la vista general");
  }
  const body = await res.json();
  return body.data || [];
}

export async function fetchCycle(filters) {
  const res = await fetch(withQuery(`${API_BASE}/api/sc-tardia/productividad/ciclo`, filters));
  if (!res.ok) {
    throw new Error("No se pudo cargar la vista por ciclo");
  }
  const body = await res.json();
  return body.data || [];
}

export async function fetchPorscheFilters() {
  const res = await fetch(`${API_BASE}/api/filtros`);
  if (!res.ok) {
    throw new Error("No se pudieron cargar los filtros de Porsche");
  }
  return res.json();
}

export async function fetchPorscheDashboard(filters) {
  const res = await fetch(withQuery(`${API_BASE}/api/dashboard`, filters));
  if (!res.ok) {
    throw new Error("No se pudo cargar el dashboard de Porsche");
  }
  return res.json();
}
export async function fetchScTempranaFilters() {
  const res = await fetch(`${API_BASE}/api/sc-temprana/filtros`);
  if (!res.ok) {
    throw new Error("No se pudieron cargar los filtros de SC Temprana");
  }
  return res.json();
}

export async function fetchScTempranaGeneral(filters) {
  const res = await fetch(withQuery(`${API_BASE}/api/sc-temprana/productividad/general`, filters));
  if (!res.ok) {
    throw new Error("No se pudo cargar la vista general de SC Temprana");
  }
  const body = await res.json();
  return body.data || [];
}

export async function fetchScTempranaCycle(filters) {
  const res = await fetch(withQuery(`${API_BASE}/api/sc-temprana/productividad/ciclo`, filters));
  if (!res.ok) {
    throw new Error("No se pudo cargar la vista por ciclo de SC Temprana");
  }
  const body = await res.json();
  return body.data || [];
}