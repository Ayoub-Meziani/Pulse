// Screen sequence for one reading (docs/API_CONTRACT.md, model: feat/web-scaffold web/src/flow.ts).
// The server decides every level and flag (EvaluationOut); this file only decides which screen comes
// next. The only thresholds used here are the server's own client_fallback values, and only when the
// API cannot be reached (EmergencyConfigOut.client_fallback).

/**
 * After POST /patients/{id}/measurements.
 * symptomsGiven: symptoms the patient ticked on the form, posted next whatever the reading says.
 */
export function afterMeasurement(result, symptomsGiven = []) {
  const ev = result.evaluation;
  if (ev.show_emergency) return { kind: "emergency", reason: ev.reason, nextStep: ev.next_step };
  if (symptomsGiven.length > 0) return { kind: "send_symptoms", result, symptoms: symptomsGiven };
  if (ev.requires_symptom_check) return { kind: "symptoms", result };
  return { kind: "done", result };
}

/** After POST /patients/{id}/symptom-reports. measurementResult is null for a symptom-only report. */
export function afterSymptoms(measurementResult, report) {
  const ev = report.evaluation;
  if (ev.show_emergency) return { kind: "emergency", reason: ev.reason, nextStep: ev.next_step };
  const seconds = measurementResult?.evaluation.recheck_after_seconds;
  if (seconds) return { kind: "recheck_wait", result: measurementResult, report, seconds };
  return { kind: "done", result: measurementResult, report };
}

/**
 * The reading could not be sent. Uses only the server-provided fallback (null if the emergency
 * configuration could not be loaded either): emergency screen when it says so, otherwise an error.
 */
export function whenUnreachable(reading, symptoms, fallback) {
  if (!fallback) return { kind: "unreachable", emergency: false };
  const severe = reading !== null && (reading.systolic >= fallback.severe_systolic
    || reading.diastolic >= fallback.severe_diastolic);
  const redFlag = symptoms.some((s) => fallback.red_flag_symptoms.includes(s));
  return { kind: "unreachable", emergency: severe || redFlag };
}

/**
 * Client id that makes POST /measurements repeat-safe (D17). The same values keep the same id, so a retry
 * after a timeout or a double tap returns the stored reading instead of creating a second one. Changed
 * values get a new id (the server would answer 409 for an old id with other values).
 */
export function readingRequest(previous, body, newId = () => crypto.randomUUID()) {
  const key = JSON.stringify(body);
  return previous && previous.key === key ? previous : { key, id: newId() };
}
