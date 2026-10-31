import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { Link } from "react-router";
import { listMyPatients } from "../../api/doctor";
import { listAlerts } from "../../api/patient";
import {
  ALERTS_CHANGED, chime, decideSounds, getSnapshot, needsAttention, readMemory, setEnabled, silence, startAlarm,
  stopAlarm, subscribe, unlock, writeMemory,
} from "../../lib/alertSound";
import Icon from "../ui/Icon";

const POLL_MS = 15000;

function useAlertSoundState() {
  return useSyncExternalStore(subscribe, getSnapshot);
}

/** Active alerts that still need this user, read from the same endpoints as the alert screens. */
async function attentionAlerts(user) {
  if (user.role === "patient") {
    const list = await listAlerts(user.id, { status: "active" });
    return list.filter((a) => needsAttention("patient", a));
  }
  const patients = (await listMyPatients()).filter((p) => p.active_alert_count > 0);
  const lists = await Promise.all(patients.map((p) => listAlerts(p.id, { status: "active" })));
  return lists.flat().filter((a) => needsAttention("doctor", a));
}

/**
 * Mounted once per signed-in page (AppLayout), for patients and doctors. Plays a chime for a new notice or
 * trend alert and repeats an urgent alarm for a severe or emergency alert until it is acknowledged (patient),
 * reviewed (doctor) or silenced here. It never changes an alert; the visual alerts stay where they are.
 */
export function AlertSoundWatcher({ user }) {
  const sound = useAlertSoundState();
  const [ringing, setRinging] = useState([]);
  const busy = useRef(false);
  const watch = user.role === "patient" || user.role === "doctor";

  const check = useCallback(async () => {
    if (busy.current) return;
    busy.current = true;
    try {
      const alerts = await attentionAlerts(user);
      const result = decideSounds(readMemory(user.id), alerts);
      writeMemory(user.id, result.memory);
      if (result.chime.length > 0 && result.ringing.length === 0) chime();
      setRinging(alerts.filter((a) => result.ringing.includes(a.id)));
    } catch {
      // Network or session error: keep the current state; the next poll tries again.
    } finally {
      busy.current = false;
    }
  }, [user]);

  useEffect(() => {
    if (!watch) return undefined;
    const now = setTimeout(check, 0);
    const id = setInterval(check, POLL_MS);
    const onVisible = () => { if (document.visibilityState === "visible") check(); };
    window.addEventListener(ALERTS_CHANGED, check);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      clearTimeout(now);
      clearInterval(id);
      window.removeEventListener(ALERTS_CHANGED, check);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [watch, check]);

  // Browsers keep audio locked until the first click or key press on the page.
  useEffect(() => {
    // The sound switch handles its own click (otherwise this would unlock first and the switch would turn off).
    const onGesture = (e) => {
      if (getSnapshot().enabled && !e.target?.closest?.("[data-alert-sound-toggle]")) unlock();
    };
    document.addEventListener("pointerdown", onGesture);
    document.addEventListener("keydown", onGesture);
    return () => {
      document.removeEventListener("pointerdown", onGesture);
      document.removeEventListener("keydown", onGesture);
    };
  }, []);

  const shouldRing = sound.enabled && ringing.length > 0;
  useEffect(() => {
    if (shouldRing) startAlarm();
    else stopAlarm();
  }, [shouldRing]);
  useEffect(() => stopAlarm, []);

  if (!shouldRing) return null;
  const first = ringing[0];
  const to = user.role === "patient" ? "/patient/alertes" : `/doctor/patients/${first.patient_id}`;
  function mute() {
    writeMemory(user.id, silence(readMemory(user.id), ringing.map((a) => a.id)));
    setRinging([]);
  }
  return (
    <div role="alert" className="fixed inset-x-0 top-0 z-50 flex flex-wrap items-center justify-center gap-3 bg-emergency px-4 py-3 text-white shadow-lg">
      <Icon name="alert" size={20} />
      <p className="text-sm font-semibold">
        {ringing.length > 1 ? `${ringing.length} alertes urgentes` : "Alerte urgente"} : {first.reason}
        {!sound.unlocked && <span className="block text-xs font-normal">Cliquez n'importe où pour activer le son.</span>}
      </p>
      <Link to={to} className="rounded-lg bg-white px-3 py-1.5 text-sm font-semibold text-emergency">Voir l'alerte</Link>
      <button type="button" onClick={mute} className="rounded-lg border border-white/70 px-3 py-1.5 text-sm font-semibold">
        Couper le son
      </button>
    </div>
  );
}

/** Sidebar switch. Turning it on is a click, which also unlocks audio and plays a short test chime. */
export function AlertSoundToggle() {
  const sound = useAlertSoundState();
  async function toggle() {
    if (sound.enabled && sound.unlocked) { setEnabled(false); return; }
    setEnabled(true);
    if (await unlock()) chime();
  }
  const label = !sound.enabled ? "Son des alertes coupé" : sound.unlocked ? "Son des alertes activé" : "Activer le son des alertes";
  return (
    <button type="button" data-alert-sound-toggle onClick={toggle} aria-pressed={sound.enabled && sound.unlocked}
      title="Un son est joué quand une nouvelle alerte apparaît, tant que PULSE est ouvert"
      className={`flex min-h-11 w-full items-center gap-3 rounded-xl px-3.5 text-sm font-medium ${
        sound.enabled && sound.unlocked ? "text-white/85 hover:bg-white/8" : "bg-white/10 text-white hover:bg-white/15"}`}>
      <Icon name={sound.enabled ? "bell" : "bellOff"} size={19} />
      {label}
    </button>
  );
}
