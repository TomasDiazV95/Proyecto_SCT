// Logica de accesos del Panel Admin > Usuarios. Solo calculo: sin React ni DOM.
// Los modulos vienen de dbo.modules (API /api/admin/modules): un panel es un modulo sin parent_code y
// sus modulos son los que lo tienen como parent_code. Asignar el panel abre todos sus modulos.

import { modulePanels } from "../../app/moduleCatalog";

export const GLOBAL = "global";
export const ADMIN = "admin";
// Modulos que solo abre el super admin aunque se le asignen a otro usuario.
export const SOLO_SUPER_ADMIN = ["rrhh"];
const ROLES_ADMIN = ["super_admin", "admin"];

export const ESPECIALES = [
  { code: GLOBAL, titulo: "Acceso global", detalle: "Todos los paneles y módulos, incluidos los que se agreguen después. No incluye el Panel Admin." },
  { code: ADMIN, titulo: "Panel Admin", detalle: "Administrar usuarios y sus accesos." },
];

// "Panel de Productividad" -> "Productividad"; "Panel KPI" -> "KPI".
export function tituloCorto(titulo) {
  return String(titulo || "").replace(/^Panel (de )?/i, "");
}

function ordenCatalogo() {
  return Object.fromEntries(modulePanels.map((panel, i) => [panel.code, i]));
}

// Paginas propias del panel: en el catalogo, modulos con el mismo codigo del panel (ej. Panel Administrativo:
// Itau Vencida y Negocios). Solo se abren asignando el panel, que ademas incluye sus submodulos.
function tienePaginasPropias(code) {
  const panel = modulePanels.find((p) => p.code === code);
  return Boolean(panel?.modules.some((m) => m.code === code));
}

// Paneles en el orden del inicio, con sus modulos. simple = se asigna con un interruptor: sin submodulos,
// o con uno solo y sin paginas propias (simuladores). Los accesos especiales (global, admin) no van aqui.
export function armarPaneles(modules) {
  const orden = ordenCatalogo();
  const especiales = new Set(ESPECIALES.map((e) => e.code));
  return modules
    .filter((m) => !m.parent_code && !especiales.has(m.code))
    .map((panel) => {
      // Modulos en el orden en que aparecen en el panel (catalogo); los que no esten, al final.
      const ordenModulos = (modulePanels.find((p) => p.code === panel.code)?.modules || []).map((m) => m.code);
      const posicion = (code) => (ordenModulos.includes(code) ? ordenModulos.indexOf(code) : 999);
      const modulos = modules
        .filter((m) => m.parent_code === panel.code)
        .map((m) => ({ code: m.code, nombre: m.display_name }))
        .sort((a, b) => posicion(a.code) - posicion(b.code));
      const propio = tienePaginasPropias(panel.code);
      return {
        code: panel.code,
        titulo: panel.display_name,
        modulos,
        propio,
        simple: modulos.length === 0 || (modulos.length === 1 && !propio),
        soloSuperAdmin: SOLO_SUPER_ADMIN.includes(panel.code),
      };
    })
    .sort((a, b) => (orden[a.code] ?? 999) - (orden[b.code] ?? 999) || a.titulo.localeCompare(b.titulo, "es"));
}

// Copia de effective_modules (WEB/backend/auth/permissions.py): mantener igual. Solo para la vista previa;
// el acceso real lo decide el backend.
export function accesoEfectivo(rol, asignados, modules) {
  const todos = new Set(modules.map((m) => m.code));
  if (rol === "super_admin") {
    return todos;
  }
  SOLO_SUPER_ADMIN.forEach((code) => todos.delete(code));
  if (ROLES_ADMIN.includes(rol)) {
    return todos;
  }
  const acceso = new Set((asignados || []).filter((code) => todos.has(code)));
  if (acceso.has(GLOBAL)) {
    const salida = new Set(todos);
    salida.delete(ADMIN);
    acceso.forEach((code) => salida.add(code));
    return salida;
  }
  modules.forEach((m) => {
    if (m.parent_code && acceso.has(m.parent_code)) {
      acceso.add(m.code);
    }
  });
  SOLO_SUPER_ADMIN.forEach((code) => acceso.delete(code));
  return acceso;
}

// Que ve de un panel quien tiene estos accesos efectivos: null (nada) o { n, total, completo }.
export function accesoPanel(panel, acceso) {
  if (panel.simple) {
    const ve = acceso.has(panel.code) || panel.modulos.some((m) => acceso.has(m.code));
    return ve ? { n: 1, total: 1, completo: true } : null;
  }
  // Las paginas propias del panel cuentan como un modulo mas (las abre solo quien tiene el panel).
  const propias = panel.propio ? 1 : 0;
  const n = panel.modulos.filter((m) => acceso.has(m.code)).length + (panel.propio && acceso.has(panel.code) ? 1 : 0);
  const total = panel.modulos.length + propias;
  return n ? { n, total, completo: n === total } : null;
}

// Resumen para la tabla y la vista previa: una entrada por panel que el usuario puede abrir.
export function resumenAccesos(rol, asignados, acceso, paneles) {
  const set = acceso instanceof Set ? acceso : new Set(acceso || []);
  const items = [];
  if (ROLES_ADMIN.includes(rol)) {
    items.push({ code: "_todo", etiqueta: rol === "super_admin" ? "Todo (super admin)" : "Todo (administrador)", completo: true });
    return { items, paneles: paneles.filter((p) => accesoPanel(p, set)).length, modulos: contarModulos(paneles, set) };
  }
  if ((asignados || []).includes(GLOBAL)) {
    items.push({ code: GLOBAL, etiqueta: "Acceso global", completo: true });
  }
  if (set.has(ADMIN)) {
    items.push({ code: ADMIN, etiqueta: "Panel Admin", completo: true });
  }
  if (!(asignados || []).includes(GLOBAL)) {
    paneles.forEach((panel) => {
      const a = accesoPanel(panel, set);
      if (a) {
        const corto = tituloCorto(panel.titulo);
        const nombres = panel.simple ? [] : panel.modulos.filter((m) => set.has(m.code)).map((m) => m.nombre);
        let etiqueta = corto;
        if (!panel.simple) {
          // Con uno o dos modulos se nombran; con mas, se cuentan.
          etiqueta = a.completo ? `${corto} · todo` : a.n <= 2 ? `${corto} · ${nombres.join(", ")}` : `${corto} · ${a.n} de ${a.total}`;
        }
        items.push({ code: panel.code, etiqueta, completo: a.completo, detalle: nombres.join(", ") || null });
      }
    });
  }
  return { items, paneles: paneles.filter((p) => accesoPanel(p, set)).length, modulos: contarModulos(paneles, set) };
}

// Modulos que se pueden abrir (un panel simple cuenta como uno).
function contarModulos(paneles, set) {
  return paneles.reduce((total, panel) => total + (accesoPanel(panel, set)?.n || 0), 0);
}

// ---- Seleccion en el selector (lista de codigos asignados) ----

// "todo" | "algunos" | "nada". abiertos: paneles que la usuaria abrio en "Algunos" aunque no tengan nada marcado.
export function estadoPanel(panel, seleccion, abiertos) {
  if (seleccion.includes(panel.code)) {
    return "todo";
  }
  if (panel.simple) {
    return panel.modulos.some((m) => seleccion.includes(m.code)) ? "todo" : "nada";
  }
  if (panel.modulos.some((m) => seleccion.includes(m.code)) || abiertos?.has(panel.code)) {
    return "algunos";
  }
  return "nada";
}

const sinCodigos = (seleccion, codigos) => seleccion.filter((code) => !codigos.includes(code));

// Nueva seleccion al elegir un estado para el panel. Al pasar de "todo" a "algunos" quedan todos sus
// modulos marcados, para desmarcar los que sobran.
export function aplicarEstado(panel, seleccion, estado) {
  const propios = [panel.code, ...panel.modulos.map((m) => m.code)];
  const base = sinCodigos(seleccion, propios);
  if (estado === "todo") {
    return [...base, panel.code];
  }
  if (estado === "algunos") {
    const antes = estadoPanel(panel, seleccion);
    const marcados = antes === "todo" ? panel.modulos.map((m) => m.code) : panel.modulos.map((m) => m.code).filter((c) => seleccion.includes(c));
    return [...base, ...marcados];
  }
  return base;
}

export function alternar(seleccion, code) {
  return seleccion.includes(code) ? seleccion.filter((c) => c !== code) : [...seleccion, code];
}

// Cuantos codigos cambian entre dos selecciones.
export function contarCambios(original, actual) {
  const a = new Set(original || []);
  const b = new Set(actual || []);
  let n = 0;
  a.forEach((code) => { if (!b.has(code)) n += 1; });
  b.forEach((code) => { if (!a.has(code)) n += 1; });
  return n;
}

// Asignacion masiva: quitar "Todo el panel" quita tambien sus modulos sueltos.
export function expandirParaQuitar(seleccion, paneles) {
  const salida = new Set(seleccion);
  paneles.forEach((panel) => {
    if (seleccion.includes(panel.code)) {
      panel.modulos.forEach((m) => salida.add(m.code));
    }
  });
  return [...salida];
}

// Opciones del filtro "Con acceso a": casos generales, cada panel y, si tiene varios, sus modulos.
export function opcionesFiltroAcceso(paneles) {
  return [
    {
      grupo: "General",
      opciones: [
        { value: "sin", label: "Sin accesos" },
        { value: `esp:${GLOBAL}`, label: "Acceso global" },
        { value: `esp:${ADMIN}`, label: "Panel Admin" },
      ],
    },
    ...paneles.map((panel) => ({
      grupo: panel.titulo,
      opciones: [
        { value: `panel:${panel.code}`, label: panel.simple ? panel.titulo : `${panel.titulo} (cualquier módulo)` },
        ...(panel.simple ? [] : panel.modulos.map((m) => ({ value: `mod:${m.code}`, label: m.nombre }))),
      ],
    })),
  ];
}

// Filtro para un chip de la tabla (null si el chip no filtra, ej. "Todo (administrador)").
export function filtroDeChip(code, paneles) {
  if (code === GLOBAL || code === ADMIN) return `esp:${code}`;
  return paneles.some((p) => p.code === code) ? `panel:${code}` : null;
}

// row: usuario de /api/admin/users (modules = asignados, access = los que puede abrir).
export function cumpleFiltroAcceso(filtro, row, paneles) {
  if (!filtro) {
    return true;
  }
  const set = new Set(row.access || []);
  if (filtro === "sin") {
    return !ROLES_ADMIN.includes(row.role_code) && !paneles.some((p) => accesoPanel(p, set)) && !set.has(ADMIN);
  }
  const [tipo, code] = filtro.split(":");
  if (tipo === "esp") {
    return code === GLOBAL ? (row.modules || []).includes(GLOBAL) : set.has(code);
  }
  if (tipo === "mod") {
    return set.has(code);
  }
  const panel = paneles.find((p) => p.code === code);
  return panel ? Boolean(accesoPanel(panel, set)) : set.has(code);
}
