// One loop at most, started only by new or more severe alerts, stopped by acknowledgement and by a global mute.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createAlertSound, highestLevel } from "./alertSound";

function fakeAudio({ allowed = true } = {}) {
  const player = { running: false, beeps: 0, resume: vi.fn(async () => { player.running = allowed; }), beep: () => { player.beeps += 1; } };
  return { player, factory: vi.fn(() => player) };
}

function memoryStore() {
  let muted = false;
  return { get: () => muted, set: (m) => { muted = m; } };
}

const severe = (id, count) => ({ id, level: "severe", ...(count ? { count } : {}) });
const emergency = (id) => ({ id, level: "emergency" });

describe("alert sound", () => {
  let audio;
  let sound;
  beforeEach(() => {
    vi.useFakeTimers();
    audio = fakeAudio();
    sound = createAlertSound({ audio: audio.factory, store: memoryStore() });
  });
  afterEach(() => vi.useRealTimers());

  it("ignores notice and trend alerts", async () => {
    await sound.update("p", [{ id: "a", level: "notice" }, { id: "b", level: "trend" }]);
    expect(audio.factory).not.toHaveBeenCalled();
    expect(sound.getState()).toMatchObject({ playing: null, ringing: false });
    expect(highestLevel([{ level: "notice" }, { level: "trend" }])).toBeNull();
  });

  it("starts one loop for a new severe alert and does not restart it on refresh", async () => {
    await sound.update("p", [severe("a")]);
    expect(sound.getState().playing).toBe("severe");
    expect(audio.player.beeps).toBe(1);
    await sound.update("p", [severe("a")]);  // same list again (15-s refresh)
    await sound.update("p", [severe("a")]);
    expect(audio.player.beeps).toBe(1);
    vi.advanceTimersByTime(5000);
    expect(audio.player.beeps).toBe(2);
    expect(vi.getTimerCount()).toBe(1);
  });

  it("uses the highest level and keeps a single loop", async () => {
    await sound.update("p", [severe("a")]);
    await sound.update("p", [severe("a"), emergency("b")]);
    expect(sound.getState().playing).toBe("emergency");
    expect(vi.getTimerCount()).toBe(1);
    vi.advanceTimersByTime(2000);
    expect(audio.player.beeps).toBe(3);  // severe start, emergency start, one emergency repeat
  });

  it("restarts at the new level when a patient's alert becomes more severe or a new one is added", async () => {
    await sound.update("d", [severe("p1", 1)]);
    sound.mute();
    await sound.activate();
    expect(sound.getState().playing).toBe("severe");
    await sound.update("d", [{ id: "p1", level: "emergency", count: 1 }]);
    expect(sound.getState().playing).toBe("emergency");
  });

  it("stops when the alert is acknowledged and the remaining loop follows the highest level left", async () => {
    await sound.update("p", [severe("a"), emergency("b")]);
    await sound.update("p", [severe("a")]);  // b acknowledged
    expect(sound.getState().playing).toBe("severe");
    await sound.update("p", []);             // a acknowledged too
    expect(sound.getState()).toMatchObject({ playing: null, ringing: false });
    expect(vi.getTimerCount()).toBe(0);
  });

  it("mute is global: new alerts stay silent until the user turns sound back on", async () => {
    await sound.update("p", [severe("a")]);
    sound.mute();
    expect(sound.getState()).toMatchObject({ muted: true, playing: null });
    await sound.update("p", [severe("a"), emergency("b")]);
    await sound.update("d", [severe("x", 2)]);
    expect(sound.getState().playing).toBeNull();
    expect(vi.getTimerCount()).toBe(0);
    await sound.activate();
    expect(sound.getState()).toMatchObject({ muted: false, playing: "emergency" });
  });

  it("mute survives a new instance in the same session (page reload)", async () => {
    const store = memoryStore();
    createAlertSound({ audio: audio.factory, store }).mute();
    const again = createAlertSound({ audio: audio.factory, store });
    await again.update("p", [emergency("a")]);
    expect(again.getState()).toMatchObject({ muted: true, playing: null });
  });

  it("stays locked when the browser refuses sound, and asks for a click", async () => {
    const refused = fakeAudio({ allowed: false });
    const s = createAlertSound({ audio: refused.factory, store: memoryStore() });
    await s.update("p", [severe("a")]);
    expect(s.getState()).toMatchObject({ status: "locked", playing: null, ringing: true });
    await s.activate();  // the click did not help either
    expect(s.getState()).toMatchObject({ status: "blocked", playing: null });
    expect(refused.player.beeps).toBe(0);
  });

  it("starts after the click when the browser needed one", async () => {
    let allowed = false;
    const player = { running: false, beeps: 0, resume: async () => { player.running = allowed; }, beep: () => { player.beeps += 1; } };
    const s = createAlertSound({ audio: () => player, store: memoryStore() });
    await s.update("p", [severe("a")]);
    expect(s.getState().status).toBe("locked");
    allowed = true;
    await s.activate();
    expect(s.getState()).toMatchObject({ status: "ready", playing: "severe" });
  });

  it("reports browsers without Web Audio as unsupported", async () => {
    const s = createAlertSound({ audio: () => null, store: memoryStore() });
    await s.update("p", [severe("a")]);
    expect(s.getState()).toMatchObject({ status: "unsupported", playing: null });
  });

  it("sign-out silences and forgets the mute", async () => {
    const store = memoryStore();
    const s = createAlertSound({ audio: audio.factory, store });
    await s.update("p", [severe("a")]);
    s.mute();
    s.reset();
    expect(store.get()).toBe(false);
    expect(s.getState()).toMatchObject({ muted: false, playing: null, ringing: false });
  });

  it("leaving a page stops its sound", async () => {
    await sound.update("d", [severe("p1", 1)]);
    await sound.update("d", []);
    expect(sound.getState().playing).toBeNull();
    expect(vi.getTimerCount()).toBe(0);
  });
});
