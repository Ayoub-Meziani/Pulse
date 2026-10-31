import { useId, useState } from "react";
import { Link, useNavigate } from "react-router";
import { importReadings, listAlerts } from "../../api/patient";
import AlertCard from "../alerts/AlertCard";
import AlertList from "../alerts/AlertList";
import { LevelBadge } from "../ui/Badge";
import Button, { ButtonLink } from "../ui/Button";
import Icon from "../ui/Icon";
import StatTile from "../ui/StatTile";
import { Section } from "../ui/States";
import { formatDateTime } from "../../lib/format";
import { csvKind, declaresSimulated, importCounts, importErrorText, MAX_CSV_CHARS } from "../../lib/importSummary";
import { unreachable } from "../../lib/readingFlow";
import { useResource } from "../../lib/useResource";

// Cuff CSV import. The server parses the file, validates every row and runs the reading rules on the fresh
// measured ones; this panel only sends the text and shows the answer (ImportResult).

const ORIGINS = [["measured", "Mesures réelles de mon tensiomètre"], ["simulated", "Données simulées (démo)"]];
const SHOWN_REJECTED = 50;

// A file of the other kind, said before it is sent (the server would refuse it for missing columns).
const ELSEWHERE = {
  cuff: {
    text: "Ce fichier ressemble à un export de tensiomètre (colonnes systolic, diastolic) : importez-le depuis Historique › Importer un fichier.",
    to: "/patient/historique?importer=1", link: "Ouvrir Historique › Importer un fichier",
  },
  ring: {
    text: "Ce fichier ressemble à un export de bague (colonnes metric, value) : importez-le depuis le tableau de bord, carte « Bracelet (facultatif) ».",
    to: "/patient#bracelet", link: "Ouvrir la carte Bracelet",
  },
};

export function ErrorBox({ children }) {
  return (
    <p role="alert" className="flex animate-fade-up gap-2 rounded-xl border border-danger/30 bg-danger-soft px-4 py-3 text-sm text-danger">
      <Icon name="alert" size={18} className="mt-0.5 shrink-0" /><span>{children}</span>
    </p>
  );
}

/**
 * File input + required origin choice (no default), shared with the ring import. choices: [[value, label]], the
 * simulated one being "simulated". A file that declares itself simulated can only be sent as simulated.
 * kind ("cuff" | "ring"): what this panel imports; a file whose header is of the other kind is not sent.
 */
export function CsvImportForm({ kind, choices, busy, onSubmit }) {
  const name = useId();
  const [file, setFile] = useState(null);  // { name, text }
  const [origin, setOrigin] = useState(null);
  const [problem, setProblem] = useState(null);
  const forced = file !== null && declaresSimulated(file.text);
  const chosen = forced ? "simulated" : origin;
  const found = file && csvKind(file.text);
  const elsewhere = found && found !== kind ? ELSEWHERE[found] : null;

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
      if (input.files?.[0] === f) setProblem("Impossible de lire ce fichier.");
      return;
    }
    if (input.files?.[0] !== f) return;  // another file was picked while this one was read: only the latest counts
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
    if (file && chosen && !elsewhere && !busy) onSubmit(file, chosen);
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      {/* The input covers the whole zone (transparent), so a file can be dropped on it or picked with a click. */}
      <label className="relative flex min-h-28 cursor-pointer flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed border-line-strong/60 bg-surface-muted/50 px-4 py-5 text-center transition-colors hover:border-brand hover:bg-brand-soft/40 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-focus">
        <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-brand-soft text-brand"><Icon name="upload" size={22} /></span>
        <span className="text-sm font-semibold text-ink">Fichier CSV</span>
        <span className="text-xs text-ink-muted">{file ? file.name : "Cliquez pour choisir un fichier, ou déposez-le ici"}</span>
        <input type="file" accept=".csv,text/csv" onChange={pick} className="absolute inset-0 h-full w-full cursor-pointer opacity-0" />
      </label>
      {problem && <ErrorBox>{problem}</ErrorBox>}
      {elsewhere && (
        <div role="alert" className="flex animate-fade-up gap-2 rounded-xl border border-warning/30 bg-warning-soft px-4 py-3 text-sm text-warning">
          <Icon name="info" size={18} className="mt-0.5 shrink-0" />
          <div>
            <p>{elsewhere.text}</p>
            <Link to={elsewhere.to} className="mt-1 inline-flex min-h-11 items-center gap-1 font-semibold underline underline-offset-2">
              {elsewhere.link}<Icon name="chevron" size={16} />
            </Link>
          </div>
        </div>
      )}
      <fieldset>
        <legend className="text-sm font-medium text-ink">Ce fichier contient <span className="font-normal text-ink-muted">(obligatoire)</span></legend>
        <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
          {choices.map(([value, text]) => {
            const off = forced && value !== "simulated";
            const sim = value === "simulated";
            return (
              <label key={value} className={`flex min-h-14 items-center gap-3 rounded-2xl border px-4 py-3 text-sm transition-colors has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-focus ${
                off ? "cursor-not-allowed border-line text-ink-subtle opacity-70"
                  : chosen === value ? `cursor-pointer shadow-card text-ink ${sim ? "border-dashed border-sim bg-sim-soft" : "border-brand bg-brand-soft"}`
                    : `cursor-pointer bg-surface text-ink hover:border-line-strong ${sim ? "border-dashed border-sim/50" : "border-line"}`
              }`}>
                <input type="radio" name={name} className="h-4 w-4 shrink-0 accent-brand" value={value}
                  checked={chosen === value} disabled={off} onChange={() => setOrigin(value)} />
                <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-surface ${sim ? "text-sim" : "text-brand"}`}>
                  <Icon name={sim ? "flask" : kind === "ring" ? "watch" : "pulse"} size={16} />
                </span>
                <span className="font-medium">{text}</span>
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
      <Button type="submit" disabled={busy || !file || !chosen || !!elsewhere}><Icon name="upload" size={18} />{busy ? "Import en cours…" : "Importer le fichier"}</Button>
    </form>
  );
}

/** Counts, rejected rows and the server's next step, shared with the ring import. */
export function ImportSummary({ counts, nextStep, children }) {
  const more = counts.rejected.length - SHOWN_REJECTED;
  return (
    <div className="animate-fade-up space-y-4 rounded-2xl border border-line bg-surface p-4 shadow-card sm:p-5">
      <p className="flex items-center gap-2 text-sm font-semibold text-success">
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-success-soft"><Icon name="check" size={16} /></span>
        <span>Fichier traité par le serveur · <span className="tnum">{counts.total}</span> ligne(s) lue(s)</span>
      </p>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <StatTile label="Ajoutées" value={counts.added} icon="plus" />
        <StatTile label="Doublons ignorés" value={counts.duplicates} icon="refresh" />
        <StatTile label="Rejetées" value={counts.rejected.length} icon="close" />
      </div>
      {children}
      {counts.rejected.length > 0 && (
        <div>
          <p className="text-sm font-semibold text-ink">Lignes rejetées</p>
          <ul className="mt-2 divide-y divide-line overflow-hidden rounded-xl border border-line text-sm text-ink-muted">
            {counts.rejected.slice(0, SHOWN_REJECTED).map((r, i) => (
              <li key={`${r.row}-${i}`} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-3 py-2">
                <span className="tnum shrink-0 rounded-md bg-surface-muted px-2 py-0.5 text-xs font-semibold text-ink">{r.row === null ? "Ligne ?" : `Ligne ${r.row}`}</span>
                <span>{r.reasons.join(", ")}</span>
              </li>
            ))}
            {more > 0 && <li className="px-3 py-2">… et {more} autre(s) ligne(s) rejetée(s).</li>}
          </ul>
        </div>
      )}
      <div className="rounded-xl bg-surface-muted px-4 py-3">
        <p className="text-sm font-medium text-ink">{nextStep}</p>
        <p className="mt-1 text-xs text-ink-subtle">Consigne du serveur (texte en anglais en attendant la traduction validée).</p>
      </div>
    </div>
  );
}

// No answer (lost, server down), or 409 after an answer that was lost: the server's step for a recent reading of this
// file may never have been shown. The symptom check falls back on the offline emergency rules if the server is down.
function MissedStep() {
  return (
    <div className="space-y-3">
      <AlertCard variant="warning" title="Une mesure récente de ce fichier était très élevée ou très basse ?"
        message="Le serveur vous aurait demandé de vérifier vos symptômes : faites-le maintenant, puis refaites une mesure. Si vous vous sentez mal, utilisez le bouton Urgence." />
      <div className="flex flex-wrap gap-3">
        <ButtonLink to="/patient/mesure?mode=symptomes">Vérifier mes symptômes</ButtonLink>
        <ButtonLink to="/patient/mesure" variant="secondary">Nouvelle mesure</ButtonLink>
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

/** ImportResult of a cuff file. Also shown under the symptom check when the import leads there (AddReading). */
export function ReadingsResult({ result, timeZone }) {
  const c = importCounts(result);
  return (
    <ImportSummary counts={c} nextStep={result.next_step}>
      <p className="text-sm text-ink-muted">
        Validation par le serveur : {c.byStatus.valid} valide(s), {c.byStatus.needs_review} à vérifier, {c.byStatus.invalid} invalide(s), non prise(s) en compte.
        {c.historical > 0 && <><br />{c.historical} mesure(s) de plus de 10 minutes, ou antérieure(s) à votre dernière mesure : ajoutée(s) à l'historique, sans alerte.</>}
        {c.pastSevere > 0 && <> Dont <strong className="text-ink">{c.pastSevere} très élevée(s)</strong>.</>}
      </p>
      <div>
        <p className="text-sm font-semibold text-ink">Alertes créées ou mises à jour par ce fichier</p>
        <div className="mt-2">
          {result.alerts.length === 0 ? <p className="text-sm text-ink-muted">Aucune alerte.</p> : <AlertList alerts={result.alerts} timeZone={timeZone} />}
        </div>
      </div>
      {result.simulated_preview.length > 0 && (
        <div className="rounded-2xl border border-dashed border-sim/50 bg-sim-soft p-4">
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

/** onBusy(true | false): lets the page keep the panel open while a file is being sent (its answer must be seen). */
export default function ImportPanel({ patientId, timeZone, onImported, onBusy }) {
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [sent, setSent] = useState(0);  // a fresh form after each import, so the same file is not sent again by mistake

  async function send(file, provenance) {
    setBusy(true);
    onBusy?.(true);
    setError(null);
    setResult(null);
    try {
      // No tz: timestamps without an offset are read in the profile's zone by the server.
      const r = await importReadings(patientId, { file_name: file.name, csv: file.text, provenance });
      onImported?.();
      if (r.evaluation?.requires_symptom_check) {
        // Same flow as after a manual reading: symptom check, then the server's recheck timer or emergency screen.
        // The whole answer goes along, so the counts and rejected rows are shown there too.
        navigate("/patient/mesure?mode=symptomes", {
          state: { result: { measurement: r.measurement, evaluation: r.evaluation }, importResult: r },
        });
        return;
      }
      setResult(r);
      setSent((n) => n + 1);
    } catch (e) {
      setError({ error: e, provenance });
    } finally {
      setBusy(false);
      onBusy?.(false);
    }
  }

  return (
    <div className="space-y-5">
      <p className="flex gap-2 rounded-xl bg-brand-soft/50 px-4 py-3 text-sm text-ink-muted">
        <Icon name="info" size={18} className="mt-0.5 shrink-0 text-brand" />
        <span>Export CSV de votre tensiomètre : colonnes measured_at, systolic, diastolic (pulse, unit, position, arm, note facultatives).
        Les mesures de moins de 10 minutes, plus récentes que votre dernière mesure, passent par les mêmes règles qu'une saisie ; les autres rejoignent l'historique sans alerte.</span>
      </p>
      <CsvImportForm key={sent} kind="cuff" choices={ORIGINS} busy={busy} onSubmit={send} />
      {error && (
        <div className="space-y-3">
          <ErrorBox>{importErrorText(error.error)}</ErrorBox>
          {/* Only measured rows can ask for a symptom check; a simulated file never does. */}
          {error.provenance === "measured" && (unreachable(error.error) || error.error.code === "already_imported") && <MissedStep />}
          {error.error.code === "already_imported" && <ActiveAlerts patientId={patientId} timeZone={timeZone} />}
        </div>
      )}
      {result && <ReadingsResult result={result} timeZone={timeZone} />}
    </div>
  );
}
