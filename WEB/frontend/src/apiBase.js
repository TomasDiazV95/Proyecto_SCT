// Base de la API y cierre de sesion local, compartidos por api.js y auth/apiAuth.js.
export const API_BASE = import.meta.env.VITE_API_URL || "";

export function clearStoredSession() {
  localStorage.removeItem("auth_access_token");
  localStorage.removeItem("auth_user");
  window.dispatchEvent(new Event("auth-session-expired"));
}
