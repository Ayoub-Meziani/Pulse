// Audible alerts for the existing alert lists (presentation only: the server decides every alert and level).
// One loop for the whole page, at the highest level among the alerts that should ring. Severe: a beep every
// 5 s; emergency: every 2 s. The loop starts when an eligible alert appears or its level (or count) goes up,
// never just because a list was refreshed, and stops when no eligible alert is left.
// "Couper le son" mutes everything for this browser tab's session; only "Réactiver le son" undoes it.
// Browsers only allow sound after the person clicked or typed on the page; until then the state is "locked".

const RANK = { severe: 1, emergency: 2 };
const PERIOD_MS = { severe: 5000, emergency: 2000 };
const MUTE_KEY = "pulse.alertSound.muted";

export const SOUND_LEVELS = Object.keys(RANK);

function sessionStore() {
  return {
    get() { try { return sessionStorage.getItem(MUTE_KEY) === "1"; } catch { return false; } },
    set(muted) {
      try { if (muted) sessionStorage.setItem(MUTE_KEY, "1"); else sessionStorage.removeItem(MUTE_KEY); } catch { /* memory only */ }
    },
  };
}

/** Web Audio: two short tones per beep. Returns null when the browser has no Web Audio. */
function webAudio() {
  const Ctx = typeof window !== "undefined" && (window.AudioContext ?? window.webkitAudioContext);
  if (!Ctx) return null;
  const ctx = new Ctx();
  return {
    get running() { return ctx.state === "running"; },
    resume: () => ctx.resume(),
    beep() {
      const t = ctx.currentTime;
      for (const [freq, start] of [[880, 0], [660, 0.18]]) {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.frequency.value = freq;
        gain.gain.setValueAtTime(0.0001, t + start);
        gain.gain.exponentialRampToValueAtTime(0.6, t + start + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.0001, t + start + 0.16);
        osc.connect(gain).connect(ctx.destination);
        osc.start(t + start);
        osc.stop(t + start + 0.17);
      }
    },
  };
}

/** Highest level among the items ({ id, level, count? }), or null. Notice and trend never ring. */
export function highestLevel(items) {
  return items.reduce((best, i) => ((RANK[i.level] ?? 0) > (RANK[best] ?? 0) ? i.level : best), null);
}

export function createAlertSound({ audio = webAudio, store = sessionStore(), setTimer = setInterval, clearTimer = clearInterval } = {}) {
  let player = null;            // created lazily (needs a user gesture to run)
  let status = "locked";        // locked | ready | unsupported | blocked
  let muted = store.get();
  let playing = null;           // level of the running loop, or null
  let timer = null;
  let pending = false;          // something new arrived that has not been heard yet
  const known = new Map();      // `${source}:${id}` -> { rank, count } already announced
  const sources = new Map();    // source -> items
  const listeners = new Set();
  let snapshot = null;

  const emit = () => { snapshot = null; listeners.forEach((l) => l()); };

  function eligible() {
    return [...sources.entries()].flatMap(([source, items]) =>
      items.filter((i) => RANK[i.level]).map((i) => ({ ...i, key: `${source}:${i.id}` })));
  }

  function stopLoop() {
    if (timer !== null) clearTimer(timer);
    timer = null;
    playing = null;
  }

  function startLoop(level) {
    if (playing === level) return;          // never restart a loop that already plays at this level
    stopLoop();
    playing = level;
    player.beep();
    timer = setTimer(() => player.beep(), PERIOD_MS[level]);
  }

  function apply() {
    const items = eligible();
    const level = highestLevel(items);
    if (!level) { stopLoop(); pending = false; emit(); return; }
    if (muted || status !== "ready") { stopLoop(); emit(); return; }
    if (playing || pending) startLoop(level);  // a running loop follows the highest level; a new alert starts one
    pending = false;
    emit();
  }

  async function open(fromGesture) {
    if (!player) {
      player = audio();
      if (!player) { status = "unsupported"; emit(); return; }
    }
    try {
      if (!player.running) await player.resume();
    } catch { /* stays suspended */ }
    status = player.running ? "ready" : fromGesture ? "blocked" : "locked";
  }

  return {
    /** Replace the items of one source (a page). Starts sound only for new or more severe alerts. */
    async update(source, items) {
      sources.set(source, items);
      const seen = new Set();
      for (const i of eligible()) {
        seen.add(i.key);
        const before = known.get(i.key);
        const rank = RANK[i.level];
        const count = i.count ?? 1;
        if (!before || rank > before.rank || count > before.count) pending = true;
        known.set(i.key, { rank, count });
      }
      for (const key of known.keys()) if (!seen.has(key)) known.delete(key);
      if (pending && !muted && status === "locked") await open(false);  // works if the page already had a click
      apply();
    },
    /** "Activer le son" / "Réactiver le son": must run inside a click. */
    async activate() {
      muted = false;
      store.set(false);
      await open(true);
      if (status === "ready" && highestLevel(eligible())) pending = true;
      apply();
    },
    /** "Couper le son": global for this tab's session; new alerts stay silent until activate(). */
    mute() {
      muted = true;
      store.set(true);
      stopLoop();
      pending = false;
      emit();
    },
    /** Sign-out: silence and forget, so the next person starts unmuted with nothing known. */
    reset() {
      stopLoop();
      sources.clear();
      known.clear();
      pending = false;
      muted = false;
      store.set(false);
      emit();
    },
    subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener); },
    getState() {
      if (!snapshot) snapshot = { status, muted, playing, ringing: Boolean(highestLevel(eligible())) };
      return snapshot;
    },
  };
}

/** The page-wide instance: one loop for the whole app. */
export const alertSound = createAlertSound();
