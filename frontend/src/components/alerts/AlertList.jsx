import { LevelBadge, StatusBadge } from "../ui/Badge";
import Icon from "../ui/Icon";
import { formatDateTime } from "../../lib/format";

// Decorative edge; the level badge carries the meaning in text.
const BAR = { notice: "bg-level-notice", trend: "bg-level-trend" };

/**
 * Alerts (AlertOut[]). Reason and next step are the server's words, shown verbatim (English until the
 * clinician-reviewed translation exists). `renderActions(alert)` adds role-specific buttons.
 */
export default function AlertList({ alerts, timeZone, renderActions }) {
  return (
    <ul className="stagger space-y-3">
      {alerts.map((a) => (
        <li key={a.id} className={`relative overflow-hidden rounded-2xl border p-4 pl-5 transition-shadow hover:shadow-card ${
          a.level === "emergency" || a.level === "severe" ? "border-emergency/40 bg-level-severe-soft/50" : "border-line bg-surface"
        }`}>
          <span aria-hidden="true" className={`absolute inset-y-0 left-0 w-1 ${a.level === "emergency" || a.level === "severe" ? "bg-emergency" : BAR[a.level] ?? "bg-line"}`} />
          <div className="flex flex-wrap items-center gap-2">
            <LevelBadge level={a.level} persistent={a.persistent} />
            <StatusBadge status={a.status} />
            <span className="ml-auto inline-flex items-center gap-1 text-xs text-ink-subtle"><Icon name="clock" size={13} />{formatDateTime(a.created_at, timeZone)}</span>
          </div>
          <p className="mt-2 text-sm text-ink">{a.reason}</p>
          <p className="mt-1 text-sm font-medium text-ink">{a.next_step}</p>
          {a.resolution_note && (
            <p className="mt-2 rounded-lg bg-surface-muted px-3 py-2 text-sm text-ink-muted">
              Clôture : {a.resolution_note}
            </p>
          )}
          {renderActions && <div className="mt-3 flex flex-wrap gap-2">{renderActions(a)}</div>}
        </li>
      ))}
    </ul>
  );
}
