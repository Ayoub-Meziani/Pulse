import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { useDialog } from "../../lib/useDialog";
import { LogoMark } from "../ui/Logo";
import Button from "../ui/Button";
import Icon from "../ui/Icon";

// The red full-screen alarm and its minimised bar. The alarm never traps anyone: "Réduire" (or Escape) always turns
// it into the bar, which keeps the page usable; the sound goes on until the alert is confirmed or muted.

const RING_DELAYS = ["0s", "0.66s", "1.33s"];
const PATIENT_HINT = "Réduire pour continuer sur la page (symptômes, nouvelle mesure). Le son continue.";

/** White status chip with a pulsing dot, readable on red. */
export function StatusChip({ children }) {
  return (
    <span className="badge inline-flex items-center gap-2 rounded-full bg-white px-3 py-1 text-sm font-bold text-alarm-2">
      <span className="relative flex h-2.5 w-2.5" aria-hidden="true">
        <span className="absolute inset-0 animate-pulse-ring rounded-full bg-current" />
        <span className="relative h-2.5 w-2.5 rounded-full bg-current" />
      </span>
      {children}
    </span>
  );
}

/** The big alert icon with its rings (decoration). */
export function AlarmIcon({ size = 88 }) {
  return (
    <span className="relative flex shrink-0 items-center justify-center" style={{ width: size, height: size }} aria-hidden="true">
      {RING_DELAYS.map((d) => (
        <span key={d} className="absolute inset-0 animate-pulse-ring rounded-full bg-white/30" style={{ animationDelay: d }} />
      ))}
      <span className="relative flex h-full w-full items-center justify-center rounded-full bg-white text-alarm-2 shadow-lift">
        <Icon name="alert" size={Math.round(size * 0.46)} strokeWidth={2.4} />
      </span>
    </span>
  );
}

export function AlarmOverlay({ titleId, readingId, onReduce, children, header, hint = PATIENT_HINT }) {
  const ref = useRef(null);
  useDialog(ref, true, onReduce);  // Escape reduces, it never dismisses

  // The browser bar turns red too while the alarm is open.
  useEffect(() => {
    const meta = document.querySelector('meta[name="theme-color"]');
    if (!meta) return undefined;
    const before = meta.content;
    meta.content = "#8e1212";
    return () => { meta.content = before; };
  }, []);

  return createPortal(
    <div ref={ref} role="alertdialog" aria-modal="true" aria-labelledby={titleId} aria-describedby={readingId} tabIndex={-1}
      className="alarm fixed inset-0 z-60 animate-scale-in overflow-y-auto overscroll-contain bg-alarm text-white outline-none">
      <div aria-hidden="true" className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute inset-0 bg-alarm-3 opacity-30 animate-breathe" />
        <div className="absolute left-1/2 top-1/3 h-[32rem] w-[32rem] -translate-x-1/2 -translate-y-1/2">
          {RING_DELAYS.map((d) => (
            <span key={d} className="absolute inset-0 animate-pulse-ring rounded-full border-2 border-white/20" style={{ animationDelay: d }} />
          ))}
        </div>
      </div>

      <div className="relative mx-auto max-w-6xl px-4 py-4 sm:px-6 sm:py-6 lg:px-8">
        <header className="flex flex-wrap items-center gap-3">
          <LogoMark size={36} animated />
          <p className="text-sm font-extrabold uppercase tracking-[0.18em]">PULSE · Alarme</p>
          <div className="order-last w-full sm:order-none sm:w-auto sm:flex-1">{header}</div>
          <Button variant="outline-inverse" onClick={onReduce} aria-keyshortcuts="Escape" className="ml-auto sm:ml-0">
            <Icon name="minimize" size={18} />Réduire
          </Button>
        </header>
        <p className="mt-2 text-sm text-white/85 sm:text-right">{hint}</p>
        <div className="mt-6 pb-8">{children}</div>
      </div>
    </div>,
    document.body,
  );
}

/** The minimised alarm: a sticky red strip at the top of <main> (in flow, never fixed). */
export function AlarmBar({ title, detail, ago, onExpand, children }) {
  return (
    <div className="alarm alarm-bar sticky top-(--header-h) z-10 mb-6 overflow-hidden rounded-2xl bg-linear-to-r from-alarm-1 via-alarm-2 to-alarm-3 px-4 py-2.5 text-white shadow-glow-alarm sm:px-5">
      <div className="flex items-center gap-3">
        <span className="relative flex h-3 w-3 shrink-0" aria-hidden="true">
          <span className="absolute inset-0 animate-pulse-ring rounded-full bg-white" />
          <span className="relative h-3 w-3 rounded-full bg-white" />
        </span>
        <div className="min-w-0 flex-1">
          <p role="alert" className="font-extrabold leading-tight tracking-wide">
            {title}{detail ? <span className="tnum font-bold"> · {detail}</span> : null}
          </p>
          {ago && <p className="text-sm text-white/85">{ago}</p>}
        </div>
        {onExpand && (
          <Button variant="inverse" onClick={onExpand} className="shrink-0">
            <Icon name="expand" size={18} />Agrandir
          </Button>
        )}
      </div>
      {children && <div className="mt-3">{children}</div>}
    </div>
  );
}
