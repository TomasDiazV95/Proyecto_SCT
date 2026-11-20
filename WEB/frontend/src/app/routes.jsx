import { lazy } from "react";

// Cada pagina se descarga al abrirla por primera vez (el JS inicial queda mas liviano).
// Sus CSS propios se importan en main.jsx para que los estilos sigan siendo los de siempre.
const AdminUsersPage = lazy(() => import("../pages/admin/AdminUsersPage"));
const BenchPage = lazy(() => import("../pages/kpi/BenchPage"));
const BitCastigoPage = lazy(() => import("../pages/productividad/BitCastigoPage"));
const BitPage = lazy(() => import("../pages/productividad/BitPage"));
const ContactabilidadItauVencidaPage = lazy(() => import("../pages/contactabilidad/ContactabilidadItauVencidaPage"));
const EstrategiaItauCastigoPage = lazy(() => import("../pages/estrategia/EstrategiaItauCastigoPage"));
const GestionesDiariasSctPage = lazy(() => import("../pages/administrativas/GestionesDiariasSctPage"));
const GmPage = lazy(() => import("../pages/productividad/GmPage"));
const ItauAdministrativasPage = lazy(() => import("../pages/administrativas/ItauAdministrativasPage"));
const ItauCastigoPage = lazy(() => import("../pages/productividad/ItauCastigoPage"));
const ItauVencidaPage = lazy(() => import("../pages/productividad/ItauVencidaPage"));
const ItauVigentePage = lazy(() => import("../pages/productividad/ItauVigentePage"));
const KpiAvancePhoenixPage = lazy(() => import("../pages/kpi/KpiAvancePhoenixPage"));
const KpiOperacionalPage = lazy(() => import("../pages/kpi/KpiOperacionalPage"));
const LaAraucanaPage = lazy(() => import("../pages/productividad/LaAraucanaPage"));
const NegociosAdministrativasPage = lazy(() => import("../pages/administrativas/NegociosAdministrativasPage"));
const ProcuradoresPage = lazy(() => import("../pages/productividad/ProcuradoresPage"));
const RrhhPage = lazy(() => import("../pages/rrhh/RrhhPage"));
const ScPilotoPage = lazy(() => import("../pages/productividad/ScPilotoPage"));
const ScTardiaPage = lazy(() => import("../pages/productividad/ScTardiaPage"));
const ScTempranaPage = lazy(() => import("../pages/productividad/ScTempranaPage"));
const SimuladorRenegociacionPage = lazy(() => import("../pages/simuladores/SimuladorRenegociacionPage"));
const SimuladorVeritusPage = lazy(() => import("../pages/simuladores/SimuladorVeritusPage"));
const SthPage = lazy(() => import("../pages/productividad/SthPage"));

// Pagina de cada modulo del catalogo (moduleCatalog.js), por su path.
export const modulePages = {
  "/productividad/sc-tardia": <ScTardiaPage />,
  "/productividad/sc-piloto": <ScPilotoPage />,
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
  "/simuladores/renegociacion-itau": <SimuladorRenegociacionPage />,
  "/simuladores-veritus/convenios": <SimuladorVeritusPage />,
  "/rrhh/cumplimientos": <RrhhPage />,
  "/admin/usuarios": <AdminUsersPage />,
};
