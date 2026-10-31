// Wording of escalation states (EscalationOut). Every label says exactly what the server knows:
// "envoyé" is not "lu", "vu" means a person pressed the button, and nothing says "appel passé" or
// "secours prévenus". Skipped steps say that PULSE did NOT notify that person.

const WHO = {
  doctor: (s) => s.target_label ?? "Votre médecin",
  facility: (s) => s.target_label ?? "L'établissement",
  contact: (s) => s.target_label ?? "Votre proche",
  emergency_services: () => "Secours (14)",
  patient: () => "Vous (rappel)",
};

const STATUS = {
  scheduled: "En attente d'envoi",
  sending: "Envoi en cours",
  sent: "Notification envoyée dans PULSE (pas encore affichée)",
  delivered: "Notification affichée sur son écran (pas encore confirmée)",
  acknowledged: "A vu l'alerte et l'a confirmée",
  failed: "Échec de l'envoi",
  expired: "Pas de confirmation à temps",
  cancelled: "Annulé",
};

const SKIPPED = {
  no_channel: "Non prévenu par PULSE : appelez-le/la vous-même",
  no_official_channel: "PULSE ne peut pas prévenir les secours : appelez le 14 vous-même",
  no_agreement: "Non prévenu : aucun accord avec cet établissement",
  not_verified: "Non prévenu : numéro non vérifié",
  no_consent: "Non prévenu : consentement manquant",
  superseded: "Remplacé par une étape suivante",
};

export function stepWho(step) {
  return (WHO[step.target_kind] ?? (() => step.target_kind))(step);
}

export function stepStatus(step) {
  if (step.status === "skipped") return SKIPPED[step.skip_reason] ?? "Non prévenu";
  return STATUS[step.status] ?? step.status;
}

export const ESCALATION_STATUS = {
  created: "Alerte créée — personne n'est encore prévenu",
  notification_attempted: "Notification envoyée",
  delivered: "Notification affichée chez le destinataire",
  acknowledged: "Quelqu'un a vu l'alerte et l'a confirmée",
  escalated: "Pas de confirmation : étape suivante",
  resolved: "Épisode clôturé",
  cancelled: "Alerte annulée",
};

/** The emergency-services step is recorded so the screen can say plainly that nobody called them. */
export function visibleSteps(escalation) {
  return (escalation?.steps ?? []).filter((s) => s.status !== "cancelled" || s.sent_at);
}

export function isActive(escalation) {
  return Boolean(escalation?.eligible) && !["resolved", "cancelled"].includes(escalation.status);
}
