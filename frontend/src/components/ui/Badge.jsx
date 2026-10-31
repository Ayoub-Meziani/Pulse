import Icon from "./Icon";
import { ALERT_LEVEL, ALERT_STATUS, originOf, VALIDATION } from "../../lib/format";

const TONES = {
  neutral: "border-line bg-surface-muted text-ink-muted",
  brand: "border-brand/30 bg-brand-soft text-brand",
  success: "border-success/30 bg-success-soft text-success",
  warning: "border-warning/30 bg-warning-soft text-warning",
  danger: "border-danger/30 bg-danger-soft text-danger",
  sim: "border-dashed border-sim/50 bg-sim-soft text-sim",
  wear: "border-wear/30 bg-wear-soft text-wear",
  ml: "border-dashed border-ml/50 bg-ml-soft text-ml",
  notice: "border-level-notice/25 bg-level-notice-soft text-level-notice",
  trend: "border-level-trend/25 bg-level-trend-soft text-level-trend",
  severe: "border-emergency/60 bg-level-severe-soft text-level-severe",
  emergency: "border-emergency bg-emergency text-white",
};

/** `dot` adds a small pulsing dot before the text (the ring only shows when motion is allowed). */
export default function Badge({ tone = "neutral", icon, dot = false, children, className = "" }) {
  return (
    <span className={`badge inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-xs font-semibold ${TONES[tone] ?? TONES.neutral} ${className}`}>
      {dot && (
        <span className="relative mr-0.5 flex h-2 w-2" aria-hidden="true">
          <span className="absolute inset-0 animate-pulse-ring rounded-full bg-current" />
          <span className="relative h-2 w-2 rounded-full bg-current" />
        </span>
      )}
      {icon && <Icon name={icon} size={13} />}
      {children}
    </span>
  );
}

/** Where a reading comes from (source + provenance). Simulated and estimated never look like measured. */
export function OriginBadge({ reading }) {
  const o = originOf(reading);
  return <Badge tone={o.tone} icon={o.icon}>{o.label}</Badge>;
}

/** Validation by the database (pulse-v1). Valid readings get no badge. */
export function ValidationBadge({ status }) {
  const v = VALIDATION[status];
  return v ? <Badge tone={v.tone} icon="info">{v.label}</Badge> : null;
}

export function LevelBadge({ level, persistent = false }) {
  const l = ALERT_LEVEL[level] ?? { label: level, tone: "neutral", icon: "info" };
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      <Badge tone={l.tone} icon={l.icon}>{l.label}</Badge>
      {persistent && <Badge tone="severe">Persistante</Badge>}
    </span>
  );
}

export function StatusBadge({ status }) {
  const s = ALERT_STATUS[status] ?? { label: status, tone: "neutral" };
  return <Badge tone={s.tone}>{s.label}</Badge>;
}
