// Patient endpoints (contract/openapi.json). Shapes are the server's.
import { request } from "./client";

export function listMeasurements(patientId, { limit = 100, signal } = {}) {
  return request(`/patients/${patientId}/measurements`, { query: { limit }, signal });
}

export function getSummary(patientId, { signal } = {}) {
  return request(`/patients/${patientId}/summary`, { signal });
}

export function listActiveAlerts(patientId, { signal } = {}) {
  return request(`/patients/${patientId}/alerts`, { query: { status: "active" }, signal });
}

// Reading flow. Each answer carries the server's deterministic evaluation (EvaluationOut).
export function addMeasurement(patientId, body) {
  return request(`/patients/${patientId}/measurements`, { method: "POST", body });
}

export function addSymptomReport(patientId, body) {
  return request(`/patients/${patientId}/symptom-reports`, { method: "POST", body });
}

/** Public: numbers, disclaimer and the offline fallback values (EmergencyConfigOut). */
export function getEmergencyConfig({ signal } = {}) {
  return request("/config/emergency", { signal });
}
