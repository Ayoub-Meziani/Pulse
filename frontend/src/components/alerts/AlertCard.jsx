import Icon from "../ui/Icon";

// Variants map to the design tokens (docs/frontend/PULSE_FRONTEND_DESIGN_SYSTEM.md §2.2). The icon and the
// title carry the meaning too, never the colour alone.
const VARIANTS = {
  info: { box: "border-brand/25 bg-brand-soft", icon: "bg-surface text-brand", title: "text-ink", text: "text-ink-muted", glyph: "info" },
  warning: { box: "border-level-notice/30 bg-level-notice-soft", icon: "bg-surface text-level-notice", title: "text-level-notice", text: "text-level-notice", glyph: "alert" },
  critical: { box: "border-emergency/50 bg-level-severe-soft", icon: "bg-emergency text-white", title: "text-level-severe", text: "text-level-severe", glyph: "alert" },
};

export default function AlertCard({ title, message, variant = "info" }) {
  const style = VARIANTS[variant] ?? VARIANTS.info;
  return (
    <article role={variant === "critical" ? "alert" : "status"} className={`flex gap-4 rounded-2xl border p-5 ${style.box}`}>
      <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full ${style.icon}`}>
        <Icon name={style.glyph} size={20} />
      </span>
      <div className="min-w-0">
        <h3 className={`font-semibold ${style.title}`}>{title}</h3>
        <p className={`mt-1 text-sm leading-6 ${style.text}`}>{message}</p>
      </div>
    </article>
  );
}
