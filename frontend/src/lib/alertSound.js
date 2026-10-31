// Audible alert cues. The server decides every alert and level; this file only decides which sound goes with
// alerts the API already returned. Sounds are made with Web Audio (no asset files). Browsers play them only
// after the user has interacted with the page, and only while the PULSE tab is open: nothing here can sound
// on a locked phone, in a closed tab, or bypass silent mode.

export const CRITICAL_LEVELS = ["severe", "emergency"];
const PREF_KEY = "pulse.alertSound.enabled";
const MAX_REMEMBERED = 300;

// ------------------------------------------------------------------ decision (pure, tested)

/**
 * memory: { seen: string[], silenced: string[] } or null the first time this browser sees this user.
 * alerts: the alerts that still need this user's attention (already filtered by role).
 * Returns the new memory, the ids to chime once (new non-critical alerts) and the ids that keep the urgent
 * alarm going (critical alerts not silenced). Alerts already on screen the first time are remembered without
 * a sound, so signing in never plays the backlog; a page reload never repeats a chime.
 */
export function decideSounds(memory, alerts) {
  const first = memory === null;
  const seen = new Set(memory?.seen ?? []);
  const silenced = new Set(memory?.silenced ?? []);
  const chime = [];
  for (const a of alerts) {
    if (seen.has(a.id)) continue;
    seen.add(a.id);
    if (first) silenced.add(a.id);
    else if (!CRITICAL_LEVELS.includes(a.level)) chime.push(a.id);
  }
  const ringing = alerts.filter((a) => CRITICAL_LEVELS.includes(a.level) && !silenced.has(a.id)).map((a) => a.id);
  return { memory: { seen: [...seen].slice(-MAX_REMEMBERED), silenced: [...silenced].slice(-MAX_REMEMBERED) }, chime, ringing };
}

export function silence(memory, ids) {
  const silenced = new Set(memory?.silenced ?? []);
  ids.forEach((id) => silenced.add(id));
  return { seen: memory?.seen ?? [], silenced: [...silenced].slice(-MAX_REMEMBERED) };
}

/** Patient: an alert needs them until they acknowledge it. Doctor: until they review it (open or acknowledged). */
export function needsAttention(role, alert) {
  return role === "patient" ? alert.status === "open" : alert.status === "open" || alert.status === "acknowledged";
}

// ------------------------------------------------------------------ memory per user (browser storage)

export function readMemory(userId) {
  try {
    const raw = localStorage.getItem(`pulse.alertSound.memory.${userId}`);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function writeMemory(userId, memory) {
  try { localStorage.setItem(`pulse.alertSound.memory.${userId}`, JSON.stringify(memory)); } catch { /* private mode */ }
}

// ------------------------------------------------------------------ preference + audio state (one per tab)

let ctx = null;
let alarmTimer = null;
const listeners = new Set();
let snapshot = { enabled: readPref(), unlocked: false, ringing: false };

function readPref() {
  try { return localStorage.getItem(PREF_KEY) !== "0"; } catch { return true; }
}

function publish(change) {
  snapshot = { ...snapshot, ...change };
  listeners.forEach((fn) => fn());
}

export function subscribe(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function getSnapshot() {
  return snapshot;
}

function context() {
  const Ctx = typeof window !== "undefined" ? (window.AudioContext ?? window.webkitAudioContext) : null;
  if (!Ctx) return null;
  if (!ctx) {
    ctx = new Ctx();
    ctx.onstatechange = () => publish({ unlocked: ctx.state === "running" });
  }
  return ctx;
}

/** Call from a user gesture: browsers keep audio suspended until then. */
export function unlock() {
  const c = context();
  if (!c) return Promise.resolve(false);
  if (c.state === "running") return Promise.resolve(true);
  return c.resume().then(() => { publish({ unlocked: c.state === "running" }); return c.state === "running"; },
    () => false);
}

export function setEnabled(enabled) {
  try { localStorage.setItem(PREF_KEY, enabled ? "1" : "0"); } catch { /* private mode */ }
  if (!enabled) stopAlarm();
  publish({ enabled });
}

function tone(c, { at, freq, duration, type = "sine", volume = 0.2 }) {
  const osc = c.createOscillator();
  const gain = c.createGain();
  osc.type = type;
  osc.frequency.value = freq;
  gain.gain.setValueAtTime(0.0001, at);
  gain.gain.exponentialRampToValueAtTime(volume, at + 0.02);
  gain.gain.exponentialRampToValueAtTime(0.0001, at + duration);
  osc.connect(gain).connect(c.destination);
  osc.start(at);
  osc.stop(at + duration + 0.02);
}

function ready() {
  const c = snapshot.enabled ? context() : null;
  return c && c.state === "running" ? c : null;
}

/** Soft two-note chime, once (new notice or trend alert). */
export function chime() {
  const c = ready();
  if (!c) return false;
  const t = c.currentTime;
  tone(c, { at: t, freq: 880, duration: 0.25 });
  tone(c, { at: t + 0.22, freq: 660, duration: 0.35 });
  return true;
}

function urgentBurst() {
  const c = ready();
  if (!c) return;
  const t = c.currentTime;
  [0, 0.25, 0.5].forEach((d, i) => tone(c, { at: t + d, freq: i % 2 ? 640 : 960, duration: 0.18, type: "square", volume: 0.3 }));
}

/** Repeating three-beep pattern every 2 s until stopAlarm(). Starting it twice never overlaps. */
export function startAlarm() {
  if (alarmTimer !== null) return;
  urgentBurst();
  alarmTimer = setInterval(urgentBurst, 2000);
  publish({ ringing: true });
}

export function stopAlarm() {
  if (alarmTimer === null) return;
  clearInterval(alarmTimer);
  alarmTimer = null;
  publish({ ringing: false });
}

// Any later API change to alerts (acknowledge, review, new reading) asks the watcher to look again at once.
export const ALERTS_CHANGED = "pulse:alerts-changed";

export function announceAlertsChanged() {
  if (typeof window !== "undefined") window.dispatchEvent(new Event(ALERTS_CHANGED));
}
