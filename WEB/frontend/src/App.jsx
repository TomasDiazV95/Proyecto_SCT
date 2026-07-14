import React from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import ProtectedRoute from "./auth/ProtectedRoute";
import AdminUsersPage from "./pages/AdminUsersPage";
import AdministrativasPage from "./pages/administrativas/AdministrativasPage";
import BenchPage from "./pages/BenchPage";
import BitCastigoPage from "./pages/BitCastigoPage";
import ChangePasswordPage from "./pages/ChangePasswordPage";
import BitPage from "./pages/BitPage";
import ForgotPasswordPage from "./pages/ForgotPasswordPage";
import GmPage from "./pages/GmPage";
import HomePage from "./pages/HomePage";
import ItauCastigoPage from "./pages/ItauCastigoPage";
import ItauAdministrativasPage from "./pages/administrativas/ItauAdministrativasPage";
import LaAraucanaPage from "./pages/LaAraucanaPage";
import LoginPage from "./pages/LoginPage";
import PanelPage from "./pages/PanelPage";
import PorschePage from "./pages/PorschePage";
import PlaceholderPage from "./pages/PlaceholderPage";
import ScTardiaPage from "./pages/ScTardiaPage";
import ScTempranaPage from "./pages/ScTempranaPage";
import SthPage from "./pages/SthPage";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<Navigate to="/forgot-password" replace />} />
      <Route path="/change-password" element={<ProtectedRoute><ChangePasswordPage /></ProtectedRoute>} />
      <Route path="/admin/usuarios" element={<ProtectedRoute moduleCode="admin"><AdminUsersPage /></ProtectedRoute>} />
      <Route path="/" element={<ProtectedRoute><HomePage /></ProtectedRoute>} />
      <Route path="/productividad" element={<ProtectedRoute><PanelPage panelCode="productividad" /></ProtectedRoute>} />
      <Route path="/kpi" element={<ProtectedRoute><PanelPage panelCode="kpi" /></ProtectedRoute>} />
      <Route path="/contactabilidad" element={<ProtectedRoute><PanelPage panelCode="contactabilidad" emptyTitle="Panel de Contactabilidad en preparacion" emptyDescription="Este panel quedo reservado para nuevos indicadores de contactabilidad." /></ProtectedRoute>} />
      <Route path="/admin" element={<ProtectedRoute moduleCode="admin"><PanelPage panelCode="admin" /></ProtectedRoute>} />
      <Route path="/sc-tardia" element={<ProtectedRoute moduleCode="sc-tardia"><ScTardiaPage /></ProtectedRoute>} />
      <Route path="/sc-temprana" element={<ProtectedRoute moduleCode="sc-temprana"><ScTempranaPage /></ProtectedRoute>} />
      <Route path="/gm" element={<ProtectedRoute moduleCode="gm"><GmPage /></ProtectedRoute>} />
      <Route path="/bench" element={<ProtectedRoute moduleCode="bench"><BenchPage /></ProtectedRoute>} />
      <Route path="/itau-castigo" element={<ProtectedRoute moduleCode="itau-castigo"><ItauCastigoPage /></ProtectedRoute>} />
      <Route path="/bit-castigo" element={<ProtectedRoute moduleCode="bit-castigo"><BitCastigoPage /></ProtectedRoute>} />
      <Route path="/bit" element={<ProtectedRoute moduleCode="bit"><BitPage /></ProtectedRoute>} />
      <Route path="/la-araucana" element={<ProtectedRoute moduleCode="la-araucana"><LaAraucanaPage /></ProtectedRoute>} />
      <Route path="/porsche" element={<ProtectedRoute moduleCode="porsche"><PorschePage /></ProtectedRoute>} />
      <Route path="/sth" element={<ProtectedRoute moduleCode="sth"><SthPage /></ProtectedRoute>} />
      <Route path="/factura" element={<ProtectedRoute moduleCode="factura"><PanelPage panelCode="factura" emptyTitle="Panel de Factura en preparacion" emptyDescription="Este modulo esta reservado para simular facturas" /></ProtectedRoute>} />
      <Route path="/administrativas" element={<ProtectedRoute moduleCode="administrativas"><AdministrativasPage /></ProtectedRoute>} />
      <Route path="/administrativas/itau" element={<ProtectedRoute moduleCode="administrativas"><ItauAdministrativasPage /></ProtectedRoute>} />
      <Route path="/admin/permisos" element={<ProtectedRoute moduleCode="admin"><PlaceholderPage title="Permisos" description="Administracion avanzada de permisos." /></ProtectedRoute>} />
      <Route path="/admin/configuracion" element={<ProtectedRoute moduleCode="admin"><PlaceholderPage title="Configuracion" description="Configuracion general de la plataforma." /></ProtectedRoute>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
