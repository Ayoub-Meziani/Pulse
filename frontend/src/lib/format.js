// Display helpers only. Every value, level and label decision comes from the API.

export function formatDateTime(iso, timeZone) {
  if (!iso) return "—";
  try {
    return new Intl.DateTimeFormat("fr-FR", { dateStyle: "short", timeStyle: "short", timeZone }).format(new Date(iso));
  } catch {
    return new Intl.DateTimeFormat("fr-FR", { dateStyle: "short", timeStyle: "short" }).format(new Date(iso));
  }
}

export function formatShortDate(iso, timeZone) {
  try {
    return new Intl.DateTimeFormat("fr-FR", { day: "2-digit", month: "2-digit", timeZone }).format(new Date(iso));
  } catch {
    return new Intl.DateTimeFormat("fr-FR", { day: "2-digit", month: "2-digit" }).format(new Date(iso));
  }
}

export function round(value) {
  return value === null || value === undefined ? null : Math.round(value);
}

// What a reading is, as recorded by the server (MeasurementOut.provenance and .source).
export const PROVENANCE = {
  measured: { label: "Mesurée", tone: "bg-emerald-50 text-emerald-700" },
  estimated: { label: "Estimation", tone: "bg-amber-50 text-amber-700" },
  simulated: { label: "SIMULÉE", tone: "bg-violet-100 text-violet-800" },
};

export const SOURCE = {
  manual: "Saisie manuelle",
  device_sync: "Appareil",
  csv_import: "Import",
  simulated: "Simulation",
};

export const TREND = {
  rising: "en hausse",
  stable: "stable",
  falling: "en baisse",
  insufficient_data: "données insuffisantes",
};

// AlertOut.level -> label and the existing AlertCard colour variant. Presentation only.
export const ALERT_LEVEL = {
  notice: { title: "Avis", variant: "info" },
  trend: { title: "Tendance à surveiller", variant: "warning" },
  severe: { title: "Alerte sévère", variant: "critical" },
  emergency: { title: "Urgence", variant: "critical" },
};

// EvaluationOut.level -> heading on the result card. Presentation only: the level is the server's.
export const EVALUATION_LEVEL = {
  none: { title: "Mesure enregistrée", variant: "info" },
  notice: { title: "Au-dessus de l'objectif", variant: "warning" },
  trend: { title: "Tendance à surveiller", variant: "warning" },
  severe: { title: "Tension très élevée", variant: "critical" },
  emergency: { title: "Urgence", variant: "critical" },
};

// Symptom codes of the contract (schemas.Symptom), in the server's order. Which ones are red flags
// is decided by the server, never here.
export const SYMPTOMS = [
  ["chest_pain", "Douleur dans la poitrine"],
  ["shortness_of_breath", "Essoufflement"],
  ["back_pain", "Douleur dans le dos"],
  ["weakness", "Faiblesse"],
  ["numbness", "Engourdissement"],
  ["vision_change", "Trouble de la vision"],
  ["difficulty_speaking", "Difficulté à parler"],
  ["severe_headache", "Mal de tête intense"],
  ["confusion", "Confusion"],
  ["dizziness", "Vertiges"],
  ["nausea", "Nausées"],
  ["palpitations", "Palpitations"],
  ["other", "Autre symptôme"],
];

export const ALERT_STATUS = {
  open: "ouverte",
  acknowledged: "prise en compte",
  reviewed: "examinée par le médecin",
  resolved: "résolue",
};
