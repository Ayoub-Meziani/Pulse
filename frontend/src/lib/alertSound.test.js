// Which sound goes with which alert. Levels and statuses are the server's (AlertOut); nothing here computes them.
import { describe, expect, it } from "vitest";
import { decideSounds, needsAttention, silence } from "./alertSound";

const alert = (id, level, status = "open") => ({ id, level, status });
const EMPTY = { seen: [], silenced: [] };

describe("decideSounds", () => {
  it("first look in this browser: remembers what is already there, plays nothing", () => {
    const r = decideSounds(null, [alert("n1", "notice"), alert("s1", "severe")]);
    expect(r.chime).toEqual([]);
    expect(r.ringing).toEqual([]);
    expect(r.memory.seen).toEqual(["n1", "s1"]);
  });

  it("new notice or trend: one chime, and never again for the same alert", () => {
    const first = decideSounds(EMPTY, [alert("n1", "notice"), alert("t1", "trend")]);
    expect(first.chime).toEqual(["n1", "t1"]);
    expect(first.ringing).toEqual([]);
    const again = decideSounds(first.memory, [alert("n1", "notice"), alert("t1", "trend")]);
    expect(again.chime).toEqual([]);
  });

  it("new severe or emergency: urgent alarm, no chime, and it keeps ringing on the next look", () => {
    const first = decideSounds(EMPTY, [alert("s1", "severe"), alert("e1", "emergency")]);
    expect(first.chime).toEqual([]);
    expect(first.ringing).toEqual(["s1", "e1"]);
    expect(decideSounds(first.memory, [alert("s1", "severe"), alert("e1", "emergency")]).ringing).toEqual(["s1", "e1"]);
  });

  it("acknowledged or reviewed (no longer in the list): the alarm stops", () => {
    const first = decideSounds(EMPTY, [alert("s1", "severe")]);
    expect(decideSounds(first.memory, []).ringing).toEqual([]);
  });

  it("silenced: stops for that alert only; a later critical alert rings again", () => {
    const first = decideSounds(EMPTY, [alert("s1", "severe")]);
    const muted = silence(first.memory, ["s1"]);
    expect(decideSounds(muted, [alert("s1", "severe")]).ringing).toEqual([]);
    expect(decideSounds(muted, [alert("s1", "severe"), alert("e2", "emergency")]).ringing).toEqual(["e2"]);
  });

  it("memory stays bounded", () => {
    const many = Array.from({ length: 400 }, (_, i) => alert(`n${i}`, "notice"));
    expect(decideSounds(EMPTY, many).memory.seen.length).toBe(300);
  });
});

describe("needsAttention", () => {
  it("patient: only open alerts (acknowledging stops the sound)", () => {
    expect(needsAttention("patient", alert("a", "severe", "open"))).toBe(true);
    expect(needsAttention("patient", alert("a", "severe", "acknowledged"))).toBe(false);
  });

  it("doctor: open or acknowledged by the patient, until the doctor reviews it", () => {
    expect(needsAttention("doctor", alert("a", "severe", "acknowledged"))).toBe(true);
    expect(needsAttention("doctor", alert("a", "severe", "reviewed"))).toBe(false);
  });
});
