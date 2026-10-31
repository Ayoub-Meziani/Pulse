import { useEffect, useSyncExternalStore } from "react";
import { alertSound, soundText } from "../../lib/alertSound";
import Button from "../ui/Button";
import Icon from "../ui/Icon";

/**
 * Sound for the alerts shown on this page. `items`: [{ id, level, count? }]; only severe and emergency ring.
 * The bar explains what the browser allows; the alerts stay on screen whatever happens to the sound.
 * canMute=false (patient, proposed D29): no "Couper le son"; the alarm stops when the alert is confirmed with the
 * password.
 */
export default function AlertSound({ source, items, canMute = true }) {
  const state = useSyncExternalStore(alertSound.subscribe, alertSound.getState);
  const key = JSON.stringify(items);

  useEffect(() => {
    alertSound.update(source, JSON.parse(key));
  }, [source, key]);
  useEffect(() => () => { alertSound.update(source, []); }, [source]);

  // The first click or key press anywhere (e.g. "Enregistrer la mesure") lets the browser play the alarm.
  useEffect(() => {
    const unlock = () => { alertSound.unlock(); };
    window.addEventListener("pointerdown", unlock, true);
    window.addEventListener("keydown", unlock, true);
    return () => {
      window.removeEventListener("pointerdown", unlock, true);
      window.removeEventListener("keydown", unlock, true);
    };
  }, []);

  useEffect(() => {
    if (!canMute && state.muted) alertSound.unmute();
  }, [canMute, state.muted]);

  return <SoundControls canMute={canMute} />;
}

/**
 * View only (no ringing logic): the sound status and its buttons. AlertSound renders it in the page; the alarm shows
 * a second copy in its header (inverse = on red). The loop itself stays in the single mounted AlertSound.
 */
export function SoundControls({ canMute = true, inverse = false }) {
  const state = useSyncExternalStore(alertSound.subscribe, alertSound.getState);
  const canActivate = state.muted || state.status === "locked" || state.status === "blocked";
  const variant = inverse ? "inverse" : "secondary";
  const look = inverse ? "border-white/30 bg-white/10 text-white"
    : state.playing ? "border-emergency/50 bg-level-severe-soft text-level-severe" : "border-line bg-surface text-ink-muted";

  return (
    <div role="status" className={`flex flex-wrap items-center gap-3 rounded-xl border px-4 py-2 text-sm ${look}`}>
      <Icon name={state.muted || state.status !== "ready" ? "volume-off" : "volume"} size={18} className="shrink-0" />
      <span className="min-w-0 flex-1 basis-56">{soundText(state, canMute)}</span>
      {canActivate
        ? <Button variant={variant} onClick={() => alertSound.activate()}>{state.muted ? "Réactiver le son" : "Activer le son des alertes"}</Button>
        : canMute && state.status === "ready" && <Button variant={variant} onClick={() => alertSound.mute()}>Couper le son</Button>}
    </div>
  );
}
