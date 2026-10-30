import Icon from "./Icon";

export function Loading({ label = "Chargement…" }) {
  return (
    <div role="status" className="flex items-center gap-3 px-1 py-6 text-sm text-ink-muted">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-line border-t-brand" aria-hidden="true" />
      {label}
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
    <div role="alert" className="flex flex-wrap items-center gap-3 rounded-xl border border-danger/25 bg-danger-soft px-4 py-3 text-sm text-danger">
      <Icon name="alert" size={18} />
      <span className="min-w-0 flex-1">{text}</span>
      {onRetry && !forbidden && (
        <button type="button" onClick={onRetry} className="font-semibold underline underline-offset-2">
          Réessayer
        </button>
      )}
    </div>
  );
}

export function EmptyState({ icon = "info", title, children, action }) {
  return (
    <div className="flex flex-col items-center rounded-xl border border-dashed border-line bg-canvas px-5 py-8 text-center">
      <span className="flex h-10 w-10 items-center justify-center rounded-full bg-surface text-ink-subtle">
        <Icon name={icon} />
      </span>
      <p className="mt-3 font-medium text-ink">{title}</p>
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
