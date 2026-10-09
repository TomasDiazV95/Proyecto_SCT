import React from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { modulePanels } from "./app/moduleCatalog";
import { modulePages } from "./app/routes";
import ProtectedRoute from "./auth/ProtectedRoute";
import ChangePasswordPage from "./pages/ChangePasswordPage";
import ForgotPasswordPage from "./pages/ForgotPasswordPage";
import HomePage from "./pages/HomePage";
import LoginPage from "./pages/LoginPage";
import PanelPage from "./pages/PanelPage";

// Direccion antigua de un modulo: lleva a la nueva conservando los parametros.
function LegacyRedirect({ to }) {
  const { search, hash } = useLocation();
  return <Navigate to={{ pathname: to, search, hash }} replace />;
}

const modules = modulePanels.flatMap((panel) => panel.modules);

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<Navigate to="/forgot-password" replace />} />
      <Route path="/change-password" element={<ProtectedRoute><ChangePasswordPage /></ProtectedRoute>} />
      <Route path="/" element={<ProtectedRoute><HomePage /></ProtectedRoute>} />
      {modulePanels.map((panel) => (
        <Route key={panel.path} path={panel.path} element={<ProtectedRoute><PanelPage panelCode={panel.code} /></ProtectedRoute>} />
      ))}
      {modules.map((module) => (
        <Route key={module.path} path={module.path} element={<ProtectedRoute moduleCode={module.code}>{modulePages[module.path]}</ProtectedRoute>} />
      ))}
      {modules.filter((module) => module.legacyPath).map((module) => (
        <Route key={module.legacyPath} path={module.legacyPath} element={<LegacyRedirect to={module.path} />} />
      ))}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
