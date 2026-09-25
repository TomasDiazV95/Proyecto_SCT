import { Link } from "react-router-dom";

// Componentes visuales compartidos por los modulos del Panel de Productividad.
// Solo presentacion: no cargan datos ni aplican reglas de negocio.

export function PageHeader({ title, subtitle, actions }) {
  return (
    <header className="pd-header">
      <div>
        <nav className="pd-breadcrumb" aria-label="Ruta">
          <Link to="/productividad">Productividad</Link>
          <span aria-hidden="true">/</span>
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

export function SectionCard({ title, description, actions, children, footer, bodyClassName = "pd-card-body", className = "" }) {
  return (
    <section className={`pd-card ${className}`.trim()}>
      {(title || actions) && (
        <div className="pd-card-header">
          <div>
            {title && <h2 className="pd-section-title">{title}</h2>}
            {description && <p className="pd-section-desc">{description}</p>}
          </div>
          {actions}
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

export const relativeLegendItems = [
  { status: "danger", label: "Bajo" },
  { status: "warning", label: "Esperado" },
  { status: "success", label: "Sobre lo esperado" },
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
