import React from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "./AuthContext";

export default function ProtectedRoute({ children, moduleCode = "", allowedRoles = [] }) {
  const { isAuthenticated, user } = useAuth();
  const location = useLocation();

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  if (user?.must_change_password && location.pathname !== "/change-password") {
    return <Navigate to="/change-password" replace />;
  }

  if (moduleCode) {
    const role = user?.role;
    const hasGlobal = role === "super_admin" || role === "admin" || role === "coordinador";
    const hasModule = (user?.modules || []).includes(moduleCode);
    if (!hasGlobal && !hasModule) {
      return <Navigate to="/" replace />;
    }
  }

  if (allowedRoles.length && !allowedRoles.includes(user?.role || "")) {
    return <Navigate to="/" replace />;
  }

  return children;
}
