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

/** Marks a journal entry read. Repeating it keeps the first review. */
export function reviewJournalEntry(entryId) {
  return request(`/journal/${entryId}/review`, { method: "POST" });
}

/** New active care plan (the previous one is superseded); the rules use the new target immediately. */
export function updateCarePlan(patientId, body) {
  return request(`/patients/${patientId}/care-plan`, { method: "PUT", body });
}
