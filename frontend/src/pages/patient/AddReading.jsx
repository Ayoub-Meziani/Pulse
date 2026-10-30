import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { useAuth } from "../../auth/AuthContext";
import { ApiError } from "../../api/client";
import { addMeasurement, addSymptomReport, getEmergencyConfig } from "../../api/patient";
import AlertCard from "../../components/alerts/AlertCard";
import { OriginBadge, ValidationBadge } from "../../components/ui/Badge";
import Button, { ButtonLink } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import Icon from "../../components/ui/Icon";
import { EVALUATION_LEVEL, formatDateTime, SYMPTOMS } from "../../lib/format";
import { afterMeasurement, afterSymptoms, readingRequest, whenUnreachable } from "../../lib/readingFlow";
import EmergencyScreen from "./EmergencyScreen";

// Reading -> server evaluation -> next screen. Every level, flag, delay and message is the
// server's (EvaluationOut); readingFlow.js only picks the screen. Nothing is shown as saved before
// the server has answered.

function unreachable(error) {
  return error instanceof ApiError && (error.status === 0 || error.status >= 500);
}

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

const field = "mt-1.5 block w-full rounded-xl border border-line bg-surface px-3.5 py-2.5 text-ink outline-none focus:border-brand focus:ring-2 focus:ring-brand/20";
const label = "text-sm font-medium text-ink";

function SymptomBoxes({ selected, onChange }) {
  function toggle(code) {
    onChange(selected.includes(code) ? selected.filter((s) => s !== code) : [...selected, code]);
  }
  return (
    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
      {SYMPTOMS.map(([code, text]) => (
        <label key={code} className={`flex min-h-11 cursor-pointer items-center gap-3 rounded-xl border px-3 py-2 text-sm transition-colors ${
          selected.includes(code) ? "border-brand bg-brand-soft text-ink" : "border-line bg-surface text-ink hover:bg-surface-muted"
        }`}>
          <input type="checkbox" className="h-4 w-4 accent-[#0b5cad]" checked={selected.includes(code)} onChange={() => toggle(code)} />
          {text}
        </label>
      ))}
    </div>
  );
}

function ReadingForm({ recheck, onSubmit }) {
  const [systolic, setSystolic] = useState("");
  const [diastolic, setDiastolic] = useState("");
  const [pulse, setPulse] = useState("");
  const [measuredAt, setMeasuredAt] = useState(nowLocalInput);
  const [position, setPosition] = useState("sitting");
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
    <Card as="form" onSubmit={submit} className="p-5 sm:p-7" noValidate>
      <h1 className="text-xl font-bold text-ink sm:text-2xl">{recheck ? "Mesure de contrôle" : "Nouvelle mesure"}</h1>
      <p className="mt-1 text-sm text-ink-muted">
        {recheck ? "Restez assis au calme et reprenez votre tension maintenant." : "Recopiez les valeurs affichées par votre tensiomètre."}
      </p>

      <div className="mt-6 grid grid-cols-2 gap-4">
        <label className={label}>Systolique
          <span className="block text-xs font-normal text-ink-muted">chiffre du haut</span>
          <input className={`${field} tnum text-xl font-semibold`} inputMode="numeric" autoComplete="off" required
            value={systolic} onChange={(e) => setSystolic(e.target.value)} placeholder="128" aria-describedby="unit-mmhg" />
        </label>
        <label className={label}>Diastolique
          <span className="block text-xs font-normal text-ink-muted">chiffre du bas</span>
          <input className={`${field} tnum text-xl font-semibold`} inputMode="numeric" autoComplete="off" required
            value={diastolic} onChange={(e) => setDiastolic(e.target.value)} placeholder="82" aria-describedby="unit-mmhg" />
        </label>
        <p id="unit-mmhg" className="col-span-2 -mt-2 text-xs text-ink-subtle">Valeurs en mmHg.</p>
        <label className={label}>Pouls <span className="font-normal text-ink-muted">(facultatif, bpm)</span>
          <input className={`${field} tnum`} inputMode="numeric" autoComplete="off" value={pulse} onChange={(e) => setPulse(e.target.value)} placeholder="72" />
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
        <label className="mt-7 flex min-h-11 items-center gap-3 text-sm text-ink">
          <input type="checkbox" className="h-4 w-4 accent-[#0b5cad]" checked={rested} onChange={(e) => setRested(e.target.checked)} />
          Repos de 5 minutes avant la mesure
        </label>
      </div>

      <div className="mt-6 rounded-xl border border-line">
        <button type="button" onClick={() => setShowSymptoms((v) => !v)} aria-expanded={showSymptoms}
          className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left text-sm font-medium text-ink">
          <span>Symptômes en ce moment <span className="font-normal text-ink-muted">(facultatif){symptoms.length ? ` · ${symptoms.length} sélectionné(s)` : ""}</span></span>
          <Icon name="chevron" size={18} className={showSymptoms ? "rotate-90" : ""} />
        </button>
        {showSymptoms && <div className="border-t border-line p-4"><SymptomBoxes selected={symptoms} onChange={setSymptoms} /></div>}
      </div>

      {error && <p className="mt-5 flex gap-2 rounded-xl bg-danger-soft px-4 py-3 text-sm text-danger" role="alert"><Icon name="alert" size={18} />{error}</p>}
      <div className="mt-6 flex flex-wrap gap-3">
        <Button type="submit" disabled={busy} className="flex-1 sm:flex-none">{busy ? "Envoi en cours…" : "Enregistrer la mesure"}</Button>
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
    <Card className="p-5 sm:p-7">
      <h2 className="text-xl font-bold text-ink">Avez-vous un de ces symptômes en ce moment ?</h2>
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
    <Card className="border-level-notice/30 bg-level-notice-soft p-5 sm:p-7">
      <h2 className="text-xl font-bold text-level-notice">Reposez-vous, puis reprenez votre tension</h2>
      <p className="tnum mt-2 text-level-notice" aria-live="polite">
        {left > 0 ? `Nouvelle mesure possible dans ${left} s.` : "Vous pouvez reprendre votre tension."}
      </p>
      <p className="mt-1 text-sm text-level-notice">Si vous vous sentez mal, utilisez le bouton Urgence.</p>
      <Button disabled={left > 0} onClick={onReady} className="mt-4">Reprendre ma tension</Button>
    </Card>
  );
}

function ResultCard({ result, report, tz }) {
  const ev = report && !result ? report.evaluation : result?.evaluation;
  const level = EVALUATION_LEVEL[ev?.level] ?? { title: ev?.level, variant: "info" };
  const m = result?.measurement;
  return (
    <div className="space-y-3">
      {m && (
        <Card className="p-5">
          <p className="flex items-center gap-2 text-sm font-medium text-success"><Icon name="check" size={18} />Mesure enregistrée par le serveur</p>
          <p className="tnum mt-2 text-3xl font-bold text-ink">{m.systolic}/{m.diastolic} <span className="text-base font-medium text-ink-muted">mmHg</span></p>
          <p className="mt-1 text-sm text-ink-muted">{formatDateTime(m.measured_at, tz)}{m.pulse ? ` · pouls ${m.pulse} bpm` : ""}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <OriginBadge reading={m} />
            <ValidationBadge status={m.validation_status} />
          </div>
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
  const [step, setStep] = useState(symptomOnly ? { kind: "symptoms", result: null } : { kind: "form", recheck: false });
  const [config, setConfig] = useState(null);
  const pending = useRef(null);  // last request: same values -> same id (repeat-safe)

  // Loaded up front so the server's fallback values are at hand if the API drops mid-flow.
  useEffect(() => {
    const controller = new AbortController();
    getEmergencyConfig({ signal: controller.signal }).then(setConfig).catch(() => {});
    return () => controller.abort();
  }, []);

  async function sendSymptoms(result, symptoms) {
    try {
      const report = await addSymptomReport(user.id, { symptoms, measurement_id: result?.measurement.id ?? null });
      setStep(afterSymptoms(result, report));
      return null;
    } catch (error) {
      if (!unreachable(error)) return errorText(error);
      setStep(whenUnreachable(null, symptoms, config?.client_fallback));
      return null;
    }
  }

  async function sendReading(body, symptoms) {
    pending.current = readingRequest(pending.current, body);
    let result;
    try {
      result = await addMeasurement(user.id, { ...body, id: pending.current.id });
    } catch (error) {
      if (!unreachable(error)) return errorText(error);
      // Keep the exact request: "Renvoyer" resends it with the same id, so it can never be stored twice.
      setStep({ ...whenUnreachable(body, symptoms, config?.client_fallback), body, symptoms });
      return null;
    }
    pending.current = null;  // stored: the next reading gets a new id
    const next = afterMeasurement(result, symptoms);
    if (next.kind === "send_symptoms") return sendSymptoms(result, symptoms);
    if (next.kind === "emergency" && symptoms.length > 0) {
      // Emergency first; the ticked symptoms are still recorded, without delaying the screen.
      addSymptomReport(user.id, { symptoms, measurement_id: result.measurement.id }).catch(() => {});
    }
    setStep(next);
    return null;
  }

  const restart = () => setStep({ kind: "form", recheck: false });

  return (
    <div className="mx-auto max-w-2xl space-y-5">
      <div className="flex items-center justify-between">
        <Link to="/patient" className="inline-flex items-center gap-1 text-sm font-semibold text-brand"><Icon name="back" size={18} />Tableau de bord</Link>
      </div>

      {step.kind === "form" && <ReadingForm key={step.recheck ? "recheck" : "first"} recheck={step.recheck} onSubmit={sendReading} />}

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
          <RecheckTimer seconds={step.seconds} onReady={() => setStep({ kind: "form", recheck: true })} />
        </>
      )}

      {step.kind === "emergency" && <EmergencyScreen reason={step.reason} nextStep={step.nextStep} initialConfig={config} />}

      {step.kind === "unreachable" && step.emergency && <EmergencyScreen notSaved initialConfig={config} />}

      {step.kind === "unreachable" && !step.emergency && (
        <Card className="border-danger/30 bg-danger-soft p-5 text-danger sm:p-7" role="alert">
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
    </div>
  );
}
