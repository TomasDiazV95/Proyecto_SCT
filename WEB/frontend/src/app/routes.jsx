import React from "react";
import AdminUsersPage from "../pages/AdminUsersPage";
import BenchPage from "../pages/BenchPage";
import BitCastigoPage from "../pages/BitCastigoPage";
import BitPage from "../pages/BitPage";
import ContactabilidadItauVencidaPage from "../pages/ContactabilidadItauVencidaPage";
import EstrategiaItauCastigoPage from "../pages/estrategia/EstrategiaItauCastigoPage";
import GestionesDiariasSctPage from "../pages/GestionesDiariasSctPage";
import GmPage from "../pages/GmPage";
import ItauAdministrativasPage from "../pages/administrativas/ItauAdministrativasPage";
import ItauCastigoPage from "../pages/ItauCastigoPage";
import ItauVencidaPage from "../pages/ItauVencidaPage";
import ItauVigentePage from "../pages/ItauVigentePage";
import KpiAvancePhoenixPage from "../pages/KpiAvancePhoenixPage";
import KpiOperacionalPage from "../pages/KpiOperacionalPage";
import LaAraucanaPage from "../pages/LaAraucanaPage";
import NegociosAdministrativasPage from "../pages/administrativas/NegociosAdministrativasPage";
import RrhhPage from "../pages/RrhhPage";
import ScTardiaPage from "../pages/ScTardiaPage";
import ScTempranaPage from "../pages/ScTempranaPage";
import SthPage from "../pages/SthPage";

// Pagina de cada modulo del catalogo (moduleCatalog.js), por su path.
export const modulePages = {
  "/productividad/sc-tardia": <ScTardiaPage />,
  "/productividad/sc-temprana": <ScTempranaPage />,
  "/productividad/gm": <GmPage />,
  "/productividad/itau-castigo": <ItauCastigoPage />,
  "/productividad/itau-vencida": <ItauVencidaPage />,
  "/productividad/itau-vigente": <ItauVigentePage />,
  "/productividad/sth": <SthPage />,
  "/productividad/bit": <BitPage />,
  "/productividad/bit-castigo": <BitCastigoPage />,
  "/productividad/la-araucana": <LaAraucanaPage />,
  "/kpi/bench": <BenchPage />,
  "/kpi/avance-phoenix": <KpiAvancePhoenixPage />,
  "/kpi/operacional": <KpiOperacionalPage />,
  "/contactabilidad/itau-vencida": <ContactabilidadItauVencidaPage />,
  "/administrativas/itau-vencida": <ItauAdministrativasPage />,
  "/administrativas/negocios": <NegociosAdministrativasPage />,
  "/administrativas/gestiones-diarias-sct": <GestionesDiariasSctPage />,
  "/estrategia-asignacion/itau-castigo": <EstrategiaItauCastigoPage />,
  "/rrhh/cumplimientos": <RrhhPage />,
  "/admin/usuarios": <AdminUsersPage />,
};
