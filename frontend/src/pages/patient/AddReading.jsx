import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router";
import { useAuth } from "../../auth/AuthContext";
import { ApiError } from "../../api/client";
import { addMeasurement, addSymptomReport, getEmergencyConfig } from "../../api/patient";
import AlertCard from "../../components/alerts/AlertCard";
import { ReadingsResult } from "../../components/readings/ImportPanel";
import { OriginBadge, ValidationBadge } from "../../components/ui/Badge";
import Button, { ButtonLink } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import Icon from "../../components/ui/Icon";
import { evaluationHeading, formatDateTime, INVALID_FLAG, SYMPTOMS } from "../../lib/format";
import { cacheConfig, readCachedConfig } from "../../lib/offlineCache";
import { afterMeasurement, afterSymptoms, readingRequest, unreachable, whenUnreachable } from "../../lib/readingFlow";
import EmergencyScreen from "./EmergencyScreen";

// Reading -> server evaluation -> next screen. Every level, flag, delay and message is the
// server's (EvaluationOut); readingFlow.js only picks the screen. Nothing is shown as saved before
// the server has answered.

function errorText(error) {
  if (!(error instanceof ApiError)) return "Erreur inattendue. Réessayez.";
  if (error.code === "conflict") return "Cette mesure a déjà été envoyée avec d'autres valeurs. Rechargez la page puis recommencez.";
  if (error.status === 422) {
    const fields = Array.isArray(error.details) ? error.details.map((d) => d.message).filter(Boolean) : [];
    return `Valeurs refusées : ${fields.join(" ; ") || error.message}`;
  }
  if (error.status === 403) return "Vous ne pouvez pas enregistrer de mesure pour ce compte.";
  return error.message || "Erreur inattendue. Réessayez.";
}

function nowLocalInput() {
  const d = new Date();
  d.setSeconds(0, 0);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}

function toInt(value) {
  const n = Number(value);
  return value.trim() !== "" && Number.isInteger(n) ? n : null;
}

const field = "field mt-1.5";
const label = "text-sm font-medium text-ink";
const big = "field mt-2 py-4 text-center text-4xl font-extrabold tracking-tight tnum placeholder:text-line-strong/60";

// Display only: where the patient is in the flow. readingFlow.js decides the steps, not this list.
const STEPS = ["Mesure", "Symptômes", "Contrôle", "Résultat"];

function stepIndex(step) {
  if (step.kind === "form") return step.recheck ? 2 : 0;
  return { symptoms: 1, recheck_wait: 2, done: 3 }[step.kind] ?? -1;
}

function Stepper({ current }) {
  return (
    <ol aria-label="Étapes" className="flex gap-2">
      {STEPS.map((name, i) => (
        <li key={name} aria-current={i === current ? "step" : undefined} className="min-w-0 flex-1">
          <span aria-hidden="true" className="block h-1.5 overflow-hidden rounded-full bg-line">
            <span className={`block h-full origin-left rounded-full bg-linear-to-r from-brand to-glow transition-transform duration-500 ease-(--ease-out-expo) ${i <= current ? "scale-x-100" : "scale-x-0"}`} />
          </span>
          <span className={`mt-2 block truncate text-xs font-semibold sm:text-sm ${i === current ? "text-brand" : i < current ? "text-ink" : "text-ink-subtle"}`}>
<span className="tnum hidden sm:inline">{i + 1} · </span>{name}
          </span>
        </li>
      ))}
    </ol>
  );
}

function SymptomBoxes({ selected, onChange }) {
  function toggle(code) {
    onChange(selected.includes(code) ? selected.filter((s) => s !== code) : [...selected, code]);
  }
  return (
    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
      {SYMPTOMS.map(([code, text]) => (
        <label key={code} className={`flex min-h-13 cursor-pointer items-center gap-3 rounded-2xl border px-4 py-3 text-sm font-medium text-ink transition-[border-color,background-color,box-shadow,transform] duration-200 hover:-translate-y-px ${
          selected.includes(code) ? "border-brand bg-brand-soft ring-1 ring-brand" : "border-line bg-surface hover:border-line-strong hover:shadow-card"
        }`}>
          <input type="checkbox" className="h-5 w-5 shrink-0 accent-brand" checked={selected.includes(code)} onChange={() => toggle(code)} />
          {text}
        </label>
      ))}
    </div>
  );
}

function ReadingForm({ recheck, guidance, onSubmit }) {
  const [systolic, setSystolic] = useState("");
  const [diastolic, setDiastolic] = useState("");
  const [pulse, setPulse] = useState("");
  const [measuredAt, setMeasuredAt] = useState(nowLocalInput);
  // A recheck may be asked lying down (R-LOW-2): no preset, so the stored position is never a guess.
  const [position, setPosition] = useState(recheck ? "" : "sitting");
  const [rested, setRested] = useState(false);
  const [symptoms, setSymptoms] = useState([]);
  const [showSymptoms, setShowSymptoms] = useState(false);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function submit(event) {
    event.preventDefault();
    if (busy) return;
    const sys = toInt(systolic);
    const dia = toInt(diastolic);
    if (sys === null || dia === null || (pulse.trim() !== "" && toInt(pulse) === null)) {
      setError("Saisissez des nombres entiers (par exemple 128 et 82).");
      return;
    }
    setBusy(true);
    setError(null);
    // Plausibility and levels are decided by the server; its message is shown as it is.
    const err = await onSubmit({
      systolic: sys, diastolic: dia, pulse: toInt(pulse),
      measured_at: new Date(measuredAt).toISOString(), body_position: position || null, rested_5_min: rested,
    }, symptoms);
    setBusy(false);
    if (err) setError(err);
  }

  return (
    <Card as="form" variant="elevated" onSubmit={submit} className="animate-fade-up p-5 sm:p-8" noValidate>
      <div className="flex items-center gap-3">
        <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-linear-to-br from-brand to-brand-hover text-white shadow-glow-brand">
          <Icon name={recheck ? "refresh" : "pulse"} size={22} />
        </span>
        <h1 className="text-2xl font-extrabold tracking-tight text-ink sm:text-3xl">{recheck ? "Mesure de contrôle" : "Nouvelle mesure"}</h1>
      </div>
      <p className="mt-1 text-sm text-ink-muted">
        {recheck ? "Reprenez votre tension maintenant, au calme, dans la position que demande la consigne." : "Recopiez les valeurs affichées par votre tensiomètre."}
      </p>
      {recheck && guidance && <p className="mt-3 rounded-xl border-l-4 border-brand bg-surface-muted px-4 py-3 text-sm text-ink">Consigne du serveur : {guidance}</p>}

      <div className="mt-6 grid grid-cols-2 gap-3 sm:gap-4">
        <label className={`${label} text-center`}>Systolique
          <span className="block text-xs font-normal text-ink-muted">chiffre du haut</span>
          <input className={big} inputMode="numeric" autoComplete="off" required
            value={systolic} onChange={(e) => setSystolic(e.target.value)} aria-describedby="unit-mmhg" />
        </label>
        <label className={`${label} text-center`}>Diastolique
          <span className="block text-xs font-normal text-ink-muted">chiffre du bas</span>
          <input className={big} inputMode="numeric" autoComplete="off" required
            value={diastolic} onChange={(e) => setDiastolic(e.target.value)} aria-describedby="unit-mmhg" />
        </label>
        <p id="unit-mmhg" className="col-span-2 -mt-1 text-center text-xs text-ink-subtle">Valeurs en mmHg.</p>
      </div>

      <div className="mt-5 grid gap-4 sm:grid-cols-2">
        <label className={label}>Pouls <span className="font-normal text-ink-muted">(facultatif, bpm)</span>
          <input className={`${field} tnum`} inputMode="numeric" autoComplete="off" value={pulse} onChange={(e) => setPulse(e.target.value)} />
        </label>
        <label className={label}>Date et heure
          <input className={field} type="datetime-local" required value={measuredAt} onChange={(e) => setMeasuredAt(e.target.value)} />
        </label>
        <label className={label}>Position
          <select className={field} value={position} onChange={(e) => setPosition(e.target.value)}>
            <option value="sitting">Assis</option>
            <option value="standing">Debout</option>
            <option value="lying">Allongé</option>
            <option value="">Non précisé</option>
          </select>
        </label>
        <label className="flex min-h-11 cursor-pointer items-center gap-3 self-end rounded-xl border border-line bg-surface px-3 py-2.5 text-sm text-ink transition-colors hover:border-line-strong has-checked:border-brand has-checked:bg-brand-soft">
          <input type="checkbox" className="h-5 w-5 shrink-0 accent-brand" checked={rested} onChange={(e) => setRested(e.target.checked)} />
          Repos de 5 minutes avant la mesure
        </label>
      </div>

      <div className="mt-6 overflow-hidden rounded-2xl border border-line bg-surface-muted/40">
        <button type="button" onClick={() => setShowSymptoms((v) => !v)} aria-expanded={showSymptoms}
          className="flex min-h-11 w-full items-center justify-between gap-3 px-4 py-3 text-left text-sm font-medium text-ink hover:bg-surface-muted">
          <span>Symptômes en ce moment <span className="font-normal text-ink-muted">(facultatif){symptoms.length ? ` · ${symptoms.length} sélectionné(s)` : ""}</span></span>
          <Icon name="chevron" size={18} className={`shrink-0 transition-transform duration-200 ${showSymptoms ? "rotate-90" : ""}`} />
        </button>
        {showSymptoms && <div className="animate-fade-in border-t border-line bg-surface p-4"><SymptomBoxes selected={symptoms} onChange={setSymptoms} /></div>}
      </div>

      {error && <p className="mt-5 flex gap-2 rounded-xl bg-danger-soft px-4 py-3 text-sm text-danger" role="alert"><Icon name="alert" size={18} className="shrink-0" />{error}</p>}
      <div className="mt-6 flex flex-wrap gap-3">
        <Button type="submit" disabled={busy} className="flex-1 sm:flex-none sm:px-6">{busy ? "Envoi en cours…" : "Enregistrer la mesure"}</Button>
        <ButtonLink to="/patient" variant="secondary">Annuler</ButtonLink>
      </div>
    </Card>
  );
}

function SymptomCheck({ onSubmit, intro }) {
  const [symptoms, setSymptoms] = useState([]);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function send(list) {
    if (busy) return;
    setBusy(true);
    setError(null);
    const err = await onSubmit(list);
    setBusy(false);
    if (err) setError(err);
  }

  return (
    <Card variant="elevated" className="animate-fade-up p-5 sm:p-8">
      <h2 className="text-xl font-extrabold tracking-tight text-ink sm:text-2xl">Avez-vous un de ces symptômes en ce moment ?</h2>
      {intro && <p className="mt-1 text-sm text-ink-muted">{intro}</p>}
      <div className="mt-5"><SymptomBoxes selected={symptoms} onChange={setSymptoms} /></div>
      {error && <p className="mt-4 rounded-xl bg-danger-soft px-4 py-3 text-sm text-danger" role="alert">{error}</p>}
      <div className="mt-6 flex flex-wrap gap-3">
        <Button disabled={busy || symptoms.length === 0} onClick={() => send(symptoms)}>Envoyer ces symptômes</Button>
        <Button variant="secondary" disabled={busy} onClick={() => send([])}>Aucun de ces symptômes</Button>
      </div>
    </Card>
  );
}

function RecheckTimer({ seconds, onReady }) {
  const [left, setLeft] = useState(seconds);
  useEffect(() => {
    if (left <= 0) return undefined;
    const id = setTimeout(() => setLeft((n) => n - 1), 1000);
    return () => clearTimeout(id);
  }, [left]);
  return (
    <Card className="flex animate-fade-up flex-col items-center gap-6 border-level-notice/30 bg-level-notice-soft p-5 text-center sm:flex-row sm:p-7 sm:text-left">
      <div className="relative h-28 w-28 shrink-0 text-level-notice" aria-hidden="true">
        <svg viewBox="0 0 120 120" className="h-full w-full -rotate-90">
          <circle cx="60" cy="60" r="52" fill="none" stroke="currentColor" strokeOpacity="0.15" strokeWidth="10" />
          <circle cx="60" cy="60" r="52" fill="none" stroke="currentColor" strokeWidth="10" strokeLinecap="round"
            pathLength="100" strokeDasharray="100" strokeDashoffset={100 * (1 - (seconds > 0 ? left / seconds : 0))}
            className="transition-[stroke-dashoffset] duration-1000 ease-linear" />
        </svg>
        <span className="absolute inset-0 flex items-center justify-center">
          {left > 0 ? <span className="tnum text-3xl font-extrabold">{left}<span className="text-base font-semibold"> s</span></span> : <Icon name="check" size={36} />}
        </span>
      </div>
      <div className="min-w-0">
        <h2 className="text-xl font-bold text-level-notice">Reposez-vous, puis reprenez votre tension</h2>
        <p className="tnum mt-2 text-level-notice" aria-live="polite">
          {left > 0 ? `Nouvelle mesure possible dans ${left} s.` : "Vous pouvez reprendre votre tension."}
        </p>
        <p className="mt-1 text-sm text-level-notice">Si vous vous sentez mal, utilisez le bouton Urgence.</p>
        <Button disabled={left > 0} onClick={onReady} className="mt-4">Reprendre ma tension</Button>
      </div>
    </Card>
  );
}

function ResultCard({ result, report, tz }) {
  const ev = report && !result ? report.evaluation : result?.evaluation;
  const m = result?.measurement;
  const level = evaluationHeading(ev, m);
  const reasons = (m?.quality_flags ?? []).filter((f) => INVALID_FLAG[f]).map((f) => INVALID_FLAG[f]);
  return (
    <div className="space-y-3">
      {m && (
        <Card variant="elevated" className="animate-scale-in p-5 sm:p-7">
          {level.invalid ? (
            <p className="flex items-start gap-2 text-sm font-medium text-danger"><Icon name="alert" size={18} className="mt-0.5 shrink-0" />Mesure enregistrée mais non valide : elle n'est utilisée ni pour vos moyennes, ni pour le graphique, ni pour les alertes</p>
          ) : (
            <p className="inline-flex items-center gap-2 rounded-full bg-success-soft px-3 py-1 text-sm font-semibold text-success"><Icon name="check" size={16} />Mesure enregistrée par le serveur</p>
          )}
          <p className="mt-4 flex flex-wrap items-baseline gap-x-2 font-extrabold tracking-tight text-ink">
            <span className="tnum animate-reveal text-5xl sm:text-6xl">{m.systolic}<span className="text-ink-subtle">/</span>{m.diastolic}</span>
            <span className="text-base font-medium text-ink-muted">mmHg</span>
          </p>
          <p className="mt-1 text-sm text-ink-muted">{formatDateTime(m.measured_at, tz)}{m.pulse ? ` · pouls ${m.pulse} bpm` : ""}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <OriginBadge reading={m} />
            <ValidationBadge status={m.validation_status} />
          </div>
          {level.invalid && reasons.length > 0 && <p className="mt-3 text-sm text-ink">Raison : {reasons.join(" ; ")}.</p>}
        </Card>
      )}
      {ev && <AlertCard title={level.title} message={`${ev.reason} ${ev.next_step}`.trim()} variant={level.variant} />}
      {report && result && (
        <p className="text-sm text-ink-muted">
          Symptômes enregistrés{report.report.symptoms.length === 0 ? " : aucun." : "."} {report.evaluation.next_step}
        </p>
      )}
      {report && !result && <p className="text-sm text-ink-muted">Vos symptômes ont été enregistrés. Votre médecin les verra lors du suivi.</p>}
      <p className="text-xs text-ink-subtle">Les consignes affichées viennent du serveur (texte en anglais en attendant la traduction validée).</p>
    </div>
  );
}

function ResendButton({ onResend }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  async function resend() {
    setBusy(true);
    setError(await onResend());
    setBusy(false);
  }
  return (
    <>
      <Button onClick={resend} disabled={busy}>{busy ? "Envoi…" : "Renvoyer la même mesure"}</Button>
      {error && <p className="w-full text-sm" role="alert">{error}</p>}
    </>
  );
}

export default function AddReading() {
  const { user } = useAuth();
  const [params] = useSearchParams();
  const symptomOnly = params.get("mode") === "symptomes";
  // A file import whose fresh reading needs a symptom check arrives with its result (ImportPanel): same flow as here.
  const location = useLocation();
  const navigate = useNavigate();
  const [importResult, setImportResult] = useState(() => location.state?.importResult ?? null);
  const [step, setStep] = useState(() => (symptomOnly ? { kind: "symptoms", result: location.state?.result ?? null }
    : { kind: "form", recheck: false }));
  const [config, setConfig] = useState(null);
  const pending = useRef(null);  // last request: same values -> same id (repeat-safe)

  // Read on every navigation (an import can finish while this page is already open)...
  const [seenKey, setSeenKey] = useState(location.key);
  if (location.key !== seenKey) {
    setSeenKey(location.key);
    if (location.state?.result || location.state?.importResult) {
      setStep({ kind: "symptoms", result: location.state.result ?? null });
      setImportResult(location.state.importResult ?? null);
    }
  }
  // ...then cleared: the browser keeps history state, so a reload or Back/Forward must not ask again about an old import.
  useEffect(() => {
    if (location.state) navigate(`${location.pathname}${location.search}`, { replace: true, state: null });
  }, [location, navigate]);

  // Loaded up front so the server's fallback values are at hand if the API drops mid-flow.
  useEffect(() => {
    const controller = new AbortController();
    getEmergencyConfig({ signal: controller.signal }).then((c) => { setConfig(c); cacheConfig(c); }).catch(() => {});
    return () => controller.abort();
  }, []);
  // The server's offline values: from this page's load, else the copy kept on the device (server already down).
  const fallback = () => (config ?? readCachedConfig())?.client_fallback;

  async function sendSymptoms(result, symptoms) {
    try {
      const report = await addSymptomReport(user.id, { symptoms, measurement_id: result?.measurement.id ?? null });
      const next = afterSymptoms(result, report);
      setStep(next.kind === "emergency" ? { ...next, trigger: "symptom", alertId: report.alert?.id ?? null, symptoms } : next);
      return null;
    } catch (error) {
      if (!unreachable(error)) return errorText(error);
      setStep({ ...whenUnreachable(null, symptoms, fallback()), symptoms });
      return null;
    }
  }

  async function sendReading(body, symptoms) {
    setImportResult(null);  // a new reading: the file's summary no longer belongs under it
    pending.current = readingRequest(pending.current, body);
    let result;
    try {
      result = await addMeasurement(user.id, { ...body, id: pending.current.id });
    } catch (error) {
      if (!unreachable(error)) return errorText(error);
      // Keep the exact request: "Renvoyer" resends it with the same id, so it can never be stored twice.
      setStep({ ...whenUnreachable(body, symptoms, fallback()), body, symptoms });
      return null;
    }
    pending.current = null;  // stored: the next reading gets a new id
    const next = afterMeasurement(result, symptoms);
    if (next.kind === "send_symptoms") return sendSymptoms(result, symptoms);
    if (next.kind === "emergency" && symptoms.length > 0) {
      // Emergency first; the ticked symptoms are still recorded, without delaying the screen.
      addSymptomReport(user.id, { symptoms, measurement_id: result.measurement.id }).catch(() => {});
    }
    setStep(next.kind === "emergency"
      ? { ...next, trigger: symptoms.length ? "symptom" : "severe_reading", alertId: result.alert?.id ?? null, symptoms }
      : next);
    return null;
  }

  const restart = () => setStep({ kind: "form", recheck: false });

  return (
    <div className="mx-auto max-w-2xl space-y-5">
      <div className="flex items-center justify-between">
        <Link to="/patient" className="inline-flex min-h-11 items-center gap-1 text-sm font-semibold text-brand hover:underline"><Icon name="back" size={18} />Tableau de bord</Link>
      </div>

      {stepIndex(step) >= 0 && <Stepper current={stepIndex(step)} />}

      {step.kind === "form" && <ReadingForm key={step.recheck ? "recheck" : "first"} recheck={step.recheck} guidance={step.guidance} onSubmit={sendReading} />}

      {step.kind === "symptoms" && (
        <>
          {step.result && <ResultCard result={step.result} tz={user.timezone} />}
          <SymptomCheck onSubmit={(s) => sendSymptoms(step.result, s)}
            intro={step.result ? "Le serveur demande de vérifier vos symptômes avant la suite." : "Signalez ce que vous ressentez maintenant."} />
        </>
      )}

      {step.kind === "recheck_wait" && (
        <>
          <ResultCard result={step.result} report={step.report} tz={user.timezone} />
          <RecheckTimer seconds={step.seconds}
            onReady={() => setStep({ kind: "form", recheck: true, guidance: step.result?.evaluation?.next_step })} />
        </>
      )}

      {step.kind === "emergency" && (
        <EmergencyScreen reason={step.reason} nextStep={step.nextStep} initialConfig={config}
          trigger={step.trigger} alertId={step.alertId} symptoms={step.symptoms} />
      )}

      {step.kind === "unreachable" && step.emergency && (
        <EmergencyScreen notSaved initialConfig={config} trigger={step.symptoms?.length ? "symptom" : "severe_reading"} symptoms={step.symptoms ?? []} />
      )}

      {step.kind === "unreachable" && !step.emergency && (
        <Card className="animate-fade-up border-danger/30 bg-danger-soft p-5 text-danger sm:p-7" role="alert">
          <h2 className="text-xl font-bold">Serveur injoignable</h2>
          <p className="mt-2">La confirmation du serveur n'est pas arrivée : considérez la saisie comme non enregistrée. Renvoyez-la dans un instant ; si elle était déjà arrivée, elle ne sera pas enregistrée deux fois. Si vous vous sentez mal, utilisez le bouton Urgence.</p>
          <div className="mt-4 flex flex-wrap gap-3">
            {step.body && <ResendButton onResend={() => sendReading(step.body, step.symptoms)} />}
            <Button variant="secondary" onClick={restart}>Nouvelle saisie</Button>
          </div>
        </Card>
      )}

      {step.kind === "done" && (
        <>
          <ResultCard result={step.result} report={step.report} tz={user.timezone} />
          <div className="flex flex-wrap gap-3">
            <ButtonLink to="/patient">Retour au tableau de bord</ButtonLink>
            <Button variant="secondary" onClick={restart}>Nouvelle mesure</Button>
          </div>
        </>
      )}

      {/* The rest of the import (counts, rejected rows, alerts), after the symptom check so it never delays it. */}
      {importResult && ["symptoms", "recheck_wait", "done"].includes(step.kind) && (
        <Card className="p-5 sm:p-7">
          <h2 className="flex items-center gap-2 text-base font-semibold text-ink"><Icon name="upload" size={18} className="text-brand" />Fichier importé</h2>
          <div className="mt-3"><ReadingsResult result={importResult} timeZone={user.timezone} /></div>
        </Card>
      )}
    </div>
  );
}
