import React, { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { toBlob } from "html-to-image";

// Componentes visuales compartidos por los modulos del Panel de Productividad.
// Solo presentacion: no cargan datos ni aplican reglas de negocio.

// breadcrumb: tramos previos de la ruta [{ label, to }]; por defecto, el Panel de Productividad.
export function PageHeader({ title, subtitle, actions, breadcrumb = [{ label: "Productividad", to: "/productividad" }] }) {
  return (
    <header className="pd-header">
      <div>
        <nav className="pd-breadcrumb" aria-label="Ruta">
          {breadcrumb.map((item) => (
            <React.Fragment key={item.to}>
              <Link to={item.to}>{item.label}</Link>
              <span aria-hidden="true">/</span>
            </React.Fragment>
          ))}
          <span>{title}</span>
        </nav>
        <h1 className="pd-title">{title}</h1>
        {subtitle && <p className="pd-subtitle">{subtitle}</p>}
      </div>
      {actions && <div className="pd-header-actions">{actions}</div>}
    </header>
  );
}

export function FilterBar({ children, actions, note }) {
  return (
    <section className="pd-card pd-filter-bar" aria-label="Filtros">
      <div className="pd-filter-grid">{children}</div>
      {actions && <div className="pd-filter-actions">{actions}</div>}
      {note && <div className="pd-filter-note">{note}</div>}
    </section>
  );
}

export function Field({ label, wide = false, children }) {
  return (
    <label className={`pd-field${wide ? " pd-field-wide" : ""}`}>
      <span className="pd-label">{label}</span>
      {children}
    </label>
  );
}

export function ViewTabs({ value, onChange, options }) {
  return (
    <div className="pd-tabs" role="tablist">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          role="tab"
          aria-selected={value === option.value}
          className={`pd-tab${value === option.value ? " active" : ""}`}
          onClick={() => onChange(option.value)}
        >
          {option.icon && <i className={`bi ${option.icon}`} aria-hidden="true" />}
          {option.label}
        </button>
      ))}
    </div>
  );
}

export function Segmented({ value, onChange, options }) {
  return (
    <div className="pd-segmented" role="group">
      {options.map((option) => (
        <button key={option.value} type="button" className={value === option.value ? "active" : undefined} aria-pressed={value === option.value} onClick={() => onChange(option.value)}>
          {option.label}
        </button>
      ))}
    </div>
  );
}

// Captura la tarjeta completa como PNG (tabla entera aunque tenga scroll, con su leyenda).
// Los elementos con la clase pd-no-export (los propios botones) quedan fuera de la imagen.
async function captureCard(node) {
  node.classList.add("pd-exporting");
  try {
    return await toBlob(node, {
      pixelRatio: 2,
      cacheBust: true,
      backgroundColor: window.getComputedStyle(node).backgroundColor || "#ffffff",
      filter: (element) => !element.classList?.contains("pd-no-export"),
    });
  } finally {
    node.classList.remove("pd-exporting");
  }
}

function ExportButtons({ targetRef, fileName }) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  function flash(text) {
    setMessage(text);
    window.setTimeout(() => setMessage(""), 2500);
  }

  async function run(action) {
    if (!targetRef.current || busy) {
      return;
    }
    setBusy(true);
    try {
      const blob = await captureCard(targetRef.current);
      if (!blob) {
        throw new Error("sin imagen");
      }
      await action(blob);
    } catch (err) {
      flash(action === copy ? "No se pudo copiar; usa Descargar PNG" : "No se pudo generar la imagen");
    } finally {
      setBusy(false);
    }
  }

  async function copy(blob) {
    // El portapapeles de imagenes solo funciona en https o localhost.
    if (!navigator.clipboard || typeof window.ClipboardItem === "undefined") {
      throw new Error("portapapeles no disponible");
    }
    await navigator.clipboard.write([new window.ClipboardItem({ "image/png": blob })]);
    flash("Imagen copiada");
  }

  async function download(blob) {
    const url = window.URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${fileName}.png`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.URL.revokeObjectURL(url);
  }

  return (
    <div className="pd-export-actions pd-no-export">
      {message && <span className="pd-small pd-muted">{message}</span>}
      <button type="button" className="pd-btn pd-btn-ghost pd-btn-sm" onClick={() => run(copy)} disabled={busy} title="Copiar la tabla como imagen">
        <i className="bi bi-clipboard-check" aria-hidden="true" /> Copiar imagen
      </button>
      <button type="button" className="pd-btn pd-btn-ghost pd-btn-sm" onClick={() => run(download)} disabled={busy} title="Descargar la tabla como PNG">
        <i className="bi bi-image" aria-hidden="true" /> Descargar PNG
      </button>
    </div>
  );
}

// Nombre de archivo para exportar: une las partes con "_" y deja solo caracteres seguros.
export function exportFileName(...parts) {
  return parts
    .filter((part) => part !== null && part !== undefined && String(part).trim() !== "")
    .map((part) => String(part).trim().normalize("NFD").replace(/\p{Diacritic}/gu, "").replace(/[^A-Za-z0-9+-]+/g, "-"))
    .join("_");
}

// exportName: si se indica, la tarjeta muestra los botones Copiar imagen / Descargar PNG
// y se usa como nombre del archivo (sin extension).
export function SectionCard({ title, description, actions, children, footer, bodyClassName = "pd-card-body", className = "", exportName }) {
  const cardRef = useRef(null);
  const hasHeading = Boolean(title || actions);
  return (
    <section ref={cardRef} className={`pd-card ${className}`.trim()}>
      {(hasHeading || exportName) && (
        <div className={`pd-card-header${hasHeading ? "" : " pd-card-header-tools pd-no-export"}`}>
          <div>
            {title && <h2 className="pd-section-title">{title}</h2>}
            {description && <p className="pd-section-desc">{description}</p>}
          </div>
          <div className="pd-card-header-actions">
            {actions}
            {exportName && <ExportButtons targetRef={cardRef} fileName={exportName} />}
          </div>
        </div>
      )}
      {bodyClassName ? <div className={bodyClassName}>{children}</div> : children}
      {footer && <div className="pd-card-footer">{footer}</div>}
    </section>
  );
}

export function KpiCard({ label, value, caption, icon }) {
  return (
    <div className="pd-card pd-kpi">
      <div className="pd-kpi-head">
        <span className="pd-kpi-label">{label}</span>
        {icon && <i className={`bi ${icon} pd-kpi-icon`} aria-hidden="true" />}
      </div>
      <div className="pd-kpi-value">{value}</div>
      {caption && <div className="pd-kpi-caption">{caption}</div>}
    </div>
  );
}

// items: [{ status: "success" | "warning" | "danger" | "neutral", label, range? }]
export function StatusLegend({ title = "Cumplimiento", items }) {
  return (
    <div className="pd-legend">
      <span className="pd-legend-title">{title}</span>
      {items.map((item) => (
        <span key={item.status + item.label} className="pd-legend-item">
          {item.range ? <span className={`pd-status pd-status-${item.status}`}>{item.range}</span> : <span className={`pd-dot pd-dot-${item.status}`} />}
          {item.label}
        </span>
      ))}
    </div>
  );
}

// PHOENIX y GRUPAL no son ejecutivos reales (cartera sin asignar / grupal): en las tablas van siempre al final.
export function isPhoenixOGrupal(nombre) {
  const valor = String(nombre || "").trim().toUpperCase();
  return valor === "PHOENIX" || valor === "GRUPAL";
}

// Deja PHOENIX y GRUPAL al final sin alterar el orden del resto de las filas.
export function phoenixGrupalAlFinal(rows, getNombre = (row) => row.ejecutivo) {
  const lista = rows || [];
  return [...lista.filter((row) => !isPhoenixOGrupal(getNombre(row))), ...lista.filter((row) => isPhoenixOGrupal(getNombre(row)))];
}

// Semaforo de cumplimiento de meta (carteras con meta). Recibe el % en escala 0-100 (100 = meta cumplida).
export function cumplimientoStatus(pct) {
  if (pct === null || pct === undefined || !Number.isFinite(Number(pct))) {
    return "neutral";
  }
  const num = Number(pct);
  if (num >= 100) {
    return "success";
  }
  if (num >= 80) {
    return "warning";
  }
  return "danger";
}

export function cumplimientoClass(pct) {
  return `pd-status pd-status-${cumplimientoStatus(pct)}`;
}

// Mismo formato que la leyenda de aporte (punto + nombre). Rangos: < 80% / 80% - 99,9% / >= 100%.
export const cumplimientoLegendItems = [
  { status: "danger", label: "Crítico" },
  { status: "warning", label: "En seguimiento" },
  { status: "success", label: "Cumplido" },
];

// Carteras de aporte (La Araucana, SC Temprana): el % es la parte del recupero total que aporta cada ejecutivo,
// no hay meta de 100%, asi que el color compara a los ejecutivos entre si (tercios: p33 / p66).
export const aporteLegendItems = [
  { status: "danger", label: "Aporte bajo" },
  { status: "warning", label: "Aporte medio" },
  { status: "success", label: "Aporte alto" },
];

export function LoadingState({ text = "Cargando..." }) {
  return (
    <div className="pd-state" role="status">
      <span className="spinner-border spinner-border-sm" aria-hidden="true" />
      {text}
    </div>
  );
}

export function EmptyRow({ colSpan, text = "Sin datos para los filtros seleccionados." }) {
  return (
    <tr>
      <td colSpan={colSpan} className="pd-empty">{text}</td>
    </tr>
  );
}

export function MetasButton({ onClick }) {
  return (
    <button type="button" className="pd-btn pd-btn-secondary" onClick={onClick}>
      <i className="bi bi-info-circle" aria-hidden="true" /> Metas
    </button>
  );
}

// Panel lateral generico (se cierra con Escape o clic fuera). footer: acciones fijas al pie (ej. Guardar / Cancelar).
export function Drawer({ open, onClose, title, subtitle, wide = false, footer, children }) {
  useEffect(() => {
    if (!open) {
      return undefined;
    }
    function onKeyDown(event) {
      if (event.key === "Escape") {
        onClose();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) {
    return null;
  }
  return (
    <>
      <div className="pd-drawer-backdrop" onClick={onClose} />
      <aside className={`pd-drawer${wide ? " pd-drawer-wide" : ""}`} role="dialog" aria-modal="true" aria-labelledby="pd-drawer-title">
        <div className="pd-drawer-header">
          <div>
            <h2 id="pd-drawer-title" className="pd-section-title">{title}</h2>
            {subtitle && <p className="pd-section-desc">{subtitle}</p>}
          </div>
          <button type="button" className="btn-close" aria-label="Cerrar" onClick={onClose} />
        </div>
        <div className="pd-drawer-body">{children}</div>
        {footer && <div className="pd-drawer-footer">{footer}</div>}
      </aside>
    </>
  );
}

// Panel lateral de metas (mismo formato que Itau Vencida).
export function MetasDrawer({ title = "Metas del mes", ...props }) {
  return <Drawer title={title} {...props} />;
}

// Bloque con encabezado de color dentro del panel de metas.
export function MetasBlock({ title, note, accent = "consumo", children }) {
  return (
    <div className={`iv-drawer-block iv-accent-${accent}`}>
      <div className="iv-drawer-block-head">
        <span>{title}</span>
        {note && <span className="iv-drawer-peso">{note}</span>}
      </div>
      {children}
    </div>
  );
}

export function Pagination({ summary, onPrev, onNext, prevDisabled, nextDisabled }) {
  return (
    <>
      <span>{summary}</span>
      <div className="d-flex gap-2">
        <button type="button" className="pd-btn pd-btn-secondary pd-btn-sm" onClick={onPrev} disabled={prevDisabled}>
          <i className="bi bi-chevron-left" aria-hidden="true" /> Anterior
        </button>
        <button type="button" className="pd-btn pd-btn-secondary pd-btn-sm" onClick={onNext} disabled={nextDisabled}>
          Siguiente <i className="bi bi-chevron-right" aria-hidden="true" />
        </button>
      </div>
    </>
  );
}
