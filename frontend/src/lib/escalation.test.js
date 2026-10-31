// The escalation panel must never overstate what happened (CLAUDE.md safety rules).
import { describe, expect, it } from "vitest";
import { ESCALATION_STATUS, isActive, stepStatus, stepWho } from "./escalation";

const step = (fields) => ({ target_kind: "doctor", target_label: "Dr Amrani", status: "scheduled", skip_reason: null, ...fields });

describe("escalation wording", () => {
  it("separates sent, displayed and confirmed", () => {
    expect(stepStatus(step({ status: "sent" }))).toMatch(/pas encore affichée/);
    expect(stepStatus(step({ status: "delivered" }))).toMatch(/pas encore confirmée/);
    expect(stepStatus(step({ status: "acknowledged" }))).toMatch(/confirmée/);
  });

  it("says plainly that contacts and emergency services were not notified", () => {
    expect(stepStatus(step({ target_kind: "contact", status: "skipped", skip_reason: "no_channel" }))).toMatch(/Non prévenu/);
    const services = step({ target_kind: "emergency_services", target_label: null, status: "skipped", skip_reason: "no_official_channel" });
    expect(stepWho(services)).toBe("Secours (14)");
    expect(stepStatus(services)).toMatch(/ne peut pas prévenir les secours/);
  });

  it("never claims a call or a dispatch", () => {
    const all = [...Object.values(ESCALATION_STATUS),
      ...["scheduled", "sending", "sent", "delivered", "acknowledged", "failed", "expired", "cancelled"].map((s) => stepStatus(step({ status: s })))];
    for (const text of all) expect(text).not.toMatch(/appel (passé|effectué)|secours (prévenus|en route)|aide arrive/i);
  });

  it("knows which escalations are still active", () => {
    expect(isActive({ eligible: true, status: "delivered" })).toBe(true);
    expect(isActive({ eligible: true, status: "cancelled" })).toBe(false);
    expect(isActive({ eligible: false, status: null })).toBe(false);
  });
});
