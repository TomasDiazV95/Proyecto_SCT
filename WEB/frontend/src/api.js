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

export async function fetchPorscheCuadroContenido(filters) {
  const res = await fetch(withQuery(`${API_BASE}/api/cuadro-contenido`, filters));
  if (!res.ok) {
    throw new Error("No se pudo cargar el cuadro de cumplimiento Porsche");
  }
  return res.json();
}

export async function fetchLaAraucanaFilters(periodo = "") {
  const res = await fetch(withQuery(`${API_BASE}/api/la-araucana/filtros`, { periodo }));
  if (!res.ok) {
    throw new Error("No se pudieron cargar los filtros de La Araucana");
  }
  return res.json();
}

export async function fetchLaAraucanaResumen(filters) {
  const res = await fetch(withQuery(`${API_BASE}/api/la-araucana/resumen`, filters));
  if (!res.ok) {
    throw new Error("No se pudo cargar el resumen de La Araucana");
  }
  return res.json();
}

export async function downloadLaAraucanaExcel(periodo, tipoCartera = "") {
  const res = await fetch(withQuery(`${API_BASE}/api/la-araucana/export`, { periodo, tipo_cartera: tipoCartera }));
  if (!res.ok) {
    throw new Error("No se pudo descargar el Excel de La Araucana");
  }
  const disposition = res.headers.get("content-disposition") || "";
  const match = disposition.match(/filename=\"?([^\"]+)\"?/i);
  const filename = match?.[1] || `la_araucana_detalle_${periodo}.xlsx`;
  return { blob: await res.blob(), filename };
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

export async function fetchGmFilters() {
  const res = await fetch(`${API_BASE}/api/gm/filtros`);
  if (!res.ok) {
    throw new Error("No se pudieron cargar los filtros de GM");
  }
  return res.json();
}

export async function fetchGmCycle(filters) {
  const res = await fetch(withQuery(`${API_BASE}/api/gm/productividad/ciclo`, filters));
  if (!res.ok) {
    throw new Error("No se pudo cargar la productividad de GM");
  }
  const body = await res.json();
  return body.data || [];
}

export async function fetchGmGeneral(filters) {
  const res = await fetch(withQuery(`${API_BASE}/api/gm/productividad/general`, filters));
  if (!res.ok) {
    throw new Error("No se pudo cargar la vista general de GM");
  }
  const body = await res.json();
  return body.data || [];
}

export async function fetchBitFilters() {
  const res = await fetch(`${API_BASE}/api/bit/filtros`);
  if (!res.ok) {
    throw new Error("No se pudieron cargar los filtros de BIT");
  }
  return res.json();
}

export async function fetchBitGeneral(filters) {
  const res = await fetch(withQuery(`${API_BASE}/api/bit/general`, filters));
  if (!res.ok) {
    throw new Error("No se pudo cargar la vista general de BIT");
  }
  return res.json();
}

export async function fetchBitTramos(filters) {
  const res = await fetch(withQuery(`${API_BASE}/api/bit/tramos`, filters));
  if (!res.ok) {
    throw new Error("No se pudo cargar la vista por tramo de BIT");
  }
  return res.json();
}

export async function fetchBitDetalle(filters) {
  const res = await fetch(withQuery(`${API_BASE}/api/bit/detalle`, filters));
  if (!res.ok) {
    throw new Error("No se pudo cargar el detalle de BIT");
  }
  return res.json();
}

export async function fetchGmBucket(filters) {
  const res = await fetch(withQuery(`${API_BASE}/api/gm/productividad/bucket`, filters));
  if (!res.ok) {
    throw new Error("No se pudo cargar la vista por bucket de GM");
  }
  const body = await res.json();
  return body.data || [];
}

export async function downloadGmMonthlyExcel(periodo) {
  const res = await fetch(withQuery(`${API_BASE}/api/gm/export`, { periodo }));
  if (!res.ok) {
    throw new Error("No se pudo descargar el Excel de GM");
  }

  const blob = await res.blob();
  const disposition = res.headers.get("content-disposition") || "";
  const match = disposition.match(/filename="?([^";]+)"?/i);
  const filename = match?.[1] || `gm_detalle_${periodo?.slice(0, 7) || "mes"}.xlsx`;

  return { blob, filename };
}
