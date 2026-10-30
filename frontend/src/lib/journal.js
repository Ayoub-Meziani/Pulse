// Contract categories (JournalIn.category), with the patient-facing French label.
export const JOURNAL_CATEGORIES = [
  ["food", { label: "Alimentation", placeholder: "Ex. : déjeuner — chorba et pain, salade ; peu de sel." }],
  ["activity", { label: "Activité physique", placeholder: "Ex. : marche de 30 minutes après le dîner." }],
  ["symptoms", { label: "Symptômes", placeholder: "Ex. : maux de tête légers en fin de journée." }],
  ["medication", { label: "Médicaments", placeholder: "Ex. : comprimé du soir oublié hier." }],
  ["question", { label: "Question pour mon médecin", placeholder: "Ex. : puis-je reprendre le vélo ?" }],
  ["other", { label: "Autre", placeholder: "" }],
];

export const JOURNAL_LABEL = Object.fromEntries(JOURNAL_CATEGORIES.map(([code, c]) => [code, c.label]));
