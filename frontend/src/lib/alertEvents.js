// "The alerts may have changed": sent after this tab saves a reading, imports readings, acknowledges or reviews an
// alert, so the alert flag and its sound update at once instead of waiting for the next refresh.
// The other side (patient or doctor) sees the change at its next refresh (ALERT_REFRESH_MS).

const EVENT = "pulse:alerts-changed";
export const ALERT_REFRESH_MS = 10000;

export function alertsChanged() {
  if (typeof window !== "undefined") window.dispatchEvent(new Event(EVENT));
}

/** Calls `fn` now, on every change signal and every ALERT_REFRESH_MS. Returns the cleanup function. */
export function watchAlerts(fn) {
  let live = true;
  Promise.resolve().then(() => { if (live) fn(); });
  const timer = setInterval(fn, ALERT_REFRESH_MS);
  window.addEventListener(EVENT, fn);
  window.addEventListener("online", fn);
  return () => {
    live = false;
    clearInterval(timer);
    window.removeEventListener(EVENT, fn);
    window.removeEventListener("online", fn);
  };
}

/** Passes an API answer through and sends the change signal once it succeeded. */
export function signalling(promise) {
  return promise.then((value) => { alertsChanged(); return value; });
}

// Alert states as the flag shows them (AlertOut.status). "dismissed" never applies to severe/emergency alerts.
export const FLAG_STATUS = {
  open: { label: "En attente de confirmation du patient", tone: "active" },
  acknowledged: { label: "Confirmée par le patient — en attente du médecin", tone: "acknowledged" },
  reviewed: { label: "Examinée par le médecin — en attente de clôture", tone: "acknowledged" },
  resolved: { label: "Clôturée par le médecin", tone: "resolved" },
};

const RANK = { severe: 1, emergency: 2 };

/** Severe and emergency alerts not resolved yet, most severe then newest first. */
export function flaggedAlerts(alerts) {
  return (alerts ?? [])
    .filter((a) => RANK[a.level] && ["open", "acknowledged", "reviewed"].includes(a.status))
    .sort((a, b) => RANK[b.level] - RANK[a.level] || new Date(b.created_at) - new Date(a.created_at));
}

/** Items that ring: only alerts still waiting for the patient's confirmation. */
export function ringingItems(alerts) {
  return flaggedAlerts(alerts).filter((a) => a.status === "open").map((a) => ({ id: a.id, level: a.level }));
}
