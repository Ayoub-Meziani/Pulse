// Doctor-only endpoints. The server returns only actively assigned patients and answers 403 otherwise.
import { request } from "./client";

export function listMyPatients({ signal } = {}) {
  return request("/patients", { signal });
}

/** Experimental estimate written offline by the ML job. status: ok | insufficient_history | model_unavailable. */
export function getLatestPrediction(patientId, { signal } = {}) {
  return request(`/patients/${patientId}/predictions/latest`, { signal });
}

export function addNote(patientId, body) {
  return request(`/patients/${patientId}/notes`, { method: "POST", body });
}
