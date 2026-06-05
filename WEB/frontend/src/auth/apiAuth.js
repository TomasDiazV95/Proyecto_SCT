const API_BASE = import.meta.env.VITE_API_URL || "";

export async function authLogin(email, password) {
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const body = await safeJson(res);
    throw new Error(body?.detail || "No se pudo iniciar sesion");
  }
  return res.json();
}

export async function authRefresh() {
  const res = await fetch(`${API_BASE}/api/auth/refresh`, {
    method: "POST",
    credentials: "include",
  });
  if (!res.ok) {
    throw new Error("Sesion expirada");
  }
  return res.json();
}

export async function authMe(accessToken) {
  const res = await fetch(`${API_BASE}/api/auth/me`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!res.ok) {
    throw new Error("No se pudo validar sesion");
  }
  return res.json();
}

export async function authLogout(accessToken) {
  await fetch(`${API_BASE}/api/auth/logout`, {
    method: "POST",
    credentials: "include",
    headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : undefined,
  });
}

export async function authChangePassword(accessToken, currentPassword, newPassword) {
  const res = await fetch(`${API_BASE}/api/auth/change-password`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${accessToken}`,
    },
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });
  if (!res.ok) {
    const body = await safeJson(res);
    throw new Error(body?.detail || "No se pudo cambiar la contrasena");
  }
  return res.json();
}

export async function authForgotPassword(email) {
  const res = await fetch(`${API_BASE}/api/auth/forgot-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  if (!res.ok) {
    throw new Error("No se pudo procesar la solicitud");
  }
  return res.json();
}

export async function authVerifyResetCode(email, code) {
  const res = await fetch(`${API_BASE}/api/auth/verify-reset-code`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, code }),
  });
  if (!res.ok) {
    const body = await safeJson(res);
    throw new Error(body?.detail || "Codigo invalido o expirado");
  }
  return res.json();
}

export async function authResetPassword(email, code, newPassword) {
  const res = await fetch(`${API_BASE}/api/auth/reset-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, code, new_password: newPassword }),
  });
  if (!res.ok) {
    const body = await safeJson(res);
    throw new Error(body?.detail || "No se pudo restablecer la contrasena");
  }
  return res.json();
}

async function safeJson(res) {
  try {
    return await res.json();
  } catch {
    return null;
  }
}
