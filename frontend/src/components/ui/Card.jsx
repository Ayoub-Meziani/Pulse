import Icon from "./Icon";

// `card` is a hook for the forced-colours border; `card-night` flips the ink/line tokens (index.css).
const VARIANTS = {
  plain: "card rounded-2xl border border-line/70 bg-surface shadow-card",
  elevated: "card rounded-2xl border border-line/70 bg-surface shadow-lift",
  glass: "card glass rounded-2xl shadow-card",
  night: "card card-night rounded-3xl border border-white/10 bg-linear-to-br from-night to-night-2 text-white shadow-lift",
};

export function Card({ as: Tag = "section", variant = "plain", className = "", children, ...rest }) {
  return (
    <Tag className={`${VARIANTS[variant] ?? VARIANTS.plain} ${className}`} {...rest}>
      {children}
    </Tag>
  );
}

export function CardHeader({ title, subtitle, action, id, icon }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3 px-5 pt-5 sm:px-6">
      <div className="flex min-w-0 items-start gap-3">
        {icon && (
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-brand-soft text-brand">
            <Icon name={icon} size={18} />
          </span>
        )}
        <div className="min-w-0">
          <h2 id={id} className="text-base font-semibold text-ink">{title}</h2>
          {subtitle && <p className="mt-0.5 text-sm text-ink-muted">{subtitle}</p>}
        </div>
      </div>
      {action}
    </div>
  );
}

export function CardBody({ className = "", children }) {
  return <div className={`px-5 pb-5 pt-4 sm:px-6 ${className}`}>{children}</div>;
}

/** Page title block used at the top of every screen. */
export function PageHeader({ eyebrow, title, subtitle, action }) {
  return (
    <div className="flex animate-fade-up flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        {eyebrow && (
          <p className="inline-flex rounded-full bg-brand-soft px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wider text-brand">
            {eyebrow}
          </p>
        )}
        <h1 className="mt-2 text-3xl font-extrabold tracking-tight text-ink">{title}</h1>
        {subtitle && <p className="mt-1 text-ink-muted">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}
