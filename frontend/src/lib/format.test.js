// Result headings. Fixtures follow EvaluationOut / MeasurementOut of contract/openapi.json.
import { describe, expect, it } from "vitest";
import { ALERT_LEVEL, evaluationHeading, FLAG_KIND, INVALID_FLAG, ringDataOrigin } from "./format";

describe("evaluationHeading", () => {
  it("an invalid reading (e.g. 1/1/1) never reads as saved and fine", () => {
    const ev = { level: "none", rule_id: "DATA-INVALID" };
    const h = evaluationHeading(ev, { validation_status: "invalid" });
    expect(h.invalid).toBe(true);
    expect(h.title).toMatch(/non valide/);
  });

  it("low blood pressure has its own warning heading and badge", () => {
    expect(evaluationHeading({ level: "low", rule_id: "R-LOW-1" }, { validation_status: "valid" }))
      .toMatchObject({ title: "Tension basse", variant: "warning" });
    expect(ALERT_LEVEL.low.label).toBe("Tension basse");
  });

  it("a normal reading stays 'Mesure enregistrée'", () => {
    expect(evaluationHeading({ level: "none", rule_id: null }, { validation_status: "valid" }).title)
      .toBe("Mesure enregistrée");
  });
});

it("ring model outputs are never labelled as an alert", () => {
  expect(FLAG_KIND.early_warning).toBe("Signal précoce (ML)");
  for (const label of Object.values(FLAG_KIND)) expect(label.toLowerCase()).not.toMatch(/alerte/);
});

describe("ringDataOrigin (DeviceOut list)", () => {
  const sim = { device_type: "simulator", is_simulated: true };
  const ring = { device_type: "wearable", is_simulated: false };
  const cuff = { device_type: "bp_cuff", is_simulated: false };

  it("simulator and no real ring: every ring value is simulated", () => {
    expect(ringDataOrigin([sim])).toBe("simulated");
    expect(ringDataOrigin([sim, cuff])).toBe("simulated");
  });

  it("simulator and a real ring: some values may be simulated", () => {
    expect(ringDataOrigin([ring, sim])).toBe("mixed");
  });

  it("no simulator: no label", () => {
    expect(ringDataOrigin([ring, cuff])).toBe(null);
    expect(ringDataOrigin([])).toBe(null);
  });
});

it("every invalid flag of the database (pulse-v1) has a French label", () => {
  expect(Object.keys(INVALID_FLAG).sort()).toEqual([
    "diastolic_implausible", "measured_in_future", "pulse_implausible", "systolic_implausible",
    "systolic_not_above_diastolic",
  ]);
});
