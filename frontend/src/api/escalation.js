// Emergency escalation and in-app notifications (migration M11, contract/openapi.json, tag "escalation").
// Statuses are the server's: "sent" is not "read", "acknowledged" means a person pressed the button, and
// emergency services are never notified by PULSE (emergency_services_notified is always false).
import { request } from "./client";

export function getEscalation(eventId, { signal } = {}) {
  return request(`/emergency-events/${eventId}/escalation`, { signal });
}

export function getEscalationTimeline(eventId, { signal } = {}) {
  return request(`/emergency-events/${eventId}/timeline`, { signal });
}

/** "ok" or "need_help" ("need_help" notifies without waiting for the cancel delay). */
export function answerAlarm(eventId, response) {
  return request(`/emergency-events/${eventId}/patient-response`, { method: "POST", body: { response } });
}

export function cancelEscalation(eventId, reason) {
  return request(`/emergency-events/${eventId}/cancel`, { method: "POST", body: { reason } });
}

export function resolveEscalation(eventId, outcome) {
  return request(`/emergency-events/${eventId}/resolve`, { method: "POST", body: { outcome } });
}

export function listDoctorEscalations({ signal } = {}) {
  return request("/doctor/escalations", { signal });
}

/** Delivery receipt: this doctor's screen displayed the escalation. Repeat-safe. */
export function markStepDelivered(stepId) {
  return request(`/escalation-steps/${stepId}/delivered`, { method: "POST" });
}

export function acknowledgeStep(stepId) {
  return request(`/escalation-steps/${stepId}/acknowledge`, { method: "POST" });
}

export function listNotifications({ unread = false, signal } = {}) {
  return request("/me/notifications", { query: { unread: unread || undefined }, signal });
}

export function markNotificationRead(notificationId) {
  return request(`/notifications/${notificationId}/read`, { method: "POST" });
}
