import { FLAG_STATUS } from "../../lib/alertEvents";
import { formatDateTime, originOf } from "../../lib/format";
import Badge from "../ui/Badge";
import Icon from "../ui/Icon";
import { StatusChip } from "./AlarmOverlay";

const TITLE = { emergency: "URGENCE", severe: "TENSION TRÈS ÉLEVÉE" };

/**
 * The persistent alert flag: level, reading, time, origin and status. It stays until the doctor resolves the alert,
 * whatever the sound does. Waiting for the patient = red with a pulsing "En attente…" chip; confirmed = amber, so
 * "waiting" and "seen" never look alike (and the status is always written out).
 */
export default function AlertFlag({ alert, reading, timeZone, who, children }) {
  const status = FLAG_STATUS[alert.status] ?? { label: alert.status, tone: "acknowledged" };
  const waiting = status.tone === "active";
  const origin = reading ? originOf(reading) : null;
  return (
    <section role="alert" aria-label={`${TITLE[alert.level] ?? "Alerte"} ${who ?? ""}`}
      className={`card animate-fade-up rounded-2xl p-4 sm:p-5 ${waiting
        ? "alarm bg-linear-to-br from-alarm-3 via-alarm-2 to-alarm-1 text-white shadow-glow-alarm"
        : "border-2 border-warning/60 bg-warning-soft text-ink shadow-card"}`}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${waiting ? "bg-white text-alarm-2" : "bg-warning text-white"}`}>
          <Icon name="alert" size={22} />
        </span>
        <p className={`text-xl font-extrabold tracking-wide sm:text-2xl ${waiting ? "text-white" : "text-warning"}`}>
          {TITLE[alert.level] ?? "ALERTE"}{who ? ` — ${who}` : ""}
        </p>
        <span className="ml-auto">
          {waiting ? <StatusChip>{status.label}</StatusChip> : <Badge tone="warning" icon="check" className="text-sm">{status.label}</Badge>}
        </span>
      </div>
      <p className={`mt-3 text-lg font-semibold ${waiting ? "text-white" : "text-ink"}`}>
        {reading
          ? <><span className="tnum">{reading.systolic}/{reading.diastolic} mmHg</span>{" "}
            <span className={`text-base font-normal ${waiting ? "text-white/85" : "text-ink-muted"}`}>· {formatDateTime(reading.measured_at, timeZone)} · {origin.label}</span></>
          : <span className="text-base font-normal">Signes d'alerte déclarés · {formatDateTime(alert.created_at, timeZone)}</span>}
      </p>
      {alert.next_step && <p className={`mt-1 text-sm font-medium ${waiting ? "text-white/90" : "text-ink"}`}>{alert.next_step}</p>}
      {children && <div className="mt-3">{children}</div>}
    </section>
  );
}
