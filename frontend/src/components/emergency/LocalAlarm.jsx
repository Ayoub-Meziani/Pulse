import { useEffect, useRef, useState } from "react";
import Button from "../ui/Button";

// Loud alarm on this phone, to wake the patient or attract people nearby. A web page can only sound while it is
// open in the foreground: it stops when the screen locks or the app is closed (docs/ALGERIA_EMERGENCY_FEASIBILITY.md §4).
// A native app is needed for a lock-screen alarm, and that is not promised until tested on real phones.

function startTone() {
  const Ctx = window.AudioContext ?? window.webkitAudioContext;
  if (!Ctx) return null;
  const ctx = new Ctx();
  const gain = ctx.createGain();
  gain.gain.value = 0.9;
  gain.connect(ctx.destination);
  const osc = ctx.createOscillator();
  osc.type = "square";
  osc.connect(gain);
  osc.start();
  let high = true;
  const timer = setInterval(() => { osc.frequency.value = high ? 960 : 640; high = !high; }, 400);
  return () => { clearInterval(timer); osc.stop(); ctx.close(); };
}

export default function LocalAlarm({ onStart, onStop }) {
  const [on, setOn] = useState(false);
  const stop = useRef(null);
  const wake = useRef(null);

  async function start() {
    stop.current = startTone();  // must run inside the tap (autoplay rules)
    if (navigator.vibrate) navigator.vibrate(Array(30).fill([700, 300]).flat());
    try { wake.current = await navigator.wakeLock?.request("screen"); } catch { /* not supported or refused */ }
    setOn(true);
    onStart?.();
  }

  function end() {
    stop.current?.();
    stop.current = null;
    if (navigator.vibrate) navigator.vibrate(0);
    wake.current?.release?.().catch(() => {});
    wake.current = null;
    setOn(false);
    onStop?.();
  }

  useEffect(() => () => { stop.current?.(); wake.current?.release?.().catch(() => {}); }, []);

  return (
    <div className={`rounded-2xl border p-5 ${on ? "border-emergency bg-level-severe-soft" : "border-line bg-surface"}`}>
      <p className="text-lg font-bold text-ink">Alarme sonore</p>
      <p className="mt-1 text-sm text-ink-muted">
        Pour attirer l'attention des personnes autour de vous. L'alarme ne sonne que tant que PULSE est ouvert à l'écran.
      </p>
      <div className="mt-3">
        {on
          ? <Button variant="emergency" onClick={end}>Arrêter l'alarme</Button>
          : <Button variant="secondary" onClick={start}>Faire sonner l'alarme</Button>}
      </div>
      {on && <p role="status" className="mt-2 text-sm font-semibold text-emergency">Alarme en cours.</p>}
    </div>
  );
}
