// Endpoints of one patient's record (contract/openapi.json). Used by the patient for their own id and by
// an actively assigned doctor; the server decides who may read what (403 otherwise). Shapes are the server's.
import { request } from "./client";

const base = (patientId) => `/patients/${patientId}`;

export function listMeasurements(patientId, { limit = 100, includeInvalid = false, signal } = {}) {
  return request(`${base(patientId)}/measurements`, {
    query: { limit, include_invalid: includeInvalid || undefined }, signal,
  });
}

export function getSummary(patientId, { signal } = {}) {
  return request(`${base(patientId)}/summary`, { signal });
}

export function listAlerts(patientId, { status = "active", signal } = {}) {
  return request(`${base(patientId)}/alerts`, { query: { status }, signal });
}

/** Kept for the Task 1 dashboard tests: active alerts only. */
export function listActiveAlerts(patientId, { signal } = {}) {
  return listAlerts(patientId, { status: "active", signal });
}

export function transitionAlert(alertId, to, note) {
  return request(`/alerts/${alertId}/transition`, { method: "POST", body: note ? { to, note } : { to } });
}

export function listSymptomReports(patientId, { limit = 50, signal } = {}) {
  return request(`${base(patientId)}/symptom-reports`, { query: { limit }, signal });
}

export function getProfile(patientId, { signal } = {}) {
  return request(`${base(patientId)}/profile`, { signal });
}

export function getCarePlan(patientId, { signal } = {}) {
  return request(`${base(patientId)}/care-plan`, { signal });
}

export function listTrustedContacts(patientId, { signal } = {}) {
  return request(`${base(patientId)}/trusted-contacts`, { signal });
}

/** Doctor: full notes. Patient: only advice and follow-up dates (note = null), decided by the server. */
export function listNotes(patientId, { signal } = {}) {
  return request(`${base(patientId)}/notes`, { signal });
}

export function listDevices(patientId, { signal } = {}) {
  return request(`${base(patientId)}/devices`, { signal });
}

export function listWearableSamples(patientId, { metric, limit = 500, signal } = {}) {
  return request(`${base(patientId)}/wearable-samples`, { query: { metric, limit }, signal });
}

// Reading flow. Each answer carries the server's deterministic evaluation (EvaluationOut).
/** body.id (uuid) makes the call repeat-safe: the same id returns the stored reading instead of a second one. */
export function addMeasurement(patientId, body) {
  return request(`${base(patientId)}/measurements`, { method: "POST", body });
}

export function addSymptomReport(patientId, body) {
  return request(`${base(patientId)}/symptom-reports`, { method: "POST", body });
}

/** Public: numbers, disclaimer, demo flag and the offline fallback values (EmergencyConfigOut). */
export function getEmergencyConfig({ signal } = {}) {
  return request("/config/emergency", { signal });
}
