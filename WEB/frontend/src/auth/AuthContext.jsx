import React, { createContext, useContext, useEffect, useMemo, useState } from "react";
import { authLogin, authLogout, authRefresh } from "./apiAuth";

const ACCESS_KEY = "auth_access_token";
const USER_KEY = "auth_user";

const AuthContext = createContext(null);

function loadInitial() {
  const token = localStorage.getItem(ACCESS_KEY) || "";
  const userRaw = localStorage.getItem(USER_KEY);
  let user = null;
  if (userRaw) {
    try {
      user = JSON.parse(userRaw);
    } catch {
      user = null;
    }
  }
  return { token, user };
}

export function AuthProvider({ children }) {
  const init = loadInitial();
  const [accessToken, setAccessToken] = useState(init.token);
  const [user, setUser] = useState(init.user);

  function setSession(token, userData) {
    setAccessToken(token || "");
    setUser(userData || null);
    if (token) {
      localStorage.setItem(ACCESS_KEY, token);
    } else {
      localStorage.removeItem(ACCESS_KEY);
    }
    if (userData) {
      localStorage.setItem(USER_KEY, JSON.stringify(userData));
    } else {
      localStorage.removeItem(USER_KEY);
    }
  }

  async function login(email, password) {
    const data = await authLogin(email, password);
    setSession(data.access_token, data.user);
    return data.user;
  }

  async function refresh() {
    const data = await authRefresh();
    setSession(data.access_token, data.user);
    return data.access_token;
  }

  async function logout() {
    try {
      await authLogout(accessToken);
    } finally {
      setSession("", null);
    }
  }

  useEffect(() => {
    function handleSessionExpired() {
      setSession("", null);
    }
    window.addEventListener("auth-session-expired", handleSessionExpired);
    return () => window.removeEventListener("auth-session-expired", handleSessionExpired);
  }, []);

  useEffect(() => {
    if (!accessToken || !user) {
      return undefined;
    }
    const now = new Date();
    const logoutAt = new Date(now);
    logoutAt.setHours(23, 0, 0, 0);
    if (logoutAt <= now) {
      logoutAt.setDate(logoutAt.getDate() + 1);
    }
    const timerId = window.setTimeout(() => {
      setSession("", null);
    }, logoutAt.getTime() - now.getTime());
    return () => window.clearTimeout(timerId);
  }, [accessToken, user]);

  const value = useMemo(
    () => ({
      accessToken,
      user,
      isAuthenticated: Boolean(accessToken && user),
      login,
      refresh,
      logout,
      setSession,
    }),
    [accessToken, user]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth debe usarse dentro de AuthProvider");
  }
  return ctx;
}
