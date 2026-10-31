// Severe, trend and emergency alerts must never offer the dismissal form (Q5).
import { describe, expect, it } from "vitest";
import { canDismiss } from "./alerts";

describe("canDismiss", () => {
  it("offers dismissal only for open or acknowledged notices", () => {
    expect(canDismiss({ level: "notice", status: "open" })).toBe(true);
    expect(canDismiss({ level: "notice", status: "acknowledged" })).toBe(true);
    for (const status of ["reviewed", "resolved", "dismissed"]) expect(canDismiss({ level: "notice", status })).toBe(false);
  });

  it("never offers it for trend, severe or emergency alerts", () => {
    for (const level of ["trend", "severe", "emergency"]) {
      for (const status of ["open", "acknowledged"]) expect(canDismiss({ level, status })).toBe(false);
    }
  });
});
