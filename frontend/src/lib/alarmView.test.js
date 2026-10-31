// When the red alarm covers the screen, shrinks to a bar, or comes back.
import { describe, expect, it } from "vitest";
import { alarmMode, pruneReduced, reduceSnapshot } from "./alarmView";

const severe = (id) => ({ id, level: "severe" });
const emergency = (id) => ({ id, level: "emergency" });

describe("alarmMode", () => {
  it("nothing ringing: no alarm", () => {
    expect(alarmMode([], null, false)).toBe("none");
  });

  it("a new alert covers the screen; after Réduire it is a bar until something new arrives", () => {
    const items = [severe("a")];
    expect(alarmMode(items, null, false)).toBe("full");
    const reduced = reduceSnapshot(items);
    expect(alarmMode(items, reduced, false)).toBe("bar");
    expect(alarmMode([severe("a"), severe("b")], reduced, false)).toBe("full");   // another alert
    expect(alarmMode([emergency("a")], reduced, false)).toBe("full");             // the same alert got worse
  });

  it("never covers the emergency screen; covers again when it closes", () => {
    expect(alarmMode([emergency("a")], null, true)).toBe("bar");
    expect(alarmMode([emergency("a")], null, false)).toBe("full");
  });

  it("an alert that stopped ringing and rings again (reopened) covers the screen again", () => {
    let reduced = reduceSnapshot([severe("a")]);
    reduced = pruneReduced(reduced, []);                 // confirmed with the password
    expect(alarmMode([severe("a")], reduced, false)).toBe("full");
  });

  it("pruneReduced keeps null and the same object when nothing changed", () => {
    expect(pruneReduced(null, [severe("a")])).toBeNull();
    const reduced = reduceSnapshot([severe("a")]);
    expect(pruneReduced(reduced, [severe("a")])).toBe(reduced);
  });
});
