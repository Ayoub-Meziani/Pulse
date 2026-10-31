import Icon from "./Icon";

export function Loading({ label = "Chargement…" }) {
  return (
    <div role="status" className="px-1 py-6">
      <div className="space-y-2.5" aria-hidden="true">
        {["w-3/4", "w-full", "w-2/3"].map((w) => (
          <span key={w} className={`block h-3 rounded-full ${w} animate-shimmer bg-[linear-gradient(90deg,var(--color-surface-muted),var(--color-line),var(--color-surface-muted))] bg-size-[200%_100%]`} />
        ))}
      </div>
      <p className="mt-3 text-sm text-ink-muted">{label}</p>
    </div>
  );
}

/** Error of one section; the rest of the page keeps working. Messages never expose server internals. */
export function ErrorState({ what, error, onRetry }) {
  const forbidden = error?.status === 403;
  const offline = error?.code === "network_error" || error?.status >= 500;
  const text = forbidden
    ? `Vous n'avez pas accès à ${what}.`
    : offline
      ? `Impossible de charger ${what} : le serveur ne répond pas.`
      : `Impossible de charger ${what}.`;
  return (
    <div role="alert" className="flex animate-fade-up flex-wrap items-center gap-3 rounded-2xl border border-danger/25 bg-danger-soft px-4 py-3 text-sm text-danger">
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-surface/70">
        <Icon name="alert" size={18} />
      </span>
      <span className="min-w-0 flex-1">{text}</span>
      {onRetry && !forbidden && (
        <button type="button" onClick={onRetry} className="inline-flex min-h-11 items-center gap-1.5 rounded-lg px-2 font-semibold underline underline-offset-2 hover:bg-surface/60">
          <Icon name="refresh" size={16} />
          Réessayer
        </button>
      )}
    </div>
  );
}

export function EmptyState({ icon = "info", title, children, action }) {
  return (
    <div className="flex animate-fade-up flex-col items-center rounded-2xl border border-dashed border-line bg-surface/60 px-5 py-10 text-center">
      <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-soft text-brand">
        <Icon name={icon} />
      </span>
      <p className="mt-4 font-semibold text-ink">{title}</p>
      {children && <p className="mt-1 max-w-md text-sm text-ink-muted">{children}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

/** Renders loading / error / content for one useResource() result. */
export function Section({ state, what, children }) {
  if (state.status === "loading") return <Loading />;
  if (state.status === "error") return <ErrorState what={what} error={state.error} onRetry={state.retry} />;
  return children(state.data);
}
