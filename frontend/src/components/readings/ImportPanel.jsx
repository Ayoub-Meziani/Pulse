import { useId, useState } from "react";
import { useNavigate } from "react-router";
import { importReadings, listAlerts } from "../../api/patient";
import AlertList from "../alerts/AlertList";
import { LevelBadge } from "../ui/Badge";
import Button from "../ui/Button";
import Icon from "../ui/Icon";
import { Section } from "../ui/States";
import { formatDateTime } from "../../lib/format";
import { declaresSimulated, importCounts, importErrorText, MAX_CSV_CHARS } from "../../lib/importSummary";
import { useResource } from "../../lib/useResource";

// Cuff CSV import. The server parses the file, validates every row and runs the reading rules on the fresh
// measured ones; this panel only sends the text and shows the answer (ImportResult).

const ORIGINS = [["measured", "Mesures réelles de mon tensiomètre"], ["simulated", "Données simulées (démo)"]];
const SHOWN_REJECTED = 50;

/**
 * File input + required origin choice (no default), shared with the ring import. choices: [[value, label]], the
 * simulated one being "simulated". A file that declares itself simulated can only be sent as simulated.
 */
export function CsvImportForm({ choices, busy, onSubmit }) {
  const name = useId();
  const [file, setFile] = useState(null);  // { name, text }
  const [origin, setOrigin] = useState(null);
  const [problem, setProblem] = useState(null);
  const forced = file !== null && declaresSimulated(file.text);
  const chosen = forced ? "simulated" : origin;

  async function pick(event) {
    const input = event.target;
    const f = input.files?.[0];
    setFile(null);
    setOrigin(null);  // a new file needs a new answer
    setProblem(null);
    if (!f) return;
    let text;
    try {
      text = await f.text();
    } catch {
      setProblem("Impossible de lire ce fichier.");
      return;
    }
    if (!text.trim()) {
      setProblem("Ce fichier est vide.");
      return;
    }
    if (text.length > MAX_CSV_CHARS) {
      input.value = "";
      setProblem(`Fichier trop volumineux (plus de ${MAX_CSV_CHARS.toLocaleString("fr-FR")} caractères) : découpez-le en plusieurs fichiers.`);
      return;
    }
    setFile({ name: f.name, text });
  }

  function submit(event) {
    event.preventDefault();
    if (file && chosen && !busy) onSubmit(file, chosen);
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <label className="block text-sm font-medium text-ink">Fichier CSV
        <input type="file" accept=".csv,text/csv" onChange={pick}
          className="mt-1.5 block w-full text-sm text-ink-muted file:mr-3 file:min-h-11 file:rounded-xl file:border-0 file:bg-brand-soft file:px-4 file:font-semibold file:text-brand" />
      </label>
      {problem && <p role="alert" className="flex gap-2 rounded-xl bg-danger-soft px-4 py-3 text-sm text-danger"><Icon name="alert" size={18} />{problem}</p>}
      <fieldset>
        <legend className="text-sm font-medium text-ink">Ce fichier contient <span className="font-normal text-ink-muted">(obligatoire)</span></legend>
        <div className="mt-1.5 grid grid-cols-1 gap-2 sm:grid-cols-2">
          {choices.map(([value, text]) => {
            const off = forced && value !== "simulated";
            return (
              <label key={value} className={`flex min-h-11 items-center gap-3 rounded-xl border px-3 py-2 text-sm ${
                off ? "cursor-not-allowed border-line text-ink-subtle" : chosen === value ? "cursor-pointer border-brand bg-brand-soft text-ink" : "cursor-pointer border-line text-ink hover:bg-surface-muted"
              }`}>
                <input type="radio" name={name} className="h-4 w-4 accent-[#0b5cad]" value={value}
                  checked={chosen === value} disabled={off} onChange={() => setOrigin(value)} />
                {text}
              </label>
            );
          })}
        </div>
        {forced && (
          <p className="mt-2 text-sm text-sim">
            La première ligne de ce fichier le déclare simulé (« # SIMULATED » ou « # SYNTHETIC ») : il ne peut être importé que comme données simulées.
          </p>
        )}
      </fieldset>
      <Button type="submit" disabled={busy || !file || !chosen}><Icon name="upload" size={18} />{busy ? "Import en cours…" : "Importer le fichier"}</Button>
    </form>
  );
}

/** Counts, rejected rows and the server's next step, shared with the ring import. */
export function ImportSummary({ counts, nextStep, children }) {
  const more = counts.rejected.length - SHOWN_REJECTED;
  return (
    <div className="space-y-4 rounded-xl border border-line p-4">
      <p className="flex items-center gap-2 text-sm font-medium text-success"><Icon name="check" size={18} />Fichier traité par le serveur · {counts.total} ligne(s) lue(s)</p>
      <dl className="grid grid-cols-3 gap-3">
        {[["Ajoutées", counts.added], ["Doublons ignorés", counts.duplicates], ["Rejetées", counts.rejected.length]].map(([text, n]) => (
          <div key={text} className="rounded-xl bg-surface-muted p-3">
            <dt className="text-xs font-medium uppercase tracking-wide text-ink-subtle">{text}</dt>
            <dd className="tnum mt-1 text-xl font-semibold text-ink">{n}</dd>
          </div>
        ))}
      </dl>
      {children}
      {counts.rejected.length > 0 && (
        <div>
          <p className="text-sm font-semibold text-ink">Lignes rejetées</p>
          <ul className="mt-1 space-y-1 text-sm text-ink-muted">
            {counts.rejected.slice(0, SHOWN_REJECTED).map((r, i) => (
              <li key={`${r.row}-${i}`}><span className="tnum">{r.row === null ? "Ligne ?" : `Ligne ${r.row}`}</span> : {r.reasons.join(", ")}</li>
            ))}
            {more > 0 && <li>… et {more} autre(s) ligne(s) rejetée(s).</li>}
          </ul>
        </div>
      )}
      <div>
        <p className="text-sm font-medium text-ink">{nextStep}</p>
        <p className="mt-1 text-xs text-ink-subtle">Consigne du serveur (texte en anglais en attendant la traduction validée).</p>
      </div>
    </div>
  );
}

// After 409 already_imported: the first try may have raised an alert whose answer was lost, so show what is pending.
function ActiveAlerts({ patientId, timeZone }) {
  const alerts = useResource((signal) => listAlerts(patientId, { status: "active", signal }), `ia:${patientId}`);
  return (
    <div>
      <p className="text-sm font-semibold text-ink">Vos alertes en cours</p>
      <div className="mt-2">
        <Section state={alerts} what="vos alertes">
          {(list) => list.length === 0 ? <p className="text-sm text-ink-muted">Aucune alerte en cours.</p> : <AlertList alerts={list} timeZone={timeZone} />}
        </Section>
      </div>
    </div>
  );
}

function ReadingsResult({ result, timeZone }) {
  const c = importCounts(result);
  return (
    <ImportSummary counts={c} nextStep={result.next_step}>
      <p className="text-sm text-ink-muted">
        Validation par le serveur : {c.byStatus.valid} valide(s), {c.byStatus.needs_review} à vérifier, {c.byStatus.invalid} invalide(s).
        {c.historical > 0 && <><br />{c.historical} mesure(s) de plus d'une heure : ajoutée(s) à l'historique, sans alerte.</>}
        {c.pastSevere > 0 && <> Dont <strong className="text-ink">{c.pastSevere} très élevée(s)</strong>.</>}
      </p>
      <div>
        <p className="text-sm font-semibold text-ink">Alertes créées ou mises à jour par ce fichier</p>
        <div className="mt-2">
          {result.alerts.length === 0 ? <p className="text-sm text-ink-muted">Aucune alerte.</p> : <AlertList alerts={result.alerts} timeZone={timeZone} />}
        </div>
      </div>
      {result.simulated_preview.length > 0 && (
        <div className="rounded-xl border border-dashed border-sim/50 bg-sim-soft p-4">
          <p className="flex items-center gap-2 text-sm font-semibold text-sim"><Icon name="flask" size={16} />Ce que les règles auraient fait — aucune alerte créée (données simulées)</p>
          <ul className="mt-2 space-y-1.5">
            {result.simulated_preview.map((p, i) => (
              <li key={`${p.measured_at}-${i}`} className="flex flex-wrap items-center gap-2 text-sm">
                <span className="tnum text-ink-muted">{formatDateTime(p.measured_at, timeZone)}</span><LevelBadge level={p.level} />
              </li>
            ))}
          </ul>
        </div>
      )}
    </ImportSummary>
  );
}

export default function ImportPanel({ patientId, timeZone, onImported }) {
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  async function send(file, provenance) {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      // No tz: timestamps without an offset are read in the profile's zone by the server.
      const r = await importReadings(patientId, { file_name: file.name, csv: file.text, provenance });
      onImported?.();
      if (r.evaluation?.requires_symptom_check) {
        // Same flow as after a manual reading: symptom check, then the server's recheck timer or emergency screen.
        navigate("/patient/mesure?mode=symptomes", { state: { result: { measurement: r.measurement, evaluation: r.evaluation } } });
        return;
      }
      setResult(r);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      <p className="text-sm text-ink-muted">
        Export CSV de votre tensiomètre : colonnes measured_at, systolic, diastolic (pulse, unit, position, arm, note facultatives).
        Les mesures de moins d'une heure passent par les mêmes règles qu'une saisie ; les plus anciennes rejoignent l'historique sans alerte.
      </p>
      <CsvImportForm choices={ORIGINS} busy={busy} onSubmit={send} />
      {error && (
        <div className="space-y-3">
          <p role="alert" className="flex gap-2 rounded-xl bg-danger-soft px-4 py-3 text-sm text-danger"><Icon name="alert" size={18} />{importErrorText(error)}</p>
          {error.code === "already_imported" && <ActiveAlerts patientId={patientId} timeZone={timeZone} />}
        </div>
      )}
      {result && <ReadingsResult result={result} timeZone={timeZone} />}
    </div>
  );
}
