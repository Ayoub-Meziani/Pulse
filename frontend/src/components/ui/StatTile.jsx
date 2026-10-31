import Icon from "./Icon";

const TONES = {
  plain: "card rounded-2xl border border-line/70 bg-surface shadow-card",
  night: "card card-night rounded-2xl border border-white/10 bg-linear-to-br from-night to-night-2 text-white shadow-lift",
  // Simulated values: dashed violet, like the simulated badge. The page still says "simulé" in text.
  sim: "card rounded-2xl border border-dashed border-sim/50 bg-sim-soft",
};

const CHIP = {
  plain: "bg-brand-soft text-brand",
  night: "bg-white/10 text-glow",
  sim: "bg-surface text-sim",
};

/** One key figure: big tabular value, small unit, label, optional hint and icon. */
export default function StatTile({ label, value, unit, hint, icon, tone = "plain", className = "" }) {
  const t = TONES[tone] ? tone : "plain";
  return (
    <div className={`${TONES[t]} p-4 sm:p-5 ${className}`}>
      <div className="flex items-start justify-between gap-3">
        <p className="text-xs font-semibold uppercase tracking-wider text-ink-muted">{label}</p>
        {icon && (
          <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-xl ${CHIP[t]}`}>
            <Icon name={icon} size={16} />
          </span>
        )}
      </div>
      <p className="mt-2 flex flex-wrap items-baseline gap-x-1.5">
        <span className="tnum text-3xl font-extrabold tracking-tight text-ink">{value}</span>
        {unit && <span className="text-sm font-medium text-ink-muted">{unit}</span>}
      </p>
      {hint && <p className="mt-1 text-xs text-ink-subtle">{hint}</p>}
    </div>
  );
}
