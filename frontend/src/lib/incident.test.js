// The incident queue must never lose a step, never send a step twice and never block the emergency screen.
import { describe, expect, it, vi } from "vitest";
import { closeIncident, flushIncidents, memoryStore, openIncident, queueAction, queuePatch } from "./incident";

function api({ failStart = false, failActions = false } = {}) {
  return {
    start: vi.fn(() => (failStart ? Promise.reject(new Error("offline")) : Promise.resolve({}))),
    actions: vi.fn(() => (failActions ? Promise.reject(new Error("500")) : Promise.resolve({}))),
    patch: vi.fn(() => Promise.resolve({})),
  };
}

describe("incident queue", () => {
  it("opens an incident with a client id and the trigger, without any network call", () => {
    const store = memoryStore();
    const id = openIncident(store, "p1", { trigger: "symptom", symptoms: ["chest_pain"] });
    const [incident] = store.read();
    expect(incident.id).toBe(id);
    expect(incident.body).toMatchObject({ id, trigger_reason: "symptom", symptoms_snapshot: ["chest_pain"] });
  });

  it("sends the event, then its actions, then the patch, and empties the queue once closed", async () => {
    const store = memoryStore();
    const id = openIncident(store, "p1");
    queueAction(store, id, "screen_opened");
    queueAction(store, id, "emergency_call_tapped", "demo");
    queuePatch(store, id, { reported_outcome: "went_to_hospital" });
    closeIncident(store, id);
    const a = api();
    expect(await flushIncidents(store, a)).toEqual([]);
    expect(a.start).toHaveBeenCalledWith("p1", expect.objectContaining({ id }));
    expect(a.actions.mock.calls[0][1].map((x) => x.action)).toEqual(["screen_opened", "emergency_call_tapped"]);
    expect(a.patch).toHaveBeenCalledWith(id, { reported_outcome: "went_to_hospital" });
  });

  it("keeps everything when offline and retries with the same ids", async () => {
    const store = memoryStore();
    const id = openIncident(store, "p1");
    queueAction(store, id, "screen_opened");
    const before = store.read()[0].actions[0].client_action_id;
    await flushIncidents(store, api({ failStart: true }));
    expect(store.read()[0]).toMatchObject({ created: false });
    const retry = api();
    await flushIncidents(store, retry);
    expect(retry.start.mock.calls[0][1].id).toBe(id);
    expect(retry.actions.mock.calls[0][1][0].client_action_id).toBe(before);
  });

  it("does not resend actions that were accepted", async () => {
    const store = memoryStore();
    const id = openIncident(store, "p1");
    queueAction(store, id, "screen_opened");
    await flushIncidents(store, api());
    queueAction(store, id, "contact_call_tapped");
    const second = api();
    await flushIncidents(store, second);
    expect(second.start).not.toHaveBeenCalled();
    expect(second.actions.mock.calls[0][1].map((x) => x.action)).toEqual(["contact_call_tapped"]);
  });

  it("keeps actions queued when only the action call fails", async () => {
    const store = memoryStore();
    const id = openIncident(store, "p1");
    queueAction(store, id, "share_opened");
    await flushIncidents(store, api({ failActions: true }));
    expect(store.read()[0].created).toBe(true);
    expect(store.read()[0].actions).toHaveLength(1);
  });

  it("drops a stale queued position but still sends the outcome", async () => {
    const store = memoryStore();
    const id = openIncident(store, "p1");
    queuePatch(store, id, { location: { lat: 36.7, lon: 3.06 }, location_shared_with_consent: true,
      location_captured_at: "2026-10-31T08:00:00Z" });
    queuePatch(store, id, { reported_outcome: "felt_better" });
    closeIncident(store, id);
    const stale = Object.assign(new Error("422"), { status: 422, details: [{ field: "location_captured_at", code: "stale_location" }] });
    const a = { ...api(), patch: vi.fn().mockRejectedValueOnce(stale).mockResolvedValue({}) };
    expect(await flushIncidents(store, a)).toEqual([]);
    expect(a.patch).toHaveBeenLastCalledWith(id, { reported_outcome: "felt_better" });
  });

  it("merges successive patches (location with consent, then the outcome)", () => {
    const store = memoryStore();
    const id = openIncident(store, "p1");
    queuePatch(store, id, { location: { lat: 36.7, lon: 3.06 }, location_shared_with_consent: true });
    queuePatch(store, id, { reported_outcome: "felt_better" });
    expect(store.read()[0].patch).toEqual({ location: { lat: 36.7, lon: 3.06 }, location_shared_with_consent: true, reported_outcome: "felt_better" });
  });
});
