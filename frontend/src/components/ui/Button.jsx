import { Link } from "react-router";

const BASE = "inline-flex min-h-11 items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold " +
  "transition-[color,background-color,border-color,box-shadow,transform,opacity] duration-200 " +
  "disabled:cursor-not-allowed disabled:opacity-60";

const VARIANTS = {
  primary: "btn-shine bg-linear-to-br from-brand to-brand-hover text-white shadow-sm hover:shadow-glow-brand enabled:active:scale-[.98] [a&]:active:scale-[.98]",
  secondary: "border border-line bg-surface text-ink shadow-sm hover:border-line-strong hover:bg-surface-muted",
  ghost: "text-ink-muted hover:bg-surface-muted hover:text-ink",
  emergency: "btn-shine bg-linear-to-br from-emergency to-alarm-2 text-white shadow-sm hover:shadow-glow-alarm enabled:active:scale-[.98] [a&]:active:scale-[.98]",
  // On a red background (the alarm).
  inverse: "bg-white text-alarm-2 shadow-sm hover:bg-white/90 enabled:active:scale-[.98] [a&]:active:scale-[.98]",
  "outline-inverse": "border border-white/60 bg-transparent text-white hover:bg-white/10",
};

function buttonClass(variant = "primary", extra = "") {
  return `${BASE} ${VARIANTS[variant] ?? VARIANTS.primary} ${extra}`;
}

export default function Button({ variant, className, type = "button", ...rest }) {
  return <button type={type} className={buttonClass(variant, className)} {...rest} />;
}

export function ButtonLink({ variant, className, ...rest }) {
  return <Link className={buttonClass(variant, className)} {...rest} />;
}
