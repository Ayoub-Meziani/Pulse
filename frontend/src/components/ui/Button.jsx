import { Link } from "react-router";

const BASE = "inline-flex min-h-11 items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold " +
  "transition-colors disabled:cursor-not-allowed disabled:opacity-60";

const VARIANTS = {
  primary: "bg-brand text-white hover:bg-brand-hover",
  secondary: "border border-line bg-surface text-ink hover:bg-surface-muted",
  ghost: "text-ink-muted hover:bg-surface-muted hover:text-ink",
  emergency: "bg-emergency text-white hover:bg-emergency-hover",
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
