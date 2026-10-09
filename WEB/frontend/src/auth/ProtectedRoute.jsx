import React from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "./AuthContext";
import { canAccessModule } from "./permissions";

export default function ProtectedRoute({ children, moduleCode = "", allowedRoles = [] }) {
  const { isAuthenticated, user } = useAuth();
  const location = useLocation();

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  // Sesion guardada antes de que el backend enviara los accesos: AuthProvider la esta renovando.
  if (!Array.isArray(user?.access)) {
    return null;
  }

  if (user?.must_change_password && location.pathname !== "/change-password") {
    return <Navigate to="/change-password" replace />;
  }

  if (moduleCode) {
    if (!canAccessModule(user, moduleCode)) {
      return <Navigate to="/" replace />;
    }
  }

  if (allowedRoles.length && !allowedRoles.includes(user?.role || "")) {
    return <Navigate to="/" replace />;
  }

  return children;
}
