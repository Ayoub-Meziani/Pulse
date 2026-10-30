import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { useAuth } from "../../auth/AuthContext";
import { ApiError } from "../../api/client";
import { addMeasurement, addSymptomReport, getEmergencyConfig } from "../../api/patient";
import AlertCard from "../../components/alerts/AlertCard";
import ProvenanceBadge from "../../components/ProvenanceBadge";
import { EVALUATION_LEVEL, formatDateTime, SOURCE, SYMPTOMS } from "../../lib/format";
import { afterMeasurement, afterSymptoms, whenUnreachable } from "../../lib/readingFlow";
import EmergencyScreen from "./EmergencyScreen";

// Reading -> server evaluation -> next screen. Every level, flag, delay and message is the
// server's (EvaluationOut); readingFlow.js only picks the screen.

function unreachable(error) {
  return error instanceof ApiError && (error.status === 0 || error.status >= 500);
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

const input = "mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900";

function SymptomBoxes({ selected, onChange }) {
  function toggle(code) {
    onChange(selected.includes(code) ? selected.filter((s) => s !== code) : [...selected, code]);
  }
  return (
    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
      {SYMPTOMS.map(([code, label]) => (
        <label key={code} className="flex items-center gap-2 text-sm text-slate-800">
          <input type="checkbox" checked={selected.includes(code)} onChange={() => toggle(code)} />
          {label}
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
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function submit(event) {
    event.preventDefault();
    const sys = toInt(systolic);
    const dia = toInt(diastolic);
    if (sys === null || dia === null || (pulse.trim() !== "" && toInt(pulse) === null)) {
      setError("Entrez des nombres entiers.");
      return;
    }
    setBusy(true);
    setError(null);
    // Plausibility and levels are the server's job; its message is shown as it is.
    const body = {
      systolic: sys,
      diastolic: dia,
      pulse: toInt(pulse),
      measured_at: new Date(measuredAt).toISOString(),
      body_position: position || null,
      rested_5_min: rested,
    };
    const err = await onSubmit(body, symptoms);
    setBusy(false);
    if (err) setError(err);
  }

  return (
    <form onSubmit={submit} className="space-y-5 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">{recheck ? "Mesure de contrôle" : "Nouvelle mesure"}</h1>
        {recheck && <p className="mt-1 text-slate-600">Restez assis au calme et reprenez votre tension maintenant.</p>}
      </div>
      <div className="grid grid-cols-2 gap-4">
        <label className="text-sm font-medium text-slate-700">
          Systolique (mmHg)
          <input className={input} inputMode="numeric" required value={systolic} onChange={(e) => setSystolic(e.target.value)} />
        </label>
        <label className="text-sm font-medium text-slate-700">
          Diastolique (mmHg)
          <input className={input} inputMode="numeric" required value={diastolic} onChange={(e) => setDiastolic(e.target.value)} />
        </label>
        <label className="text-sm font-medium text-slate-700">
          Pouls (facultatif)
          <input className={input} inputMode="numeric" value={pulse} onChange={(e) => setPulse(e.target.value)} />
        </label>
        <label className="text-sm font-medium text-slate-700">
          Date et heure
          <input className={input} type="datetime-local" required value={measuredAt} onChange={(e) => setMeasuredAt(e.target.value)} />
        </label>
        <label className="text-sm font-medium text-slate-700">
          Position
          <select className={input} value={position} onChange={(e) => setPosition(e.target.value)}>
            <option value="sitting">Assis</option>
            <option value="standing">Debout</option>
            <option value="lying">Allongé</option>
            <option value="">Non précisé</option>
          </select>
        </label>
        <label className="mt-6 flex items-center gap-2 text-sm text-slate-700">
          <input type="checkbox" checked={rested} onChange={(e) => setRested(e.target.checked)} />
          Repos de 5 minutes avant la mesure
        </label>
      </div>
      <fieldset>
        <legend className="text-sm font-medium text-slate-700">Symptômes en ce moment (facultatif)</legend>
        <div className="mt-2"><SymptomBoxes selected={symptoms} onChange={setSymptoms} /></div>
      </fieldset>
      {error && <p className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-800" role="alert">{error}</p>}
      <button type="submit" disabled={busy} className="rounded-lg bg-blue-700 px-5 py-2.5 font-semibold text-white disabled:opacity-60">
        {busy ? "Envoi…" : "Enregistrer la mesure"}
      </button>
    </form>
  );
}

function SymptomCheck({ onSubmit }) {
  const [symptoms, setSymptoms] = useState([]);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function send(list) {
    setBusy(true);
    setError(null);
    const err = await onSubmit(list);
    setBusy(false);
    if (err) setError(err);
  }

  return (
    <section className="space-y-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
      <h2 className="text-xl font-bold text-slate-900">Avez-vous un de ces symptômes en ce moment ?</h2>
      <SymptomBoxes selected={symptoms} onChange={setSymptoms} />
      {error && <p className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-800" role="alert">{error}</p>}
      <div className="flex flex-wrap gap-3">
        <button type="button" disabled={busy || symptoms.length === 0} onClick={() => send(symptoms)}
          className="rounded-lg bg-blue-700 px-5 py-2.5 font-semibold text-white disabled:opacity-60">
          Envoyer ces symptômes
        </button>
        <button type="button" disabled={busy} onClick={() => send([])}
          className="rounded-lg border border-slate-300 px-5 py-2.5 font-semibold text-slate-800 disabled:opacity-60">
          Aucun de ces symptômes
        </button>
      </div>
    </section>
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
    <section className="rounded-2xl border border-amber-200 bg-amber-50 p-6 sm:p-8">
      <h2 className="text-xl font-bold text-amber-900">Reposez-vous, puis reprenez votre tension</h2>
      <p className="mt-2 text-amber-900">
        {left > 0 ? `Nouvelle mesure dans ${left} s.` : "Vous pouvez reprendre votre tension."}
      </p>
      <button type="button" disabled={left > 0} onClick={onReady}
        className="mt-4 rounded-lg bg-amber-700 px-5 py-2.5 font-semibold text-white disabled:opacity-50">
        Reprendre ma tension
      </button>
    </section>
  );
}

function ResultCard({ result, report, tz }) {
  const ev = report && !result ? report.evaluation : result?.evaluation;
  const level = EVALUATION_LEVEL[ev?.level] ?? { title: ev?.level, variant: "info" };
  const m = result?.measurement;
  return (
    <div className="space-y-3">
      {m && (
        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <p className="text-3xl font-bold text-slate-900">{m.systolic} / {m.diastolic} <span className="text-base font-medium text-slate-500">mmHg</span></p>
          <p className="mt-2 text-sm text-slate-600">
            {formatDateTime(m.measured_at, tz)} · <ProvenanceBadge provenance={m.provenance} /> {SOURCE[m.source] ?? m.source}
            {m.pulse ? ` · pouls ${m.pulse}` : ""}
            {m.validation_status === "needs_review" && " · à vérifier"}
            {m.validation_status === "invalid" && " · mesure jugée non valide"}
          </p>
        </div>
      )}
      {ev && (
        <AlertCard title={level.title} message={`${ev.reason} ${ev.next_step}`.trim()} variant={level.variant} />
      )}
      {report && result && (
        <p className="text-sm text-slate-600">
          Symptômes enregistrés{report.report.symptoms.length === 0 ? " : aucun." : "."} {report.evaluation.next_step}
        </p>
      )}
      <p className="text-xs text-slate-500">Consignes du serveur (texte en anglais en attendant la traduction validée).</p>
    </div>
  );
}

export default function AddReading() {
  const { user } = useAuth();
  const [params] = useSearchParams();
  const symptomOnly = params.get("mode") === "symptomes";
  const [step, setStep] = useState(symptomOnly ? { kind: "symptoms", result: null } : { kind: "form", recheck: false });
  const [config, setConfig] = useState(null);

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
      if (!unreachable(error)) return error.message;
      setStep({ ...whenUnreachable(null, symptoms, config?.client_fallback) });
      return null;
    }
  }

  async function sendReading(body, symptoms) {
    let result;
    try {
      result = await addMeasurement(user.id, body);
    } catch (error) {
      if (!unreachable(error)) return error.message;
      setStep(whenUnreachable(body, symptoms, config?.client_fallback));
      return null;
    }
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
    <div className="mx-auto max-w-2xl space-y-6">
      <div className="flex items-center justify-between">
        <Link to="/patient" className="text-sm font-medium text-blue-700">← Tableau de bord</Link>
        <Link to="/patient/urgence" className="rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold text-white">Urgence</Link>
      </div>

      {step.kind === "form" && <ReadingForm key={step.recheck ? "recheck" : "first"} recheck={step.recheck} onSubmit={sendReading} />}

      {step.kind === "symptoms" && (
        <>
          {step.result && <ResultCard result={step.result} tz={user.timezone} />}
          <SymptomCheck onSubmit={(s) => sendSymptoms(step.result, s)} />
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
        <section className="rounded-2xl border border-red-200 bg-red-50 p-6 text-red-900" role="alert">
          <h2 className="text-xl font-bold">Serveur injoignable</h2>
          <p className="mt-2">Votre saisie n'a pas été enregistrée. Réessayez dans un instant. Si vous vous sentez mal, utilisez le bouton Urgence.</p>
          <button type="button" onClick={restart} className="mt-4 rounded-lg bg-red-700 px-5 py-2.5 font-semibold text-white">Réessayer</button>
        </section>
      )}

      {step.kind === "done" && (
        <>
          <ResultCard result={step.result} report={step.report} tz={user.timezone} />
          <div className="flex flex-wrap gap-3">
            <Link to="/patient" className="rounded-lg bg-blue-700 px-5 py-2.5 font-semibold text-white">Retour au tableau de bord</Link>
            <button type="button" onClick={restart} className="rounded-lg border border-slate-300 px-5 py-2.5 font-semibold text-slate-800">Nouvelle mesure</button>
          </div>
        </>
      )}
    </div>
  );
}
