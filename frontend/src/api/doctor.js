// Doctor-only endpoints. The server returns only actively assigned patients and answers 403 otherwise.
import { request } from "./client";

export function listMyPatients({ signal } = {}) {
  return request("/patients", { signal });
}

/** Severe and emergency alerts of my patients not resolved yet (open, acknowledged, reviewed), with the reading. */
export function listDoctorAlerts({ signal } = {}) {
  return request("/doctor/alerts", { signal });
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

// Ring model outputs written by the offline jobs. Advisory: never an alert, never read by the rules, no notification.
// A server that does not serve them answers 404 "feature_disabled". First reviewer stands (409 already_reviewed).
/** Flags and live early warnings, newest first. */
export function listWearableFlags(patientId, { kind, review_status, limit, signal } = {}) {
  return request(`/patients/${patientId}/wearable-flags`, { query: { kind, review_status, limit }, signal });
}

/** body: { review_status: "confirmed" | "dismissed", review_note? } */
export function reviewFlag(flagId, body) {
  return request(`/wearable-flags/${flagId}/review`, { method: "POST", body });
}

/** Newest week first. */
export function listWeeklyReports(patientId, { limit, signal } = {}) {
  return request(`/patients/${patientId}/weekly-reports`, { query: { limit }, signal });
}

/** body: { doctor_comment? } */
export function reviewWeeklyReport(reportId, body) {
  return request(`/weekly-reports/${reportId}/review`, { method: "POST", body });
}

/** Personal ring ranges, proposed first. */
export function listBands(patientId, { signal } = {}) {
  return request(`/patients/${patientId}/bands`, { signal });
}

/** body: {} to approve as proposed, or { low, high } to edit first (basis becomes "doctor"). Only from proposed (409). */
export function approveBand(bandId, body = {}) {
  return request(`/bands/${bandId}/approve`, { method: "POST", body });
}

export function rejectBand(bandId) {
  return request(`/bands/${bandId}/reject`, { method: "POST" });
}
