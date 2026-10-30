export function Card({ as: Tag = "section", className = "", children, ...rest }) {
  return (
    <Tag className={`rounded-2xl border border-line bg-surface shadow-[0_1px_2px_rgba(16,24,40,0.04)] ${className}`} {...rest}>
      {children}
    </Tag>
  );
}

export function CardHeader({ title, subtitle, action, id }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3 px-5 pt-5 sm:px-6">
      <div className="min-w-0">
        <h2 id={id} className="text-base font-semibold text-ink">{title}</h2>
        {subtitle && <p className="mt-0.5 text-sm text-ink-muted">{subtitle}</p>}
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
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        {eyebrow && <p className="text-xs font-semibold uppercase tracking-wider text-brand">{eyebrow}</p>}
        <h1 className="mt-1 text-2xl font-bold tracking-tight text-ink sm:text-[1.75rem]">{title}</h1>
        {subtitle && <p className="mt-1 text-ink-muted">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}
