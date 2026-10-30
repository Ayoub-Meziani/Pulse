// Screen choice after each server answer. Levels and flags in these fixtures are what the backend
// returns for the named rules (api/app/analysis/rules.py); the helper must follow them, never compute them.
import { describe, expect, it } from "vitest";
import { afterMeasurement, afterSymptoms, whenUnreachable } from "./readingFlow";

function evaluation(over = {}) {
  return { level: "none", rule_id: null, reason: "Below target.", next_step: "Reading saved.",
    requires_symptom_check: false, recheck_after_seconds: null, show_emergency: false, ...over };
}

const measurement = (ev) => ({ measurement: { id: "m1" }, evaluation: evaluation(ev), alert: null, trend_alert: null });
const report = (ev) => ({ report: { id: "s1" }, evaluation: evaluation(ev), alert: null });

const SEV1 = { level: "severe", rule_id: "R-SEV-1", requires_symptom_check: true, recheck_after_seconds: 60 };
const SEV2 = { level: "severe", rule_id: "R-SEV-2", requires_symptom_check: true };
const EMG = { level: "emergency", rule_id: "R-EMG-1", reason: "Reported: chest pain.",
  next_step: "Call emergency services now. Do not wait to measure again.", show_emergency: true };
const FALLBACK = { severe_systolic: 180, severe_diastolic: 120, red_flag_symptoms: ["chest_pain", "numbness"] };

describe("afterMeasurement", () => {
  it("normal reading: done", () => {
    expect(afterMeasurement(measurement()).kind).toBe("done");
  });

  it("above target (R-TGT-1, notice): done, no symptom check", () => {
    expect(afterMeasurement(measurement({ level: "notice", rule_id: "R-TGT-1" })).kind).toBe("done");
  });

  it("severe 185/125 (R-SEV-1): symptom check first", () => {
    const step = afterMeasurement(measurement(SEV1));
    expect(step.kind).toBe("symptoms");
  });

  it("symptoms ticked on the form are always sent, even for a normal reading", () => {
    const step = afterMeasurement(measurement(), ["dizziness"]);
    expect(step).toMatchObject({ kind: "send_symptoms", symptoms: ["dizziness"] });
  });

  it("server emergency wins over everything", () => {
    const step = afterMeasurement(measurement({ ...SEV1, show_emergency: true }), ["dizziness"]);
    expect(step.kind).toBe("emergency");
  });

  it("implausible reading (DATA-INVALID with symptom check): symptom check", () => {
    const step = afterMeasurement(measurement({ rule_id: "DATA-INVALID", requires_symptom_check: true }));
    expect(step.kind).toBe("symptoms");
  });
});

describe("afterSymptoms", () => {
  it("red-flag symptom (R-EMG-1): emergency with the server's own words", () => {
    const step = afterSymptoms(measurement(SEV1), report(EMG));
    expect(step).toEqual({ kind: "emergency", reason: EMG.reason, nextStep: EMG.next_step });
  });

  it("no red flag after a severe first reading: recheck timer with the server's delay", () => {
    const step = afterSymptoms(measurement(SEV1), report());
    expect(step).toMatchObject({ kind: "recheck_wait", seconds: 60 });
  });

  it("no red flag after a severe recheck (R-SEV-2): done, no second timer", () => {
    expect(afterSymptoms(measurement(SEV2), report()).kind).toBe("done");
  });

  it("symptom-only report without a reading: done or emergency", () => {
    expect(afterSymptoms(null, report()).kind).toBe("done");
    expect(afterSymptoms(null, report(EMG)).kind).toBe("emergency");
  });
});

describe("whenUnreachable", () => {
  it("uses the server-provided fallback only", () => {
    expect(whenUnreachable({ systolic: 185, diastolic: 100 }, [], FALLBACK).emergency).toBe(true);
    expect(whenUnreachable({ systolic: 150, diastolic: 125 }, [], FALLBACK).emergency).toBe(true);
    expect(whenUnreachable({ systolic: 150, diastolic: 95 }, ["numbness"], FALLBACK).emergency).toBe(true);
    expect(whenUnreachable({ systolic: 150, diastolic: 95 }, ["dizziness"], FALLBACK).emergency).toBe(false);
    expect(whenUnreachable(null, ["chest_pain"], FALLBACK).emergency).toBe(true);
  });

  it("without the server fallback it never guesses a level", () => {
    expect(whenUnreachable({ systolic: 250, diastolic: 150 }, [], null)).toEqual({ kind: "unreachable", emergency: false });
  });
});
