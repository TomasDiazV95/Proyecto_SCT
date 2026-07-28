function resolveApiBase() {
  const envBase = import.meta.env.VITE_API_URL;
  if (envBase) {
    return envBase;
  }

  return "";
}

const API_BASE = resolveApiBase();

function clearStoredSession() {
  localStorage.removeItem("auth_access_token");
  localStorage.removeItem("auth_user");
  window.dispatchEvent(new Event("auth-session-expired"));
}

async function apiFetch(url, options = {}, retry = true) {
  const token = localStorage.getItem("auth_access_token") || "";
  const headers = new Headers(options.headers || {});
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const res = await fetch(url, { ...options, headers, credentials: "include" });
  if (res.status !== 401 || !retry) {
    return res;
  }

  const refreshRes = await fetch(`${API_BASE}/api/auth/refresh`, { method: "POST", credentials: "include" });
  if (!refreshRes.ok) {
    clearStoredSession();
    throw new Error("Sesion expirada");
  }
  const refreshBody = await refreshRes.json();
  localStorage.setItem("auth_access_token", refreshBody.access_token || "");
  localStorage.setItem("auth_user", JSON.stringify(refreshBody.user || null));
  return apiFetch(url, options, false);
}

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
  const res = await apiFetch(`${API_BASE}/api/sc-tardia/filtros`);
  if (!res.ok) {
    throw new Error("No se pudieron cargar los filtros");
  }
  return res.json();
}

export async function fetchGeneral(filters) {
  const res = await apiFetch(withQuery(`${API_BASE}/api/sc-tardia/productividad/general`, filters));
  if (!res.ok) {
    throw new Error("No se pudo cargar la vista general");
  }
  const body = await res.json();
  return body.data || [];
}

export async function fetchCycle(filters) {
  const res = await apiFetch(withQuery(`${API_BASE}/api/sc-tardia/productividad/ciclo`, filters));
  if (!res.ok) {
    throw new Error("No se pudo cargar la vista por ciclo");
  }
  const body = await res.json();
  return body.data || [];
}

export async function fetchPorscheFilters() {
  const res = await apiFetch(`${API_BASE}/api/filtros`);
  if (!res.ok) {
    throw new Error("No se pudieron cargar los filtros de Porsche");
  }
  return res.json();
}

export async function fetchPorscheDashboard(filters) {
  const res = await apiFetch(withQuery(`${API_BASE}/api/dashboard`, filters));
  if (!res.ok) {
    throw new Error("No se pudo cargar el dashboard de Porsche");
  }
  return res.json();
}

export async function fetchPorscheCuadroContenido(filters) {
  const res = await apiFetch(withQuery(`${API_BASE}/api/cuadro-contenido`, filters));
  if (!res.ok) {
    throw new Error("No se pudo cargar el cuadro de cumplimiento Porsche");
  }
  return res.json();
}

export async function downloadPorscheExcel(mes) {
  const res = await apiFetch(withQuery(`${API_BASE}/api/porsche/export`, { mes }));
  if (!res.ok) {
    throw new Error("No se pudo descargar el Excel de Porsche");
  }
  const blob = await res.blob();
  const disposition = res.headers.get("content-disposition") || "";
  const match = disposition.match(/filename="?([^";]+)"?/i);
  const filename = match?.[1] || `seguimiento_porsche_${mes || "periodo"}.xlsx`;
  return { blob, filename };
}

export async function fetchLaAraucanaFilters(periodo = "") {
  const res = await apiFetch(withQuery(`${API_BASE}/api/la-araucana/filtros`, { periodo }));
  if (!res.ok) {
    throw new Error("No se pudieron cargar los filtros de La Araucana");
  }
  return res.json();
}

export async function fetchLaAraucanaResumen(filters) {
  const res = await apiFetch(withQuery(`${API_BASE}/api/la-araucana/resumen`, filters));
  if (!res.ok) {
    throw new Error("No se pudo cargar el resumen de La Araucana");
  }
  return res.json();
}

export async function downloadLaAraucanaExcel(periodo, tipoCartera = "") {
  const res = await apiFetch(withQuery(`${API_BASE}/api/la-araucana/export`, { periodo, tipo_cartera: tipoCartera }));
  if (!res.ok) {
    throw new Error("No se pudo descargar el Excel de La Araucana");
  }
  const disposition = res.headers.get("content-disposition") || "";
  const match = disposition.match(/filename=\"?([^\"]+)\"?/i);
  const filename = match?.[1] || `la_araucana_detalle_${periodo}.xlsx`;
  return { blob: await res.blob(), filename };
}
export async function fetchScTempranaFilters() {
  const res = await apiFetch(`${API_BASE}/api/sc-temprana/filtros`);
  if (!res.ok) {
    throw new Error("No se pudieron cargar los filtros de SC Temprana");
  }
  return res.json();
}

export async function fetchScTempranaGeneral(filters) {
  const res = await apiFetch(withQuery(`${API_BASE}/api/sc-temprana/productividad/general`, filters));
  if (!res.ok) {
    throw new Error("No se pudo cargar la vista general de SC Temprana");
  }
  const body = await res.json();
  return body.data || [];
}

export async function fetchScTempranaCycle(filters) {
  const res = await apiFetch(withQuery(`${API_BASE}/api/sc-temprana/productividad/ciclo`, filters));
  if (!res.ok) {
    throw new Error("No se pudo cargar la vista por ciclo de SC Temprana");
  }
  const body = await res.json();
  return body.data || [];
}

export async function fetchScTempranaDetail(filters) {
  const res = await apiFetch(withQuery(`${API_BASE}/api/sc-temprana/detalle`, filters));
  if (!res.ok) {
    throw new Error("No se pudo cargar el detalle de SC Temprana");
  }
  return res.json();
}

export async function fetchGmFilters() {
  const res = await apiFetch(`${API_BASE}/api/gm/filtros`);
  if (!res.ok) {
    throw new Error("No se pudieron cargar los filtros de GM");
  }
  return res.json();
}

export async function fetchGmCycle(filters) {
  const res = await apiFetch(withQuery(`${API_BASE}/api/gm/productividad/ciclo`, filters));
  if (!res.ok) {
    throw new Error("No se pudo cargar la productividad de GM");
  }
  const body = await res.json();
  return body.data || [];
}

export async function fetchGmGeneral(filters) {
  const res = await apiFetch(withQuery(`${API_BASE}/api/gm/productividad/general`, filters));
  if (!res.ok) {
    throw new Error("No se pudo cargar la vista general de GM");
  }
  const body = await res.json();
  return body.data || [];
}

export async function fetchBitFilters() {
  const res = await apiFetch(`${API_BASE}/api/bit/filtros`);
  if (!res.ok) {
    throw new Error("No se pudieron cargar los filtros de BIT");
  }
  return res.json();
}

export async function fetchBitGeneral(filters) {
  const res = await apiFetch(withQuery(`${API_BASE}/api/bit/general`, filters));
  if (!res.ok) {
    throw new Error("No se pudo cargar la vista general de BIT");
  }
  return res.json();
}

export async function fetchBitTramos(filters) {
  const res = await apiFetch(withQuery(`${API_BASE}/api/bit/tramos`, filters));
  if (!res.ok) {
    throw new Error("No se pudo cargar la vista por tramo de BIT");
  }
  return res.json();
}

export async function fetchBitDetalle(filters) {
  const res = await apiFetch(withQuery(`${API_BASE}/api/bit/detalle`, filters));
  if (!res.ok) {
    throw new Error("No se pudo cargar el detalle de BIT");
  }
  return res.json();
}

export async function fetchBitCastigoFilters() {
  const res = await apiFetch(`${API_BASE}/api/bit-castigo/filtros`);
  if (!res.ok) {
    throw new Error("No se pudieron cargar los filtros de BIT Castigo");
  }
  return res.json();
}

export async function fetchBitCastigoGeneral(filters) {
  const res = await apiFetch(withQuery(`${API_BASE}/api/bit-castigo/general`, filters));
  if (!res.ok) {
    throw new Error("No se pudo cargar la vista general de BIT Castigo");
  }
  return res.json();
}

// export async function fetchFacturaBitDashboard(periodo = "", scope = "") {
//   const res = await apiFetch(withQuery(`${API_BASE}/api/factura/bit`, { periodo, scope }));
//   const body = await res.json().catch(() => ({}));
//   if (!res.ok) {
//     throw new Error(body?.detail || "No se pudo cargar la simulacion de factura BIT");
//   }
//   return body;
// }

export async function fetchItauCastigoFilters() {
  const res = await apiFetch(`${API_BASE}/api/itau-castigo/filtros`);
  if (!res.ok) {
    throw new Error("No se pudieron cargar los filtros de Itaú Castigo");
  }
  return res.json();
}

export async function fetchItauCastigoGeneral(filters) {
  const res = await apiFetch(withQuery(`${API_BASE}/api/itau-castigo/general`, filters));
  if (!res.ok) {
    throw new Error("No se pudo cargar la vista general de Itaú Castigo");
  }
  return res.json();
}

export async function fetchItauCastigoProducto(filters) {
  const res = await apiFetch(withQuery(`${API_BASE}/api/itau-castigo/producto`, filters));
  if (!res.ok) {
    throw new Error("No se pudo cargar la vista producto de Itaú Castigo");
  }
  return res.json();
}

export async function fetchGmBucket(filters) {
  const res = await apiFetch(withQuery(`${API_BASE}/api/gm/productividad/bucket`, filters));
  if (!res.ok) {
    throw new Error("No se pudo cargar la vista por bucket de GM");
  }
  const body = await res.json();
  return body.data || [];
}

export async function fetchGmDetail(filters) {
  const res = await apiFetch(withQuery(`${API_BASE}/api/gm/detalle`, filters));
  if (!res.ok) {
    throw new Error("No se pudo cargar el detalle de GM");
  }
  const body = await res.json();
  return body.data || [];
}

export async function fetchBenchFilters(filters = {}) {
  const res = await apiFetch(withQuery(`${API_BASE}/api/bench/filtros`, filters));
  if (!res.ok) {
    throw new Error("No se pudieron cargar los filtros de BENCH");
  }
  return res.json();
}

export async function fetchBenchKpi(filters) {
  const res = await apiFetch(withQuery(`${API_BASE}/api/bench/kpi`, filters));
  if (!res.ok) {
    throw new Error("No se pudo cargar el panel BENCH");
  }
  return res.json();
}

export async function downloadGmMonthlyExcel(periodo) {
  const res = await apiFetch(withQuery(`${API_BASE}/api/gm/export`, { periodo }));
  if (!res.ok) {
    throw new Error("No se pudo descargar el Excel de GM");
  }

  const blob = await res.blob();
  const disposition = res.headers.get("content-disposition") || "";
  const match = disposition.match(/filename="?([^";]+)"?/i);
  const filename = match?.[1] || `gm_detalle_${periodo?.slice(0, 7) || "mes"}.xlsx`;

  return { blob, filename };
}

export async function fetchSthFilters() {
  const res = await apiFetch(`${API_BASE}/api/sth/filtros`);
  if (!res.ok) {
    throw new Error("No se pudieron cargar los filtros de STH");
  }
  return res.json();
}

export async function fetchSthGeneral(filters) {
  const res = await apiFetch(withQuery(`${API_BASE}/api/sth/productividad/general`, filters));
  if (!res.ok) {
    throw new Error("No se pudo cargar la vista general de STH");
  }
  const body = await res.json();
  return body.data || [];
}

export async function fetchSthDetail(filters) {
  const res = await apiFetch(withQuery(`${API_BASE}/api/sth/productividad/desglosada`, filters));
  if (!res.ok) {
    throw new Error("No se pudo cargar la vista desglosada de STH");
  }
  const body = await res.json();
  return body.data || [];
}

export async function fetchSthOperationsDetail(filters) {
  const res = await apiFetch(withQuery(`${API_BASE}/api/sth/detalle`, filters));
  if (!res.ok) {
    throw new Error("No se pudo cargar el detalle de STH");
  }
  return res.json();
}

export async function fetchAdminModules() {
  const res = await apiFetch(`${API_BASE}/api/admin/modules`);
  if (!res.ok) {
    throw new Error("No se pudieron cargar los modulos");
  }
  const body = await res.json();
  return body.data || [];
}

export async function fetchAdminUsers() {
  const res = await apiFetch(`${API_BASE}/api/admin/users`);
  if (!res.ok) {
    throw new Error("No se pudieron cargar los usuarios");
  }
  const body = await res.json();
  return body.data || [];
}

export async function createAdminUser(payload) {
  const res = await apiFetch(`${API_BASE}/api/admin/users`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(body?.detail || "No se pudo crear el usuario");
  }
  return body;
}

export async function updateAdminUserModules(userId, moduleCodes) {
  const res = await apiFetch(`${API_BASE}/api/admin/users/${userId}/modules`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payloadOrModules(moduleCodes)),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(body?.detail || "No se pudieron actualizar los modulos");
  }
  return body;
}

function payloadOrModules(value) {
  if (Array.isArray(value)) {
    return { module_codes: value };
  }
  return {
    module_codes: value?.module_codes || [],
  };
}

export async function updateAdminUserStatus(userId, isActive) {
  const res = await apiFetch(`${API_BASE}/api/admin/users/${userId}/status`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ is_active: isActive }),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(body?.detail || "No se pudo actualizar el estado");
  }
  return body;
}

export async function fetchItauAdministrativasPeriodos() {
  const res = await apiFetch(`${API_BASE}/api/administrativas/itau/periodos`);
  if (!res.ok) {
    throw new Error("No se pudieron cargar los periodos de Itaú");
  }
  return res.json();
}

async function downloadAdministrativasExcel(url, fallbackFilename) {
  const res = await apiFetch(url);
  const body = res.ok ? null : await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(body?.detail || "No se pudo descargar el archivo");
  }
  const disposition = res.headers.get("content-disposition") || "";
  const match = disposition.match(/filename="?([^";]+)"?/i);
  const filename = match?.[1] || fallbackFilename;
  return { blob: await res.blob(), filename };
}

export async function downloadItauCuotasVencida(periodo) {
  return downloadAdministrativasExcel(
    withQuery(`${API_BASE}/api/administrativas/itau/cuotas/export`, { periodo }),
    `itau_cuotas_vencida_${periodo || "periodo"}.xlsx`
  );
}

export async function downloadItauAsignacionVencida(periodo) {
  return downloadAdministrativasExcel(
    withQuery(`${API_BASE}/api/administrativas/itau/asignacion/export`, { periodo }),
    `itau_asignacion_vencida_${periodo || "periodo"}.xlsx`
  );
}

export async function downloadItauCuotasPagadas(periodo) {
  return downloadAdministrativasExcel(
    withQuery(`${API_BASE}/api/administrativas/itau/cuotas-pagadas/export`, { periodo }),
    `itau_cuotas_pagadas_${periodo || "periodo"}.xlsx`
  );
}
