// Result headings. Fixtures follow EvaluationOut / MeasurementOut of contract/openapi.json.
import { describe, expect, it } from "vitest";
import { ALERT_LEVEL, evaluationHeading, INVALID_FLAG } from "./format";

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

it("every invalid flag of the database (pulse-v1) has a French label", () => {
  expect(Object.keys(INVALID_FLAG).sort()).toEqual([
    "diastolic_implausible", "measured_in_future", "pulse_implausible", "systolic_implausible",
    "systolic_not_above_diastolic",
  ]);
});
