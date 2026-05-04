import { Navigate, Route, Routes } from "react-router-dom";
import GmPage from "./pages/GmPage";
import HomePage from "./pages/HomePage";
import LaAraucanaPage from "./pages/LaAraucanaPage";
import PorschePage from "./pages/PorschePage";
import ScTardiaPage from "./pages/ScTardiaPage";
import ScTempranaPage from "./pages/ScTempranaPage";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/sc-tardia" element={<ScTardiaPage />} />
      <Route path="/sc-temprana" element={<ScTempranaPage />} />
      <Route path="/gm" element={<GmPage />} />
      <Route path="/la-araucana" element={<LaAraucanaPage />} />
      <Route path="/porsche" element={<PorschePage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
