import { useEffect, useSyncExternalStore } from "react";
import { alertSound } from "../../lib/alertSound";
import Button from "../ui/Button";

/**
 * Sound for the alerts shown on this page. `items`: [{ id, level, count? }]; only severe and emergency ring.
 * The bar explains what the browser allows; the alerts stay on screen whatever happens to the sound.
 */
export default function AlertSound({ source, items }) {
  const state = useSyncExternalStore(alertSound.subscribe, alertSound.getState);
  const key = JSON.stringify(items);

  useEffect(() => {
    alertSound.update(source, JSON.parse(key));
  }, [source, key]);
  useEffect(() => () => { alertSound.update(source, []); }, [source]);

  const text = state.status === "unsupported" || state.status === "blocked"
    ? "Ce navigateur ne permet pas de jouer le son. Les alertes restent affichées à l'écran."
    : state.muted ? "Son des alertes coupé pour cette session."
      : state.status === "locked" ? "Son des alertes inactif : le navigateur demande d'abord un clic."
        : state.playing ? `Alerte sonore en cours (${state.playing === "emergency" ? "urgence" : "tension très élevée"}).`
          : "Son des alertes activé.";
  const canActivate = state.muted || state.status === "locked" || state.status === "blocked";

  return (
    <div role="status" className={`flex flex-wrap items-center gap-3 rounded-xl border px-4 py-2 text-sm ${
      state.playing ? "border-emergency/50 bg-level-severe-soft text-level-severe" : "border-line bg-surface text-ink-muted"}`}>
      <span className="flex-1">{text}</span>
      {canActivate
        ? <Button variant="secondary" onClick={() => alertSound.activate()}>{state.muted ? "Réactiver le son" : "Activer le son des alertes"}</Button>
        : state.status === "ready" && <Button variant="secondary" onClick={() => alertSound.mute()}>Couper le son</Button>}
    </div>
  );
}
