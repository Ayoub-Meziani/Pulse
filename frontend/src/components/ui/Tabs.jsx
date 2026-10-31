import { useId } from "react";

const LIST = {
  underline: "flex min-w-max gap-1 border-b border-line",
  segmented: "inline-flex min-w-max gap-1 rounded-xl bg-surface-muted p-1",
};

const TAB = {
  underline: "relative min-h-11 whitespace-nowrap px-3.5 text-sm font-semibold text-ink-muted transition-colors " +
    "hover:text-ink aria-selected:text-brand after:absolute after:inset-x-2 after:-bottom-px after:h-0.5 " +
    "after:rounded-full after:bg-brand after:scale-x-0 after:transition-transform after:duration-300 " +
    "after:ease-(--ease-out-expo) aria-selected:after:scale-x-100",
  segmented: "min-h-11 whitespace-nowrap rounded-lg px-3.5 text-sm font-semibold text-ink-muted transition " +
    "hover:text-ink aria-selected:bg-surface aria-selected:text-ink aria-selected:shadow-card",
};

/**
 * Accessible tabs: items = [[key, label]] or [[key, label, count]]. Roving tabindex; ArrowLeft/Right, Home, End
 * move focus and selection. The page renders the panel:
 * <div role="tabpanel" id={`${idPrefix}-panel`} aria-labelledby={`${idPrefix}-tab-${value}`}>
 */
export default function Tabs({ items, value, onChange, label, variant = "underline", idPrefix }) {
  const auto = useId();
  const prefix = idPrefix ?? auto;
  const kind = LIST[variant] ? variant : "underline";

  function onKeyDown(event) {
    const keys = items.map(([key]) => key);
    const i = keys.indexOf(value);
    const target = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: keys.length - 1 }[event.key];
    if (target === undefined) return;
    event.preventDefault();
    const key = keys[(target + keys.length) % keys.length];
    onChange(key);
    document.getElementById(`${prefix}-tab-${key}`)?.focus();
  }

  return (
    <div className="overflow-x-auto px-3 py-1 [mask-image:linear-gradient(to_right,transparent,#000_12px,#000_calc(100%-12px),transparent)]">
      <div role="tablist" aria-label={label} className={LIST[kind]} onKeyDown={onKeyDown}>
        {items.map(([key, text, count]) => {
          const selected = key === value;
          return (
            <button key={key} type="button" role="tab" id={`${prefix}-tab-${key}`} aria-selected={selected}
              aria-controls={`${prefix}-panel`} tabIndex={selected ? 0 : -1} onClick={() => onChange(key)}
              className={TAB[kind]}>
              {text}
              {count != null && (
                <span className="tnum ml-1.5 rounded-full bg-surface-muted px-1.5 py-0.5 text-xs text-ink-muted">{count}</span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
