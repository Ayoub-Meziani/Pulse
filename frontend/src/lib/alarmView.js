// How the alarm is shown: "full" (red full screen), "bar" (slim red bar on top of the page) or "none".
// The patient cannot mute the alarm, so the full screen can always be reduced to the bar: the symptom check, the
// recheck timer and the call button stay reachable without the password. Something new (another alert, or a higher
// level) brings the full screen back. It never covers the emergency screen.

const RANK = { severe: 1, emergency: 2 };

/** What the person has seen when they pressed "Réduire": { [alertId]: rank }. */
export const reduceSnapshot = (items) => Object.fromEntries(items.map((i) => [i.id, RANK[i.level] ?? 0]));

/** Forget alerts that stopped ringing, so the same alert ringing again (reopened) shows the full screen again. */
export function pruneReduced(reduced, items) {
  if (!reduced) return reduced;
  const ringing = new Set(items.map((i) => i.id));
  const kept = Object.fromEntries(Object.entries(reduced).filter(([id]) => ringing.has(id)));
  return Object.keys(kept).length === Object.keys(reduced).length ? reduced : kept;
}

/** items = ringingItems(alerts); reduced = reduceSnapshot(...) or null; screenOpen = an emergency screen is open. */
export function alarmMode(items, reduced, screenOpen) {
  if (!items?.length) return "none";
  if (screenOpen) return "bar";
  return items.some((i) => (reduced?.[i.id] ?? 0) < (RANK[i.level] ?? 0)) ? "full" : "bar";
}
