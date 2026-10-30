// Read endpoints of the patient dashboard (contract/openapi.json). Shapes are the server's.
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
