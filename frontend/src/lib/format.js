// Display helpers only. Every value, level and label decision comes from the API.

export function formatDateTime(iso, timeZone) {
  if (!iso) return "—";
  try {
    return new Intl.DateTimeFormat("fr-FR", { dateStyle: "medium", timeStyle: "short", timeZone }).format(new Date(iso));
  } catch {
    return new Intl.DateTimeFormat("fr-FR", { dateStyle: "medium", timeStyle: "short" }).format(new Date(iso));
  }
}

export function formatDate(iso, timeZone) {
  if (!iso) return "—";
  try {
    return new Intl.DateTimeFormat("fr-FR", { dateStyle: "medium", timeZone }).format(new Date(iso));
  } catch {
    return new Intl.DateTimeFormat("fr-FR", { dateStyle: "medium" }).format(new Date(iso));
  }
}

export function formatShortDate(iso, timeZone) {
  try {
    return new Intl.DateTimeFormat("fr-FR", { day: "2-digit", month: "2-digit", timeZone }).format(new Date(iso));
  } catch {
    return new Intl.DateTimeFormat("fr-FR", { day: "2-digit", month: "2-digit" }).format(new Date(iso));
  }
}

/** "il y a 2 h", "il y a 3 j". Relative to the browser clock; only used next to an absolute date. */
export function formatAgo(iso, now = Date.now()) {
  if (!iso) return "";
  const minutes = Math.round((now - new Date(iso).getTime()) / 60000);
  if (minutes < 1) return "à l'instant";
  if (minutes < 60) return `il y a ${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `il y a ${hours} h`;
  return `il y a ${Math.round(hours / 24)} j`;
}

export function round(value) {
  return value === null || value === undefined ? null : Math.round(value);
}

export function initials(name) {
  return (name ?? "?").split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0].toUpperCase()).join("") || "?";
}

export const SOURCE = {
  manual: "Saisie manuelle",
  device_sync: "Appareil",
  csv_import: "Importée",
  simulated: "Simulée",
};

/**
 * Origin of a blood-pressure reading (MeasurementOut.source / provenance). Simulated and estimated values
 * never share the style of a measured one (design system §2.4).
 */
export function originOf(reading) {
  if (reading.provenance === "simulated" || reading.source === "simulated") {
    return { label: "Simulée", tone: "sim", icon: "flask", simulated: true };
  }
  if (reading.provenance === "estimated") return { label: "Estimation (bracelet)", tone: "wear", icon: "watch" };
  if (reading.source === "device_sync") return { label: "Appareil", tone: "brand", icon: "pulse" };
  if (reading.source === "csv_import") return { label: "Importée", tone: "neutral", icon: "note" };
  return { label: "Saisie manuelle", tone: "neutral", icon: "user" };
}

// MeasurementOut.validation_status, decided by the database (policy pulse-v1). "valid" has no badge.
export const VALIDATION = {
  needs_review: { label: "À vérifier", tone: "warning" },
  invalid: { label: "Invalide", tone: "danger" },
};

// MeasurementOut.quality_flags that make a reading invalid (policy pulse-v1), in plain French.
export const INVALID_FLAG = {
  systolic_not_above_diastolic: "le chiffre du haut doit être plus grand que celui du bas",
  systolic_implausible: "le chiffre du haut est hors de la plage possible",
  diastolic_implausible: "le chiffre du bas est hors de la plage possible",
  pulse_implausible: "le pouls est hors de la plage possible",
  measured_in_future: "l'heure de la mesure est dans le futur",
};

export const TREND = {
  rising: "en hausse",
  stable: "stable",
  falling: "en baisse",
  insufficient_data: "pas assez de mesures",
};

// AlertOut.level / EvaluationOut.level -> label, badge tone, icon. Presentation only.
export const ALERT_LEVEL = {
  none: { label: "Enregistrée", tone: "success", icon: "check" },
  low: { label: "Tension basse", tone: "warning", icon: "alert" },
  notice: { label: "Au-dessus de la cible", tone: "notice", icon: "info" },
  trend: { label: "Tendance élevée", tone: "trend", icon: "pulse" },
  severe: { label: "Très élevée", tone: "severe", icon: "alert" },
  emergency: { label: "Urgence", tone: "emergency", icon: "phone" },
};

// Result card after a reading: heading and the AlertCard variant. Presentation only.
export const EVALUATION_LEVEL = {
  none: { title: "Mesure enregistrée", variant: "info" },
  low: { title: "Tension basse", variant: "warning" },
  notice: { title: "Au-dessus de votre cible", variant: "warning" },
  trend: { title: "Tendance à surveiller", variant: "warning" },
  severe: { title: "Tension très élevée", variant: "critical" },
  emergency: { title: "Urgence", variant: "critical" },
};

/** Result card heading. An invalid reading never reads as "saved and fine". */
export function evaluationHeading(evaluation, measurement) {
  if (evaluation?.rule_id === "DATA-INVALID" || measurement?.validation_status === "invalid") {
    return { title: "Mesure non valide : elle n'est pas prise en compte", variant: "warning", invalid: true };
  }
  return EVALUATION_LEVEL[evaluation?.level] ?? { title: evaluation?.level, variant: "info" };
}

export const ALERT_STATUS = {
  open: { label: "Ouverte", tone: "danger" },
  acknowledged: { label: "Prise en compte", tone: "warning" },
  reviewed: { label: "Examinée par le médecin", tone: "brand" },
  resolved: { label: "Clôturée", tone: "neutral" },
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

export const SYMPTOM_LABEL = Object.fromEntries(SYMPTOMS);

// Wearable metrics (WearableSampleOut). Never blood pressure, never an alert input.
export const WEARABLE_METRIC = {
  heart_rate: { label: "Fréquence cardiaque", unit: "bpm" },
  spo2: { label: "SpO₂", unit: "%" },
  hrv_rmssd: { label: "VFC (RMSSD)", unit: "ms" },
  skin_temperature: { label: "Température cutanée", unit: "°C" },
};

export const DEVICE_TYPE = {
  bp_cuff: "Tensiomètre",
  wearable: "Bracelet / bague",
  phone_app: "Application",
  simulator: "Simulateur",
};

/** 0.734 -> "73 %". For model probabilities, never a measurement. */
export function formatPercent(p) {
  return p === null || p === undefined ? "—" : `${Math.round(p * 100)} %`;
}

// Ring model outputs shown to the doctor (WearableFlagOut, WeeklyReportOut, BandOut). Advisory, never an alert.
export const FLAG_KIND = {
  early_warning: "Alerte précoce (prévision)",
  outside_reference: "Hors référence",
  personal_anomaly: "Inhabituel pour ce patient",
  multivariate_anomaly: "Anomalie combinée",
};

export const FLAG_WINDOW = { live_10min: "direct (10 min)", night: "nuit", forecast: "prévision" };

// Flag metrics beyond the four ring metrics of WEARABLE_METRIC.
const FLAG_ONLY_METRIC = { multivariate: "Plusieurs mesures combinées", sleep: "Sommeil (nuit agitée)" };

export function flagMetricLabel(metric) {
  return WEARABLE_METRIC[metric]?.label ?? FLAG_ONLY_METRIC[metric] ?? metric;
}

export const FLAG_REVIEW = {
  open: { label: "À examiner", tone: "warning" },
  confirmed: { label: "Confirmé", tone: "brand" },
  dismissed: { label: "Écarté", tone: "neutral" },
};

export const HOME_BP_CATEGORY = { normal: "normale", elevated: "élevée", stage_1_range: "stade 1", stage_2_range: "stade 2" };

export const CONTROL_STATUS = {
  at_or_below_target: "à la cible ou en dessous",
  above_target: "au-dessus de la cible",
  insufficient_data: "données insuffisantes",
};

export const REPORT_STATUS = {
  ready: { label: "À examiner", tone: "warning" },
  reviewed: { label: "Examiné", tone: "success" },
};

export const BAND_STATISTIC = {
  night_median: "médiane de nuit",
  night_min: "minimum de nuit",
  live_10min_median: "médiane 10 min en direct",
};

export const BAND_STATUS = {
  proposed: { label: "Proposée", tone: "warning" },
  active: { label: "Active", tone: "success" },
  superseded: { label: "Remplacée", tone: "neutral" },
  rejected: { label: "Refusée", tone: "neutral" },
};

export const BAND_BASIS = { reference: "référence générale", model_proposal: "proposée par le modèle", doctor: "fixée par le médecin" };
