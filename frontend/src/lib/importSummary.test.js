// Import display helpers. Fixtures follow ImportResult / RingImportResult / ErrorOut of contract/openapi.json.
import { describe, expect, it } from "vitest";
import { ApiError } from "../api/client";
import { csvKind, declaresSimulated, importCounts, importErrorText, reasonLabel } from "./importSummary";

describe("csvKind: which import panel a file belongs to", () => {
  it("reads the header after comment lines and a BOM, like the server", () => {
    expect(csvKind("﻿# SIMULATED example\r\nmeasured_at,systolic,diastolic,pulse\r\n2026-10-20 08:00,128,82,70\r\n")).toBe("cuff");
    expect(csvKind("# SIMULATED ring\nmeasured_at,metric,value,unit,external_id\n")).toBe("ring");
    expect(csvKind('"Measured_At","Metric","Value"\n')).toBe("ring");
  });

  it("unknown or ambiguous headers: no guess", () => {
    expect(csvKind("# only a comment\n")).toBeNull();
    expect(csvKind("date,top,bottom\n")).toBeNull();
    expect(csvKind("measured_at,systolic,diastolic,metric,value\n")).toBeNull();
  });
});

describe("importErrorText: the server's file errors in French", () => {
  const fileError = (code, message) => new ApiError(422, "invalid_file", message, [{ field: "csv", code, message }]);

  it("names the missing columns (the cuff example sent to the ring panel)", () => {
    expect(importErrorText(fileError("missing_column", "The file is missing column(s): metric, value.")))
      .toBe("Fichier refusé : colonne(s) obligatoire(s) manquante(s) : metric, value.");
  });

  it("known codes in French, unknown ones as sent", () => {
    expect(importErrorText(fileError("empty_file", "The file is empty."))).toBe("Fichier refusé : le fichier est vide.");
    expect(importErrorText(fileError("file_is_simulated", "x"))).toMatch(/importez-le comme données simulées/);
    expect(importErrorText(fileError("invalid_timezone", "x"))).toMatch(/Mon profil/);
    expect(importErrorText(fileError("something_new", "Server text."))).toBe("Fichier refusé : Server text.");
  });
});

describe("declaresSimulated", () => {
  it("first non-empty line, BOM and case ignored", () => {
    expect(declaresSimulated("# SIMULATED demo\nmeasured_at,systolic,diastolic\n")).toBe(true);
    expect(declaresSimulated("﻿\r\n  \r\n  # Synthetic cohort\r\nmeasured_at")).toBe(true);
  });

  it("a marker after the first line, or another comment, does not count", () => {
    expect(declaresSimulated("measured_at,systolic,diastolic\n# SIMULATED\n")).toBe(false);
    expect(declaresSimulated("# export of my cuff\n# SIMULATED\n")).toBe(false);
    expect(declaresSimulated("")).toBe(false);
  });
});

describe("reasonLabel", () => {
  it("known codes in French, database refusals grouped, unknown codes as sent", () => {
    expect(reasonLabel("missing_systolic")).toBe("systolique manquante");
    expect(reasonLabel("refused_by_database:measurements_systolic_check")).toBe("refusée par la base (valeur hors limites)");
    expect(reasonLabel("something_new")).toBe("something_new");
  });
});

describe("importCounts", () => {
  it("cuff import: server counts as sent", () => {
    const c = importCounts({
      rows_total: 6, inserted: 3, duplicates: 1, historical: 2, past_severe: 1,
      by_status: { valid: 2, needs_review: 1, invalid: 0 },
      rejected: [{ row: 4, reasons: ["missing_systolic", "invalid_timestamp"] }],
    });
    expect(c).toMatchObject({ total: 6, added: 3, duplicates: 1, historical: 2, pastSevere: 1, byMetric: null,
      byStatus: { valid: 2, needs_review: 1, invalid: 0 } });
    expect(c.rejected).toEqual([{ row: 4, reasons: ["systolique manquante", "date et heure illisibles"] }]);
  });

  it("ring import: added is the sum per metric, no cuff fields", () => {
    const c = importCounts({ rows_total: 5, inserted_by_metric: { heart_rate: 3, spo2: 1 }, duplicates: 0,
      rejected: [{ row: 6, reasons: ["unknown_metric"] }] });
    expect(c).toMatchObject({ total: 5, added: 4, byMetric: { heart_rate: 3, spo2: 1 }, byStatus: null, historical: null });
  });
});

describe("importErrorText", () => {
  it("already imported, file refused (first detail), other 422", () => {
    expect(importErrorText(new ApiError(409, "already_imported", "This file was already imported."))).toBe("Ce fichier a déjà été importé.");
    expect(importErrorText(new ApiError(422, "invalid_file", "x", [{ field: "csv", code: "missing_column", message: "Missing systolic." }])))
      .toBe("Fichier refusé : Missing systolic.");
    expect(importErrorText(new ApiError(422, "validation_error", "Invalid.", [{ message: "too long" }]))).toBe("Valeurs refusées : too long");
    expect(importErrorText(new Error("boom"))).toBe("Erreur inattendue. Réessayez.");
  });

  it("no answer (network error or 5xx): the import may have happened, never reads as 'nothing done'", () => {
    for (const e of [new ApiError(0, "network_error", "Impossible de joindre le serveur."), new ApiError(502, "bad_gateway", "Bad gateway.")]) {
      expect(importErrorText(e)).toMatch(/a peut-être été importé/);
    }
    expect(importErrorText(new ApiError(403, "forbidden", "No."))).toBe("Vous ne pouvez pas importer de fichier pour ce compte.");
  });
});
