// Emergency incident record (conception §7.6). The screen never waits for it: every step is queued in the
// browser and sent in the background, retried until the server accepts it. Ids are generated here, so a retry
// never creates a second event or a second action (the server deduplicates on them).
// Actions describe what the patient TAPPED or OPENED. PULSE never knows that a call connected or that a
// message was sent, and nothing here says so.

const KEY = "pulse.emergency.queue";

export function memoryStore(initial = []) {
  let value = JSON.stringify(initial);
  return { read: () => JSON.parse(value), write: (v) => { value = JSON.stringify(v); } };
}

export function browserStore() {
  return {
    read() {
      try { return JSON.parse(localStorage.getItem(KEY) ?? "[]"); } catch { return []; }
    },
    write(v) {
      try { localStorage.setItem(KEY, JSON.stringify(v)); } catch { /* private mode: in-memory only */ }
    },
  };
}

const uuid = () => crypto.randomUUID();

/** Queue a new incident. Returns its id at once; nothing waits for the network. */
export function openIncident(store, patientId, { trigger = "manual", alertId = null, symptoms = [] } = {}, now = new Date()) {
  const incident = {
    id: uuid(), patientId, created: false,
    body: { trigger_reason: trigger, alert_id: alertId, symptoms_snapshot: symptoms, started_at: now.toISOString() },
    actions: [], patch: null,
  };
  incident.body.id = incident.id;
  store.write([...store.read(), incident]);
  return incident.id;
}

export function queueAction(store, incidentId, action, detail = null, now = new Date()) {
  store.write(store.read().map((i) => i.id !== incidentId ? i : {
    ...i, actions: [...i.actions, { client_action_id: uuid(), action, at: now.toISOString(), detail }],
  }));
}

/** Location (only with consent in the same request) and/or the outcome. Later patches merge into earlier ones. */
export function queuePatch(store, incidentId, patch) {
  store.write(store.read().map((i) => i.id !== incidentId ? i : { ...i, patch: { ...(i.patch ?? {}), ...patch } }));
}

/**
 * Sends what is queued. api: { start(patientId, body), actions(eventId, list), patch(eventId, body) }.
 * Anything that fails stays queued for the next flush; what succeeded is removed. Returns the queue left.
 */
export async function flushIncidents(store, api, patientId) {
  // Only the signed-in patient's incidents: another account's token would be refused (403).
  for (const incident of store.read().filter((i) => !patientId || i.patientId === patientId)) {
    try {
      if (!incident.created) {
        await api.start(incident.patientId, incident.body);
        update(store, incident.id, { created: true });
      }
      const pending = current(store, incident.id).actions;
      if (pending.length) {
        await api.actions(incident.id, pending);
        const sent = new Set(pending.map((a) => a.client_action_id));
        update(store, incident.id, { actions: current(store, incident.id).actions.filter((a) => !sent.has(a.client_action_id)) });
      }
      const patch = current(store, incident.id).patch;
      if (patch) {
        await api.patch(incident.id, patch);
        update(store, incident.id, { patch: null });
      }
      const done = current(store, incident.id);
      if (done.created && done.actions.length === 0 && !done.patch && done.closed) {
        store.write(store.read().filter((i) => i.id !== incident.id));
      }
    } catch {
      // Network or server error: keep it queued; the next flush retries with the same ids.
    }
  }
  return store.read();
}

/** Marks an incident finished locally (outcome reported); it leaves the queue once everything is sent. */
export function closeIncident(store, incidentId) {
  update(store, incidentId, { closed: true });
}

function current(store, id) {
  return store.read().find((i) => i.id === id);
}

function update(store, id, fields) {
  store.write(store.read().map((i) => (i.id === id ? { ...i, ...fields } : i)));
}
