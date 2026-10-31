// What the flag shows and what rings, from the server's alert states only.
import { describe, expect, it, vi } from "vitest";
import { flaggedAlerts, ringingItems, signalling } from "./alertEvents";

const alert = (id, level, status, created_at = "2026-10-31T08:00:00Z") => ({ id, level, status, created_at });

describe("alert flag selection", () => {
  it("flags severe and emergency alerts until the doctor resolves them", () => {
    const list = [alert("n", "notice", "open"), alert("t", "trend", "open"), alert("s1", "severe", "open"),
      alert("s2", "severe", "acknowledged"), alert("s3", "severe", "reviewed"), alert("s4", "severe", "resolved")];
    expect(flaggedAlerts(list).map((a) => a.id).sort()).toEqual(["s1", "s2", "s3"]);
  });

  it("puts the most severe, then the newest, first", () => {
    const list = [alert("old", "severe", "open", "2026-10-31T07:00:00Z"), alert("new", "severe", "open", "2026-10-31T09:00:00Z"),
      alert("e", "emergency", "acknowledged", "2026-10-31T06:00:00Z")];
    expect(flaggedAlerts(list).map((a) => a.id)).toEqual(["e", "new", "old"]);
  });

  it("rings only while the patient has not confirmed (both sides use the same rule)", () => {
    const list = [alert("s1", "severe", "open"), alert("s2", "severe", "acknowledged"), alert("e", "emergency", "reviewed"),
      alert("n", "notice", "open"), alert("t", "trend", "open")];
    expect(ringingItems(list)).toEqual([{ id: "s1", level: "severe" }]);
    expect(ringingItems([])).toEqual([]);
    expect(ringingItems(undefined)).toEqual([]);
  });
});

describe("change signal", () => {
  it("is sent after a successful call only", async () => {
    const seen = vi.fn();
    globalThis.window = new EventTarget();
    window.addEventListener("pulse:alerts-changed", seen);
    await signalling(Promise.resolve({ ok: true }));
    await signalling(Promise.reject(new Error("x"))).catch(() => {});
    expect(seen).toHaveBeenCalledTimes(1);
    delete globalThis.window;
  });
});

describe("emergency screen signal", () => {
  it("counts open emergency screens and tells the flag", async () => {
    const { emergencyScreenOpened, isEmergencyScreenOpen, subscribeEmergencyScreen } = await import("./alertEvents");
    let calls = 0;
    const stop = subscribeEmergencyScreen(() => { calls += 1; });
    const close = emergencyScreenOpened();
    expect(isEmergencyScreenOpen()).toBe(true);
    close();
    expect(isEmergencyScreenOpen()).toBe(false);
    stop();
    expect(calls).toBe(2);
  });
});
