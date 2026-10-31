import { useState } from "react";
import { importRing } from "../../api/patient";
import { CsvImportForm, ErrorBox, ImportSummary } from "../readings/ImportPanel";
import Badge from "../ui/Badge";
import Icon from "../ui/Icon";
import { WEARABLE_METRIC } from "../../lib/format";
import { importCounts, importErrorText } from "../../lib/importSummary";

const SOURCES = [["csv_import", "Export réel de ma bague"], ["simulated", "Données simulées (démo)"]];

/** Ring CSV import (RingImportResult). Ring data is never read by the rules: it raises no alert, whatever the values. */
export default function RingImportPanel({ patientId, onImported }) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  async function send(file, source) {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(await importRing(patientId, { file_name: file.name, csv: file.text, source }));
      onImported?.();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  const counts = result && importCounts(result);
  return (
    <details className="group rounded-2xl border border-line bg-surface">
      <summary className="flex min-h-11 cursor-pointer list-none items-center gap-3 rounded-2xl px-4 py-3 text-sm font-semibold text-ink hover:bg-surface-muted [&::-webkit-details-marker]:hidden">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-wear-soft text-wear"><Icon name="upload" size={16} /></span>
        <span className="flex-1">Importer un export de ma bague (CSV)</span>
        <Icon name="chevron" size={18} className="shrink-0 text-ink-subtle transition-transform group-open:rotate-90" />
      </summary>
      <div className="space-y-4 border-t border-line p-4">
        <p className="flex gap-2 rounded-xl bg-wear-soft/60 px-4 py-3 text-sm text-ink-muted">
          <Icon name="info" size={18} className="mt-0.5 shrink-0 text-wear" />
          <span>Colonnes measured_at, metric (heart_rate, hrv_rmssd, spo2, skin_temperature), value. Les données de la bague
          ne déclenchent jamais d'alerte ni de consigne d'urgence, quelles que soient les valeurs.</span>
        </p>
        <CsvImportForm kind="ring" choices={SOURCES} busy={busy} onSubmit={send} />
        {error && <ErrorBox>{importErrorText(error)}</ErrorBox>}
        {counts && (
          <ImportSummary counts={counts} nextStep={result.next_step}>
            {Object.keys(counts.byMetric).length > 0 && (
              <ul className="flex flex-wrap gap-2">
                {Object.entries(counts.byMetric).map(([metric, n]) => (
                  <li key={metric}><Badge tone="wear" icon="watch">{WEARABLE_METRIC[metric]?.label ?? metric} : {n} ajoutée(s)</Badge></li>
                ))}
              </ul>
            )}
            <p className="text-sm text-ink-muted">Aucune alerte : les données de la bague ne passent par aucune règle.</p>
          </ImportSummary>
        )}
      </div>
    </details>
  );
}
