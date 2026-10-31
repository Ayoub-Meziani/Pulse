import { useId } from "react";

// PULSE mark: a heart outline crossed by a pulse line, on a blue gradient. Same drawing as public/favicon.svg.
// `animated`: the heart beats and the pulse line redraws (both stop under reduced motion, fully drawn).
export function LogoMark({ size = 32, animated = false, className = "" }) {
  const gradient = useId();
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" className={className} aria-hidden="true">
      <defs>
        <linearGradient id={gradient} x1="0" y1="0" x2="32" y2="32" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#1d4ed8" />
          <stop offset="1" stopColor="#0284c7" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="8" fill={`url(#${gradient})`} />
      <path
        d="M16 25s-8.5-5.1-8.5-11.2A4.6 4.6 0 0 1 16 11.4a4.6 4.6 0 0 1 8.5 2.4C24.5 19.9 16 25 16 25z"
        fill="none"
        stroke="#ffffff"
        strokeWidth="1.8"
        strokeLinejoin="round"
        className={animated ? "animate-heartbeat" : undefined}
        style={animated ? { transformBox: "fill-box", transformOrigin: "center" } : undefined}
      />
      <path d="M8 16.2h4l1.6-3 2.6 5.6 1.8-3.4H24" fill="none" stroke="#ffffff" strokeWidth="1.8"
        strokeLinecap="round" strokeLinejoin="round" pathLength="100"
        strokeDasharray={animated ? "100" : undefined} className={animated ? "animate-ecg" : undefined} />
    </svg>
  );
}

export default function Logo({ inverse = false, size = 32, animated = false }) {
  return (
    <span className="inline-flex items-center gap-2.5">
      <LogoMark size={size} animated={animated} />
      <span className={`text-lg font-extrabold tracking-[0.18em] ${inverse ? "text-white" : "text-ink"}`}>PULSE</span>
    </span>
  );
}
