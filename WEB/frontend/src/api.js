import { API_BASE, clearStoredSession } from "./apiBase";

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
    throw new Error("Sesión expirada");
  }
  const refreshBody = await refreshRes.json();
  localStorage.setItem("auth_access_token", refreshBody.access_token || "");
  localStorage.setItem("auth_user", JSON.stringify(refreshBody.user || null));
  return apiFetch(url, options, false);
}

export async function fetchDataVersion() {
  const res = await apiFetch(`${API_BASE}/api/datos/version`);
  if (!res.ok) {
    throw new Error("No se pudo consultar la version de los datos");
  }
  const body = await res.json();
  return body.version;
}

function withQuery(url, params = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (Array.isArray(value)) {
      value.forEach((item) => {
        if (item !== undefined && item !== null && item !== "") {
          query.append(key, String(item));
        }
      });
      return;
    }
    if (value !== undefined && value !== null && value !== "") {
      query.set(key, value);
    }
  });

  const qs = query.toString();
  return qs ? `${url}?${qs}` : url;
}

// GET que devuelve el JSON de la respuesta, o lanza Error(mensajeError) si no es 2xx.
async function getJson(url, mensajeError) {
  const res = await apiFetch(url);
  if (!res.ok) {
    throw new Error(mensajeError);
  }
  return res.json();
}

// Igual que getJson, pero devuelve body.data (o [] si no viene).
async function getData(url, mensajeError) {
  const body = await getJson(url, mensajeError);
  return body.data || [];
}

// base: "sc-tardia" (SC Terreno) o "sc-piloto" (SC Piloto, misma productividad con otra cartera).
export async function fetchFilters(periodo = "", zona = "", base = "sc-tardia") {
  return getJson(withQuery(`${API_BASE}/api/${base}/filtros`, { periodo, zona }), "No se pudieron cargar los filtros");
}

export async function fetchGeneral(filters, base = "sc-tardia") {
  return getData(withQuery(`${API_BASE}/api/${base}/productividad/general`, filters), "No se pudo cargar la vista general");
}

export async function fetchCycle(filters, base = "sc-tardia") {
  return getData(withQuery(`${API_BASE}/api/${base}/productividad/ciclo`, filters), "No se pudo cargar la vista por ciclo");
}

export async function fetchScTardiaMetas(filters, base = "sc-tardia") {
  return getData(withQuery(`${API_BASE}/api/${base}/metas`, { periodo: filters.periodo }), "No se pudieron cargar las metas");
}

export async function fetchLaAraucanaFilters(periodo = "") {
  return getJson(withQuery(`${API_BASE}/api/la-araucana/filtros`, { periodo }), "No se pudieron cargar los filtros de La Araucana");
}

export async function fetchLaAraucanaResumen(filters) {
  return getJson(withQuery(`${API_BASE}/api/la-araucana/resumen`, filters), "No se pudo cargar el resumen de La Araucana");
}

export async function fetchLaAraucanaNegocios(filters) {
  return getJson(withQuery(`${API_BASE}/api/la-araucana/negocios`, filters), "No se pudieron cargar los negocios de La Araucana");
}

export async function fetchLaAraucanaDetalle(filters) {
  return getJson(withQuery(`${API_BASE}/api/la-araucana/detalle`, filters), "No se pudo cargar el detalle de La Araucana");
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
export async function fetchScTempranaFilters(periodo = "") {
  return getJson(withQuery(`${API_BASE}/api/sc-temprana/filtros`, { periodo }), "No se pudieron cargar los filtros de SC Temprana");
}

export async function fetchScTempranaCycle(filters) {
  return getData(withQuery(`${API_BASE}/api/sc-temprana/productividad/ciclo`, filters), "No se pudo cargar la vista por ciclo de SC Temprana");
}

export async function fetchScTempranaDetail(filters) {
  return getJson(withQuery(`${API_BASE}/api/sc-temprana/detalle`, filters), "No se pudo cargar el detalle de SC Temprana");
}

export async function fetchGestionesDiariasSctFilters(filters = {}) {
  return getJson(withQuery(`${API_BASE}/api/gestiones-diarias-sct/filtros`, filters), "No se pudieron cargar los filtros de Gestiones Diarias SCT");
}

export async function fetchKpiDiarioFilters(filters = {}) {
  return getJson(withQuery(`${API_BASE}/api/kpi-diario/filtros`, filters), "No se pudieron cargar los filtros de KPI diario");
}

export async function fetchGestionesDiariasSctDetail(filters) {
  return getJson(withQuery(`${API_BASE}/api/gestiones-diarias-sct/detalle`, filters), "No se pudo cargar Gestiones Diarias SCT");
}

export async function fetchGestionesDiariasSctSummary(filters) {
  return getJson(withQuery(`${API_BASE}/api/gestiones-diarias-sct/resumen`, filters), "No se pudo cargar el resumen de Gestiones Diarias SCT");
}

export async function fetchKpiDiarioGeneral(filters) {
  return getData(withQuery(`${API_BASE}/api/kpi-diario/productividad/general`, filters), "No se pudo cargar la vista general de KPI diario");
}

export async function fetchKpiDiarioCycle(filters) {
  return getData(withQuery(`${API_BASE}/api/kpi-diario/productividad/ciclo`, filters), "No se pudo cargar la vista por ciclo de KPI diario");
}

export async function fetchGmFilters(periodo = "") {
  return getJson(withQuery(`${API_BASE}/api/gm/filtros`, { periodo }), "No se pudieron cargar los filtros de GM");
}

export async function fetchGmCycle(filters) {
  return getData(withQuery(`${API_BASE}/api/gm/productividad/ciclo`, filters), "No se pudo cargar la productividad de GM");
}

export async function fetchGmGeneral(filters) {
  return getData(withQuery(`${API_BASE}/api/gm/productividad/general`, filters), "No se pudo cargar la vista general de GM");
}

export async function fetchBitFilters(periodo = "") {
  return getJson(withQuery(`${API_BASE}/api/bit/filtros`, { periodo }), "No se pudieron cargar los filtros de BIT");
}

export async function fetchBitGeneral(filters) {
  return getJson(withQuery(`${API_BASE}/api/bit/general`, filters), "No se pudo cargar la vista general de BIT");
}

export async function fetchBitTramos(filters) {
  return getJson(withQuery(`${API_BASE}/api/bit/tramos`, filters), "No se pudo cargar la vista por tramo de BIT");
}

export async function fetchBitNegocios(filters) {
  return getJson(withQuery(`${API_BASE}/api/bit/negocios`, filters), "No se pudo cargar la vista de negocios de BIT");
}

export async function fetchBitCastigoFilters(periodo = "") {
  return getJson(withQuery(`${API_BASE}/api/bit-castigo/filtros`, { periodo }), "No se pudieron cargar los filtros de BIT Castigo");
}

export async function fetchBitCastigoNuevosConvenios(filters) {
  return getJson(withQuery(`${API_BASE}/api/bit-castigo/nuevos-convenios`, filters), "No se pudo cargar el detalle de nuevos convenios de BIT Castigo");
}

export async function fetchBitCastigoGeneral(filters) {
  return getJson(withQuery(`${API_BASE}/api/bit-castigo/general`, filters), "No se pudo cargar la vista general de BIT Castigo");
}

export async function fetchProcuradoresFilters() {
  return getJson(`${API_BASE}/api/procuradores/filtros`, "No se pudieron cargar los filtros de Procuradores");
}

export async function fetchProcuradoresGeneral(periodo) {
  return getJson(withQuery(`${API_BASE}/api/procuradores/general`, { periodo }), "No se pudo cargar la vista general de Procuradores");
}

export async function fetchProcuradoresDetalle(periodo) {
  return getJson(withQuery(`${API_BASE}/api/procuradores/detalle`, { periodo }), "No se pudo cargar el detalle de Procuradores");
}

export async function saveProcuradoresLogros(periodo, valores) {
  const res = await apiFetch(`${API_BASE}/api/procuradores/logros`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ periodo, valores }),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(body?.detail || "No se pudieron guardar los logros");
  }
  return body;
}

// export async function fetchFacturaBitDashboard(periodo = "", scope = "") {
//   const res = await apiFetch(withQuery(`${API_BASE}/api/factura/bit`, { periodo, scope }));
//   const body = await res.json().catch(() => ({}));
//   if (!res.ok) {
//     throw new Error(body?.detail || "No se pudo cargar la simulación de factura BIT");
//   }
//   return body;
// }

export async function fetchItauCastigoFilters(fecha_carga = "") {
  return getJson(withQuery(`${API_BASE}/api/itau-castigo/filtros`, { fecha_carga }), "No se pudieron cargar los filtros de Itaú Castigo");
}

export async function fetchItauCastigoGeneral(filters) {
  return getJson(withQuery(`${API_BASE}/api/itau-castigo/general`, filters), "No se pudo cargar la vista general de Itaú Castigo");
}

export async function fetchItauCastigoNuevosConvenios(filters) {
  return getJson(withQuery(`${API_BASE}/api/itau-castigo/nuevos-convenios`, filters), "No se pudieron cargar los nuevos convenios de Itaú Castigo");
}

export async function fetchItauVencidaFilters(fecha_carga = "") {
  return getJson(withQuery(`${API_BASE}/api/itau-vencida/filtros`, { fecha_carga }), "No se pudieron cargar los filtros de Itaú Vencida");
}

export async function fetchItauVencidaGeneral(filters) {
  return getJson(withQuery(`${API_BASE}/api/itau-vencida/general`, filters), "No se pudo cargar la vista general de Itaú Vencida");
}

export async function fetchItauVigenteFilters(fecha_carga = "") {
  return getJson(withQuery(`${API_BASE}/api/itau-vigente/filtros`, { fecha_carga }), "No se pudieron cargar los filtros de Itaú Vigente");
}

export async function fetchItauVigenteGeneral(filters) {
  return getJson(withQuery(`${API_BASE}/api/itau-vigente/general`, filters), "No se pudo cargar la vista general de Itaú Vigente");
}

export async function fetchItauVencidaNegocios(filters) {
  return getJson(withQuery(`${API_BASE}/api/itau-vencida/negocios`, filters), "No se pudieron cargar los negocios de Itaú Vencida");
}

export async function fetchItauVigenteNegocios(filters) {
  return getJson(withQuery(`${API_BASE}/api/itau-vigente/negocios`, filters), "No se pudieron cargar los negocios de Itaú Vigente");
}

export async function fetchGmBucket(filters) {
  return getData(withQuery(`${API_BASE}/api/gm/productividad/bucket`, filters), "No se pudo cargar la vista por bucket de GM");
}

export async function fetchGmDetail(filters) {
  return getData(withQuery(`${API_BASE}/api/gm/detalle`, filters), "No se pudo cargar el detalle de GM");
}

// Mensaje del backend (detail) si lo trae; si no, el generico. Ej.: el aviso de "solo tu negocio" en los KPI.
async function detalleError(res, generico) {
  const body = await res.json().catch(() => ({}));
  return typeof body?.detail === "string" && body.detail ? body.detail : generico;
}

export async function fetchBenchFilters(filters = {}) {
  const res = await apiFetch(withQuery(`${API_BASE}/api/bench/filtros`, filters));
  if (!res.ok) {
    throw new Error(await detalleError(res, "No se pudieron cargar los filtros de BENCH"));
  }
  return res.json();
}

export async function fetchBenchKpi(filters) {
  const res = await apiFetch(withQuery(`${API_BASE}/api/bench/kpi`, filters));
  if (!res.ok) {
    throw new Error(await detalleError(res, "No se pudo cargar el panel BENCH"));
  }
  return res.json();
}

export async function fetchKpiAvancePhoenixFilters(filters = {}) {
  const res = await apiFetch(withQuery(`${API_BASE}/api/kpi-avance-phoenix/filtros`, filters));
  if (!res.ok) {
    throw new Error(await detalleError(res, "No se pudieron cargar los filtros de KPI Phoenix"));
  }
  return res.json();
}

export async function fetchKpiAvancePhoenixComparison(filters) {
  const res = await apiFetch(withQuery(`${API_BASE}/api/kpi-avance-phoenix/comparacion`, filters));
  if (!res.ok) {
    throw new Error(await detalleError(res, "No se pudo cargar la comparación de KPI Phoenix"));
  }
  return res.json();
}

export async function fetchKpiOperacionalFilters(filters = {}) {
  const res = await apiFetch(withQuery(`${API_BASE}/api/kpi-operacional/filtros`, filters));
  if (!res.ok) {
    throw new Error(await detalleError(res, "No se pudieron cargar los filtros del KPI Operacional"));
  }
  return res.json();
}

export async function fetchKpiOperacionalDashboard(filters) {
  const res = await apiFetch(withQuery(`${API_BASE}/api/kpi-operacional/dashboard`, filters));
  if (!res.ok) {
    throw new Error(await detalleError(res, "No se pudo cargar el KPI Operacional"));
  }
  return res.json();
}

export async function downloadGmExcel(periodo) {
  return downloadExcelFile(
    withQuery(`${API_BASE}/api/gm/export`, { periodo }),
    `GM_${periodo?.slice(0, 7) || "periodo"}.xlsx`
  );
}

export async function fetchSthFilters(periodo = "") {
  return getJson(withQuery(`${API_BASE}/api/sth/filtros`, { periodo }), "No se pudieron cargar los filtros de STH");
}

export async function fetchSthGeneral(filters) {
  return getData(withQuery(`${API_BASE}/api/sth/productividad/general`, filters), "No se pudo cargar la vista general de STH");
}

export async function fetchSthDetail(filters) {
  return getData(withQuery(`${API_BASE}/api/sth/productividad/desglosada`, filters), "No se pudo cargar la vista desglosada de STH");
}

export async function fetchSthMetas(filters) {
  return getData(withQuery(`${API_BASE}/api/sth/metas`, { periodo: filters.periodo }), "No se pudieron cargar las metas de STH");
}

export async function fetchSthOperationsDetail(filters) {
  return getJson(withQuery(`${API_BASE}/api/sth/detalle`, filters), "No se pudo cargar el detalle de STH");
}

export async function fetchAdminModules() {
  return getData(`${API_BASE}/api/admin/modules`, "No se pudieron cargar los módulos");
}

export async function fetchAdminUsers() {
  return getData(`${API_BASE}/api/admin/users`, "No se pudieron cargar los usuarios");
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
    throw new Error(body?.detail || "No se pudieron actualizar los módulos");
  }
  return body;
}

export async function bulkUpdateAdminUserModules(userIds, { add = [], remove = [] }) {
  const res = await apiFetch(`${API_BASE}/api/admin/users/modules/bulk`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_ids: userIds, add, remove }),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(body?.detail || "No se pudieron actualizar los módulos");
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

export async function updateAdminUser(userId, { full_name, role }) {
  const res = await apiFetch(`${API_BASE}/api/admin/users/${userId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ full_name, role }),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(body?.detail || "No se pudieron guardar los datos del usuario");
  }
  return body;
}

export async function resetAdminUserPassword(userId) {
  const res = await apiFetch(`${API_BASE}/api/admin/users/${userId}/reset-password`, { method: "POST" });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(body?.detail || "No se pudo restablecer la contraseña");
  }
  return body;
}

export async function unlockAdminUser(userId) {
  const res = await apiFetch(`${API_BASE}/api/admin/users/${userId}/unlock`, { method: "POST" });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(body?.detail || "No se pudo desbloquear el usuario");
  }
  return body;
}

export async function fetchItauMedibles(periodo) {
  const res = await apiFetch(withQuery(`${API_BASE}/api/administrativas/itau/medibles`, { periodo }));
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(body?.detail || "No se pudieron cargar los casos medibles");
  }
  return body;
}

export async function addItauMedibles(payload) {
  const res = await apiFetch(`${API_BASE}/api/administrativas/itau/medibles`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(body?.detail || "No se pudo agregar el filtro");
  }
  return body;
}

export async function replaceItauMedibles(payload) {
  const res = await apiFetch(`${API_BASE}/api/administrativas/itau/medibles`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(body?.detail || "No se pudieron guardar los casos medibles");
  }
  return body;
}

export async function sugerirItauMedibles(payload) {
  const res = await apiFetch(`${API_BASE}/api/administrativas/itau/medibles/sugerir`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(body?.detail || "No se pudieron buscar los casos medibles");
  }
  return body;
}

export async function deleteItauMedible(filtro) {
  const res = await apiFetch(withQuery(`${API_BASE}/api/administrativas/itau/medibles`, filtro), { method: "DELETE" });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(body?.detail || "No se pudo eliminar el filtro");
  }
  return body;
}

export async function fetchNegociosCargas() {
  const res = await apiFetch(`${API_BASE}/api/administrativas/negocios/cargas`);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(body?.detail || "No se pudieron cargar los archivos subidos");
  }
  return body;
}

export async function uploadNegocioCarga({ negocio, archivo }) {
  const form = new FormData();
  form.append("negocio", negocio);
  form.append("archivo", archivo);
  // Sin Content-Type: el navegador lo arma con el separador del formulario.
  const res = await apiFetch(`${API_BASE}/api/administrativas/negocios/cargas`, { method: "POST", body: form });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(body?.detail || "No se pudo subir el archivo");
  }
  return body;
}

export async function deleteNegocioCarga(idCarga) {
  const res = await apiFetch(`${API_BASE}/api/administrativas/negocios/cargas/${idCarga}`, { method: "DELETE" });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(body?.detail || "No se pudo eliminar la carga");
  }
  return body;
}

// modulo: productividad que muestra el conteo ("sc-tardia", "sc-temprana", "gm").
export async function fetchNegociosConteo(modulo, filters) {
  const res = await apiFetch(withQuery(`${API_BASE}/api/${modulo}/negocios`, filters));
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(body?.detail || "No se pudieron cargar los negocios del mes");
  }
  return body;
}

// Una fila por operacion del mes: OP, ejecutivo y tipo de negocio.
export async function fetchNegociosDetalle(modulo, filters) {
  const res = await apiFetch(withQuery(`${API_BASE}/api/${modulo}/negocios/detalle`, filters));
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(body?.detail || "No se pudo cargar el detalle de negocios");
  }
  return body;
}

export async function fetchItauAdministrativasPeriodos() {
  return getJson(`${API_BASE}/api/administrativas/itau/periodos`, "No se pudieron cargar los periodos de Itaú");
}

async function downloadExcelFile(url, fallbackFilename) {
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

export async function downloadNegociosPlantilla(negocio) {
  return downloadExcelFile(
    withQuery(`${API_BASE}/api/administrativas/negocios/plantilla`, { negocio }),
    `Plantilla_Negocios_${negocio}.xlsx`
  );
}

export async function downloadItauCuotasVencida(periodo) {
  return downloadExcelFile(
    withQuery(`${API_BASE}/api/administrativas/itau/cuotas/export`, { periodo }),
    `itau_cuotas_vencida_${periodo || "periodo"}.xlsx`
  );
}

export async function downloadItauAsignacionVencida(periodo) {
  return downloadExcelFile(
    withQuery(`${API_BASE}/api/administrativas/itau/asignacion/export`, { periodo }),
    `itau_asignacion_vencida_${periodo || "periodo"}.xlsx`
  );
}

export async function downloadItauCuotasPagadas(periodo) {
  return downloadExcelFile(
    withQuery(`${API_BASE}/api/administrativas/itau/cuotas-pagadas/export`, { periodo }),
    `itau_cuotas_pagadas_${periodo || "periodo"}.xlsx`
  );
}

export async function fetchEstrategiaItauCastigoPeriodos() {
  const res = await apiFetch(`${API_BASE}/api/estrategia-asignacion/itau-castigo/periodos`);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(body?.detail || "No se pudieron cargar los periodos de la asignación");
  }
  return body;
}

export async function downloadEstrategiaItauCastigo(periodo, ejecutivos) {
  return downloadExcelFile(
    withQuery(`${API_BASE}/api/estrategia-asignacion/itau-castigo/export`, { periodo, ejecutivos }),
    `Estrategia_Asignacion_Itau_Castigo_${periodo || "periodo"}.xlsx`
  );
}

export async function fetchContactabilidadItauFilters(periodo = "", options = {}) {
  const res = await apiFetch(withQuery(`${API_BASE}/api/contactabilidad/itau-vencida/filtros`, { periodo }), options);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || "No se pudieron cargar los filtros de contactabilidad");
  return body;
}

async function fetchContactabilidad(path, filters, options = {}) {
  const res = await apiFetch(withQuery(`${API_BASE}/api/contactabilidad/itau-vencida/${path}`, filters), options);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || "No fue posible cargar la información de contactabilidad");
  return body;
}

export const fetchContactabilidadItauDashboard = (filters, options) => fetchContactabilidad("dashboard", filters, options);

export async function downloadContactabilidadItauDetalle(filters) {
  return downloadExcelFile(
    withQuery(`${API_BASE}/api/contactabilidad/itau-vencida/detalle/export`, filters),
    "contactabilidad_itau_vencida_detalle.xlsx"
  );
}

export async function fetchRrhhPeriodos() {
  const res = await apiFetch(`${API_BASE}/api/rrhh/periodos`);
  if (!res.ok) {
    throw new Error("No se pudieron cargar los meses disponibles");
  }
  const body = await res.json();
  return body.periodos || [];
}

export async function fetchRrhhNegocios(periodo) {
  const res = await apiFetch(withQuery(`${API_BASE}/api/rrhh/negocios`, { periodo }));
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(body?.detail || "No se pudieron cargar los negocios del mes");
  }
  return body.negocios || [];
}

export async function fetchRrhhPlanilla(periodo, negocio) {
  const res = await apiFetch(withQuery(`${API_BASE}/api/rrhh/planilla`, { periodo, negocio }));
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(body?.detail || "No se pudo cargar la planilla del negocio");
  }
  return body;
}

export async function downloadRrhhPlanilla(periodo, negocio) {
  return downloadExcelFile(
    withQuery(`${API_BASE}/api/rrhh/export`, { periodo, negocio }),
    `Cumplimiento_${negocio}_${periodo || "periodo"}.xlsx`
  );
}

export async function downloadProcuradoresExcel(periodo) {
  return downloadExcelFile(
    withQuery(`${API_BASE}/api/procuradores/export`, { periodo }),
    `Procuradores_${periodo || "periodo"}.xlsx`
  );
}

export async function downloadBitExcel(periodo) {
  return downloadExcelFile(
    withQuery(`${API_BASE}/api/bit/export`, { periodo }),
    `BIT_Vigente_${periodo || "periodo"}.xlsx`
  );
}

export async function downloadBitCastigoExcel(periodo) {
  return downloadExcelFile(
    withQuery(`${API_BASE}/api/bit-castigo/export`, { periodo }),
    `BIT_Castigo_${periodo || "periodo"}.xlsx`
  );
}

export async function downloadItauCastigoExcel(fecha_carga) {
  return downloadExcelFile(
    withQuery(`${API_BASE}/api/itau-castigo/export`, { fecha_carga }),
    `Itau_Castigo_${fecha_carga || "fecha"}.xlsx`
  );
}

export async function downloadItauVencidaExcel(fecha_carga) {
  return downloadExcelFile(
    withQuery(`${API_BASE}/api/itau-vencida/export`, { fecha_carga }),
    `Itau_Vencida_${fecha_carga || "fecha"}.xlsx`
  );
}

export async function downloadItauVigenteExcel(fecha_carga) {
  return downloadExcelFile(
    withQuery(`${API_BASE}/api/itau-vigente/export`, { fecha_carga }),
    `Itau_Vigente_${fecha_carga || "fecha"}.xlsx`
  );
}

export async function downloadRrhhConsolidado(periodo) {
  return downloadExcelFile(
    withQuery(`${API_BASE}/api/rrhh/export`, { periodo }),
    `Cumplimientos_Campanas_${periodo || "periodo"}.xlsx`
  );
}

export async function downloadLaAraucanaProductividadExcel(periodo) {
  return downloadExcelFile(
    withQuery(`${API_BASE}/api/la-araucana/export/productividad`, { periodo }),
    `La_Araucana_${periodo || "periodo"}.xlsx`
  );
}

export async function downloadScTardiaExcel(periodo, base = "sc-tardia") {
  const prefijo = base === "sc-piloto" ? "SC_Piloto" : "SC_Tardia";
  return downloadExcelFile(
    withQuery(`${API_BASE}/api/${base}/export`, { periodo }),
    `${prefijo}_${periodo || "periodo"}.xlsx`
  );
}

export async function downloadScTempranaExcel(periodo) {
  return downloadExcelFile(
    withQuery(`${API_BASE}/api/sc-temprana/export`, { periodo }),
    `SC_Temprana_${periodo || "periodo"}.xlsx`
  );
}

export async function downloadSthExcel(periodo) {
  return downloadExcelFile(
    withQuery(`${API_BASE}/api/sth/export`, { periodo }),
    `STH_${String(periodo || "periodo").slice(0, 7)}.xlsx`
  );
}

// Simulador Veritus: deudor de la asignacion del mes por RUT (con o sin puntos, guion y DV).
export async function fetchVeritusDeudor(rut) {
  const res = await apiFetch(withQuery(`${API_BASE}/api/simulador-veritus/deudor`, { rut }));
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const error = new Error(body?.detail || "No se pudo buscar el RUT");
    error.status = res.status;
    throw error;
  }
  const body = await res.json();
  return body.data;
}
