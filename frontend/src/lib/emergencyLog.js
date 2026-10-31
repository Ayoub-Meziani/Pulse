// The emergency incident record, shared by the emergency screen and the alarm's call button. Every tap is queued on
// this device and sent in the background (lib/incident.js): nothing on screen waits for it, and it says "tapped",
// never "called".
import { addEmergencyActions, patchEmergencyEvent, startEmergencyEvent } from "../api/patient";
import { browserStore, flushIncidents } from "./incident";

export const incidentStore = browserStore();
export const INCIDENT_API = { start: startEmergencyEvent, actions: addEmergencyActions, patch: patchEmergencyEvent };

/** Sends what is queued; failures stay queued for the next try. */
export const flushQueued = (patientId) => flushIncidents(incidentStore, INCIDENT_API, patientId).catch(() => {});
