import { useState } from "react";
import { getAlertEvents } from "../../api/patient";
import { ALERT_EVENT_ACTOR, ALERT_LEVEL, ALERT_STATUS, formatDateTime } from "../../lib/format";
import { useResource } from "../../lib/useResource";
import Button from "../ui/Button";
import { ErrorState, Loading } from "../ui/States";

function describe(e) {
  const status = (s) => ALERT_STATUS[s]?.label ?? s;
  if (e.kind === "created") return `Alerte créée (${ALERT_LEVEL[e.level]?.label ?? e.level})`;
  if (e.kind === "level_raised") return `Niveau relevé : ${ALERT_LEVEL[e.level]?.label ?? e.level}`;
  if (e.kind === "measurement_attached") return "Mesure ajoutée à cet épisode";
  return `${status(e.from_status)} → ${status(e.to_status)}`;
}

function Events({ alertId, timeZone }) {
  const events = useResource((signal) => getAlertEvents(alertId, { signal }), `ae:${alertId}`);
  if (events.status === "loading") return <Loading />;
  if (events.status === "error") return <ErrorState what="l'historique" error={events.error} onRetry={events.retry} />;
  return (
    <ol className="space-y-1.5 border-l-2 border-line pl-4 text-sm">
      {events.data.map((e, i) => (
        <li key={i}>
          <span className="tnum text-ink-muted">{formatDateTime(e.at, timeZone)}</span> · <span className="text-ink">{describe(e)}</span>
          <span className="text-ink-subtle"> · {ALERT_EVENT_ACTOR[e.actor_role] ?? e.actor_role}</span>
          {e.note && <span className="text-ink-muted"> : « {e.note} »</span>}
        </li>
      ))}
    </ol>
  );
}

/** Read-only history of one alert (GET /alerts/{id}/events), loaded on demand. */
export default function AlertTimeline({ alertId, timeZone }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="w-full space-y-2">
      <Button variant="ghost" onClick={() => setOpen(!open)}>{open ? "Masquer l'historique" : "Historique"}</Button>
      {open && <Events alertId={alertId} timeZone={timeZone} />}
    </div>
  );
}
