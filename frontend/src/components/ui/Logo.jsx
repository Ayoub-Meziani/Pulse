// PULSE mark: a heart outline crossed by a pulse line. Same drawing as public/favicon.svg.
export function LogoMark({ size = 32, className = "" }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" className={className} aria-hidden="true">
      <rect width="32" height="32" rx="8" fill="#0b5cad" />
      <path
        d="M16 25s-8.5-5.1-8.5-11.2A4.6 4.6 0 0 1 16 11.4a4.6 4.6 0 0 1 8.5 2.4C24.5 19.9 16 25 16 25z"
        fill="none"
        stroke="#ffffff"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      <path d="M8 16.2h4l1.6-3 2.6 5.6 1.8-3.4H24" fill="none" stroke="#ffffff" strokeWidth="1.8"
        strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export default function Logo({ inverse = false, size = 32 }) {
  return (
    <span className="inline-flex items-center gap-2.5">
      <LogoMark size={size} />
      <span className={`text-lg font-bold tracking-[0.18em] ${inverse ? "text-white" : "text-ink"}`}>PULSE</span>
    </span>
  );
}
