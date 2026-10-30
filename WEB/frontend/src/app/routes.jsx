import React from "react";
import AdminUsersPage from "../pages/admin/AdminUsersPage";
import BenchPage from "../pages/kpi/BenchPage";
import BitCastigoPage from "../pages/productividad/BitCastigoPage";
import BitPage from "../pages/productividad/BitPage";
import ContactabilidadItauVencidaPage from "../pages/contactabilidad/ContactabilidadItauVencidaPage";
import EstrategiaItauCastigoPage from "../pages/estrategia/EstrategiaItauCastigoPage";
import GestionesDiariasSctPage from "../pages/administrativas/GestionesDiariasSctPage";
import GmPage from "../pages/productividad/GmPage";
import ItauAdministrativasPage from "../pages/administrativas/ItauAdministrativasPage";
import ItauCastigoPage from "../pages/productividad/ItauCastigoPage";
import ItauVencidaPage from "../pages/productividad/ItauVencidaPage";
import ItauVigentePage from "../pages/productividad/ItauVigentePage";
import KpiAvancePhoenixPage from "../pages/kpi/KpiAvancePhoenixPage";
import KpiOperacionalPage from "../pages/kpi/KpiOperacionalPage";
import LaAraucanaPage from "../pages/productividad/LaAraucanaPage";
import NegociosAdministrativasPage from "../pages/administrativas/NegociosAdministrativasPage";
import ProcuradoresPage from "../pages/productividad/ProcuradoresPage";
import RrhhPage from "../pages/rrhh/RrhhPage";
import ScTardiaPage from "../pages/productividad/ScTardiaPage";
import ScTempranaPage from "../pages/productividad/ScTempranaPage";
import SthPage from "../pages/productividad/SthPage";

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
  "/productividad/procuradores": <ProcuradoresPage />,
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
