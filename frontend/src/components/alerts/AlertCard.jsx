import Icon from "../ui/Icon";

// Variants map to the design tokens (docs/frontend/PULSE_FRONTEND_DESIGN_SYSTEM.md §2.2). The icon and the
// title carry the meaning too, never the colour alone.
const VARIANTS = {
  info: { box: "border-brand/25 bg-brand-soft", icon: "bg-surface text-brand shadow-card", title: "text-ink", text: "text-ink-muted", glyph: "info" },
  warning: { box: "border-level-notice/30 bg-level-notice-soft", icon: "bg-surface text-level-notice shadow-card", title: "text-level-notice", text: "text-level-notice", glyph: "alert" },
  critical: { box: "border-emergency/50 bg-level-severe-soft shadow-glow-alarm", icon: "bg-emergency text-white", title: "text-level-severe", text: "text-level-severe", glyph: "alert" },
};

export default function AlertCard({ title, message, variant = "info" }) {
  const style = VARIANTS[variant] ?? VARIANTS.info;
  return (
    <article role={variant === "critical" ? "alert" : "status"} className={`flex animate-fade-up gap-4 rounded-2xl border p-5 ${style.box}`}>
      <span className={`relative flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl ${style.icon}`}>
        {variant === "critical" && <span aria-hidden="true" className="absolute inset-0 animate-pulse-ring rounded-2xl bg-emergency" />}
        <Icon name={style.glyph} size={20} className="relative" />
      </span>
      <div className="min-w-0">
        <h3 className={`text-lg font-bold ${style.title}`}>{title}</h3>
        <p className={`mt-1 text-sm leading-6 ${style.text}`}>{message}</p>
      </div>
    </article>
  );
}
