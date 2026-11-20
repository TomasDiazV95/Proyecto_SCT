// Aviso de los KPI para un supervisor sin productividad asignada. Los supervisores ven en los KPI solo los
// negocios de su productividad; la regla esta en el backend (auth/negocios_kpi.py), que responde sin_negocio.
export const SIN_NEGOCIO_KPI =
  "No tienes un negocio asignado para ver los KPI. Pide al administrador que te asigne la productividad de tu negocio.";
