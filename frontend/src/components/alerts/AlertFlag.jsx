import { FLAG_STATUS } from "../../lib/alertEvents";
import { formatDateTime, originOf } from "../../lib/format";
import Icon from "../ui/Icon";

const TITLE = { emergency: "URGENCE", severe: "TENSION TRÈS ÉLEVÉE" };

/**
 * The persistent alert flag: level, reading, time, origin and status. It stays until the doctor resolves the alert,
 * whatever the sound does. The colour changes once the patient has confirmed, so "waiting" and "seen" never look alike.
 */
export default function AlertFlag({ alert, reading, timeZone, who, children }) {
  const status = FLAG_STATUS[alert.status] ?? { label: alert.status, tone: "acknowledged" };
  const waiting = status.tone === "active";
  const origin = reading ? originOf(reading) : null;
  return (
    <section role="alert" aria-label={`${TITLE[alert.level] ?? "Alerte"} ${who ?? ""}`}
      className={`rounded-2xl border-4 p-4 sm:p-5 ${waiting ? "border-emergency bg-level-severe-soft" : "border-warning bg-warning-soft"}`}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <Icon name="alert" size={28} className={waiting ? "text-emergency" : "text-warning"} />
        <p className={`text-xl font-extrabold tracking-wide sm:text-2xl ${waiting ? "text-emergency" : "text-warning"}`}>
          {TITLE[alert.level] ?? "ALERTE"}{who ? ` — ${who}` : ""}
        </p>
        <span className={`ml-auto rounded-full px-3 py-1 text-sm font-bold ${waiting ? "bg-emergency text-white" : "bg-surface text-ink"}`}>
          {status.label}
        </span>
      </div>
      <p className="mt-2 text-lg font-semibold text-ink">
        {reading
          ? <><span className="tnum">{reading.systolic}/{reading.diastolic} mmHg</span>{" "}
            <span className="text-base font-normal text-ink-muted">· {formatDateTime(reading.measured_at, timeZone)} · {origin.label}</span></>
          : <span className="text-base font-normal">Signes d'alerte déclarés · {formatDateTime(alert.created_at, timeZone)}</span>}
      </p>
      {alert.next_step && <p className="mt-1 text-sm font-medium text-ink">{alert.next_step}</p>}
      {children && <div className="mt-3">{children}</div>}
    </section>
  );
}
