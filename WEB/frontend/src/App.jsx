import React from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import ProtectedRoute from "./auth/ProtectedRoute";
import AdminUsersPage from "./pages/AdminUsersPage";
import ChangePasswordPage from "./pages/ChangePasswordPage";
import BitPage from "./pages/BitPage";
import ForgotPasswordPage from "./pages/ForgotPasswordPage";
import GmPage from "./pages/GmPage";
import HomePage from "./pages/HomePage";
import LaAraucanaPage from "./pages/LaAraucanaPage";
import LoginPage from "./pages/LoginPage";
import PorschePage from "./pages/PorschePage";
import ResetPasswordPage from "./pages/ResetPasswordPage";
import ScTardiaPage from "./pages/ScTardiaPage";
import ScTempranaPage from "./pages/ScTempranaPage";
import SthPage from "./pages/SthPage";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route path="/change-password" element={<ProtectedRoute><ChangePasswordPage /></ProtectedRoute>} />
      <Route path="/admin/usuarios" element={<ProtectedRoute allowedRoles={["admin", "super_admin"]}><AdminUsersPage /></ProtectedRoute>} />
      <Route path="/" element={<ProtectedRoute><HomePage /></ProtectedRoute>} />
      <Route path="/sc-tardia" element={<ProtectedRoute moduleCode="sc-tardia"><ScTardiaPage /></ProtectedRoute>} />
      <Route path="/sc-temprana" element={<ProtectedRoute moduleCode="sc-temprana"><ScTempranaPage /></ProtectedRoute>} />
      <Route path="/gm" element={<ProtectedRoute moduleCode="gm"><GmPage /></ProtectedRoute>} />
      <Route path="/bit" element={<ProtectedRoute moduleCode="bit"><BitPage /></ProtectedRoute>} />
      <Route path="/la-araucana" element={<ProtectedRoute moduleCode="la-araucana"><LaAraucanaPage /></ProtectedRoute>} />
      <Route path="/porsche" element={<ProtectedRoute moduleCode="porsche"><PorschePage /></ProtectedRoute>} />
      <Route path="/sth" element={<ProtectedRoute moduleCode="sth"><SthPage /></ProtectedRoute>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
