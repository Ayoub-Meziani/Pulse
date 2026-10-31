// Display helpers for the file-import answers (ImportResult, RingImportResult; contract/openapi.json).
// Formatting only: every count, level, alert and next step is the server's. Nothing here decides anything.
import { ApiError } from "../api/client";
import { unreachable } from "./readingFlow";

/** ReadingsImportIn.csv / RingImportIn.csv maxLength: a bigger file is refused before it is sent. */
export const MAX_CSV_CHARS = 300000;

/**
 * Same test as the server (api csv_import.declares_simulated): the first non-empty line starts with
 * "# SIMULATED" or "# SYNTHETIC". Such a file can only be imported as simulated (the server answers 422 otherwise).
 */
export function declaresSimulated(text) {
  const first = text.replace(/^﻿/, "").trimStart().split(/\r\n|\r|\n/, 1)[0].toLowerCase();
  return first.startsWith("# simulated") || first.startsWith("# synthetic");
}

// RejectedRow.reasons codes (api csv_import.py). Unknown codes are shown as sent.
const REASONS = {
  missing_measured_at: "date et heure manquantes",
  invalid_timestamp: "date et heure illisibles",
  missing_systolic: "systolique manquante",
  missing_diastolic: "diastolique manquante",
  not_integer_systolic: "systolique non entière",
  not_integer_diastolic: "diastolique non entière",
  not_integer_pulse: "pouls non entier",
  unsupported_unit: "unité non prise en charge",
  invalid_position: "position inconnue",
  invalid_arm: "bras inconnu",
  unknown_metric: "type de donnée inconnu",
  not_number_value: "valeur non numérique",
};

export function reasonLabel(code) {
  return code.startsWith("refused_by_database:") ? "refusée par la base (valeur hors limites)" : REASONS[code] ?? code;
}

/** Display counts of an ImportResult (cuff) or a RingImportResult (ring: inserted_by_metric instead of inserted). */
export function importCounts(result) {
  const byMetric = result.inserted_by_metric ?? null;
  return {
    total: result.rows_total,
    added: byMetric ? Object.values(byMetric).reduce((sum, n) => sum + n, 0) : result.inserted,
    duplicates: result.duplicates,
    rejected: result.rejected.map((r) => ({ row: r.row, reasons: r.reasons.map(reasonLabel) })),
    byMetric,
    byStatus: result.by_status ?? null,
    historical: result.historical ?? null,
    pastSevere: result.past_severe ?? null,
  };
}

/** Message for a failed import (the server's file message is English until the reviewed translation exists). */
export function importErrorText(error) {
  if (!(error instanceof ApiError)) return "Erreur inattendue. Réessayez.";
  if (error.code === "already_imported") return "Ce fichier a déjà été importé.";
  if (unreachable(error)) {
    return "La réponse du serveur n'est pas arrivée : le fichier a peut-être été importé, ou non. Renvoyez-le dans un instant ; s'il était déjà arrivé, il ne sera pas importé deux fois.";
  }
  const details = Array.isArray(error.details) ? error.details.map((d) => d.message).filter(Boolean) : [];
  if (error.code === "invalid_file") return `Fichier refusé : ${details[0] ?? error.message}`;
  if (error.status === 422) return `Valeurs refusées : ${details.join(" ; ") || error.message}`;
  if (error.status === 403) return "Vous ne pouvez pas importer de fichier pour ce compte.";
  return error.message || "Erreur inattendue. Réessayez.";
}
