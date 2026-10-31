// Client-side mirror of the server's Q5 rule, used only to decide whether to show the form.
// The server stays the authority (409 for anything else).

/** True when the server would accept a dismissal: notice alerts that are open or acknowledged. */
export function canDismiss(alert) {
  return alert.level === "notice" && (alert.status === "open" || alert.status === "acknowledged");
}
