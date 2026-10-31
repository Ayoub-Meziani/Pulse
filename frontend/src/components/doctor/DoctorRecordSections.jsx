import { useState } from "react";
import { reviewJournalEntry, updateCarePlan } from "../../api/doctor";
import { getCarePlan, getEmergencyReport, listEmergencyEvents, listJournal } from "../../api/patient";
import BloodPressureChart from "../charts/BloodPressureChart";
import JournalList from "../journal/JournalList";
import Badge, { LevelBadge } from "../ui/Badge";
import Button from "../ui/Button";
import { EmptyState, ErrorState, Loading, Section } from "../ui/States";
import { formatDate, formatDateTime, SYMPTOM_LABEL } from "../../lib/format";
import { useResource } from "../../lib/useResource";

const input = "mt-1.5 block w-full rounded-xl border border-line bg-surface px-3.5 py-2.5 text-sm text-ink outline-none focus:border-brand focus:ring-2 focus:ring-brand/20";

// ---------------------------------------------------------------- journal
export function DoctorJournal({ patientId, timeZone }) {
  const entries = useResource((signal) => listJournal(patientId, { signal }), `dj:${patientId}`);
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);

  async function review(entry) {
    setBusy(entry.id);
    setError(null);
    try { await reviewJournalEntry(entry.id); entries.reload(); }
    catch { setError("Impossible de marquer l'entrée comme lue. Réessayez."); }
    finally { setBusy(null); }
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-ink-muted">Entrées écrites par le patient (alimentation, activité, symptômes, questions). Elles ne déclenchent aucune alerte. Répondez par une note avec un conseil au patient.</p>
      {error && <p role="alert" className="text-sm text-danger">{error}</p>}
      <Section state={entries} what="le journal">
        {(list) => list.length === 0 ? <p className="text-sm text-ink-muted">Aucune entrée.</p> : (
          <JournalList entries={list} timeZone={timeZone}
            renderActions={(e) => e.doctor_review_status !== "reviewed" && (
              <Button variant="secondary" disabled={busy === e.id} onClick={() => review(e)}>Marquer comme lue</Button>
            )} />
        )}
      </Section>
    </div>
  );
}

// ---------------------------------------------------------------- emergency events (incident record)
const ACTION_LABEL = {
  screen_opened: "Écran d'urgence ouvert",
  emergency_call_tapped: "Bouton d'appel des secours touché (appel non confirmé)",
  contact_call_tapped: "Bouton d'appel du proche touché (appel non confirmé)",
  share_opened: "Partage de la position ouvert (envoi non confirmé)",
  share_failed: "Partage échoué",
  location_granted: "Position autorisée",
  location_denied: "Position refusée",
  location_timeout: "Position : délai dépassé",
  outcome_reported: "Suite déclarée par le patient",
  alarm_started: "Alarme sonore déclenchée sur le téléphone",
  alarm_stopped: "Alarme sonore arrêtée",
};
const TRIGGER_LABEL = { symptom: "Symptôme d'alerte", severe_reading: "Mesure très élevée", manual: "Bouton Urgence" };

function EventReport({ eventId, timeZone }) {
  const report = useResource((signal) => getEmergencyReport(eventId, { signal }), `er:${eventId}`);
  if (report.status === "loading") return <Loading />;
  if (report.status === "error") return <ErrorState what="le rapport" error={report.error} onRetry={report.retry} />;
  const { event, alert, readings, symptom_reports: symptoms } = report.data;
  return (
    <div className="space-y-4 border-t border-line pt-4">
      {alert && <p className="flex flex-wrap items-center gap-2 text-sm"><span className="text-ink-muted">Alerte liée :</span><LevelBadge level={alert.level} /> {alert.reason}</p>}
      <div>
        <p className="text-sm font-semibold text-ink">Chronologie</p>
        <ol className="mt-2 space-y-1.5 border-l-2 border-line pl-4 text-sm">
          {event.actions.map((a) => (
            <li key={a.client_action_id}>
              <span className="tnum text-ink-muted">{formatDateTime(a.at, timeZone)}</span> · <span className="text-ink">{ACTION_LABEL[a.action] ?? a.action}</span>
              {a.action === "outcome_reported" && event.reported_outcome ? ` : « ${event.reported_outcome} »` : ""}
            </li>
          ))}
          {event.actions.length === 0 && <li className="text-ink-muted">Aucune action enregistrée.</li>}
        </ol>
      </div>
      <p className="text-sm text-ink">
        Position partagée : {event.location
          ? <a className="font-semibold text-brand underline" target="_blank" rel="noreferrer" href={`https://maps.google.com/?q=${event.location.lat},${event.location.lon}`}>oui (voir la carte)</a>
          : "non"}
      </p>
      {symptoms.length > 0 && (
        <p className="flex flex-wrap items-center gap-1.5 text-sm"><span className="text-ink-muted">Symptômes signalés :</span>
          {symptoms.flatMap((s) => s.symptoms).map((s, i) => <Badge key={`${s}-${i}`}>{SYMPTOM_LABEL[s] ?? s}</Badge>)}</p>
      )}
      <div>
        <p className="text-sm font-semibold text-ink">Mesures de 24 h avant à 24 h après</p>
        <div className="mt-2"><BloodPressureChart readings={readings} timeZone={timeZone} /></div>
      </div>
    </div>
  );
}

export function DoctorEmergencies({ patientId, timeZone }) {
  const events = useResource((signal) => listEmergencyEvents(patientId, { signal }), `ev:${patientId}`);
  const [open, setOpen] = useState(null);
  return (
    <div className="space-y-3">
      <p className="text-sm text-ink-muted">Épisodes où le patient a ouvert l'écran d'urgence. Les actions sont ce que le patient a touché : PULSE ne sait pas si un appel a abouti.</p>
      <Section state={events} what="les épisodes d'urgence">
        {(list) => list.length === 0 ? <EmptyState icon="phone" title="Aucun épisode d'urgence" /> : (
          <ul className="space-y-3">
            {list.map((e) => (
              <li key={e.id} className="rounded-xl border border-line p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone="severe" icon="alert">{TRIGGER_LABEL[e.trigger_reason] ?? e.trigger_reason}</Badge>
                  <span className="text-sm text-ink">{formatDateTime(e.started_at, timeZone)}</span>
                  {e.reported_outcome && <span className="text-sm text-ink-muted">· Suite : « {e.reported_outcome} »</span>}
                  <Button variant="ghost" className="ml-auto" onClick={() => setOpen(open === e.id ? null : e.id)}>{open === e.id ? "Fermer" : "Voir le rapport"}</Button>
                </div>
                {open === e.id && <EventReport eventId={e.id} timeZone={timeZone} />}
              </li>
            ))}
          </ul>
        )}
      </Section>
    </div>
  );
}

// ---------------------------------------------------------------- care plan (doctor edits)
export function DoctorCarePlan({ patientId }) {
  const plan = useResource((signal) => getCarePlan(patientId, { signal }), `plan:${patientId}`);
  const [editing, setEditing] = useState(false);
  const [f, setF] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [saved, setSaved] = useState(false);

  function start(c) {
    setF({ target_systolic: String(c.target_systolic), target_diastolic: String(c.target_diastolic), review_date: c.review_date ?? "",
      monitoring_readings_per_day: c.monitoring_readings_per_day ? String(c.monitoring_readings_per_day) : "", clinician_guidance: c.clinician_guidance ?? "" });
    setEditing(true);
    setSaved(false);
  }

  async function save(event) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await updateCarePlan(patientId, {
        target_systolic: Number(f.target_systolic), target_diastolic: Number(f.target_diastolic),
        review_date: f.review_date || null,
        monitoring_readings_per_day: f.monitoring_readings_per_day ? Number(f.monitoring_readings_per_day) : null,
        clinician_guidance: f.clinician_guidance.trim(),
      });
      setEditing(false);
      setSaved(true);
      plan.reload();
    } catch (e) {
      setError(e.status === 422 ? "Valeurs refusées : cible systolique 90–200, diastolique 50–130, consigne obligatoire." : "Le plan n'a pas été enregistré. Réessayez.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Section state={plan} what="le plan de suivi">
      {(c) => editing ? (
        <form onSubmit={save} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block text-sm font-medium text-ink">Cible systolique (mmHg)<input className={input} inputMode="numeric" required value={f.target_systolic} onChange={(e) => setF({ ...f, target_systolic: e.target.value })} /></label>
            <label className="block text-sm font-medium text-ink">Cible diastolique (mmHg)<input className={input} inputMode="numeric" required value={f.target_diastolic} onChange={(e) => setF({ ...f, target_diastolic: e.target.value })} /></label>
            <label className="block text-sm font-medium text-ink">Mesures par jour<input className={input} inputMode="numeric" value={f.monitoring_readings_per_day} onChange={(e) => setF({ ...f, monitoring_readings_per_day: e.target.value })} /></label>
            <label className="block text-sm font-medium text-ink">Date de révision<input className={input} type="date" value={f.review_date} onChange={(e) => setF({ ...f, review_date: e.target.value })} /></label>
          </div>
          <label className="block text-sm font-medium text-ink">Consigne pour le patient<textarea className={input} rows={3} required maxLength={4000} value={f.clinician_guidance} onChange={(e) => setF({ ...f, clinician_guidance: e.target.value })} /></label>
          <p className="text-xs text-ink-muted">La nouvelle cible remplace l'ancienne et s'applique immédiatement aux règles « au-dessus de la cible » et « tendance ». Les seuils d'urgence (180/120) ne changent pas.</p>
          {error && <p role="alert" className="rounded-xl bg-danger-soft px-4 py-3 text-sm text-danger">{error}</p>}
          <div className="flex flex-wrap gap-3">
            <Button type="submit" disabled={busy}>{busy ? "Enregistrement…" : "Enregistrer le plan"}</Button>
            <Button variant="secondary" onClick={() => setEditing(false)}>Annuler</Button>
          </div>
        </form>
      ) : (
        <div className="space-y-3">
          {saved && <p role="status" className="rounded-xl bg-success-soft px-4 py-3 text-sm text-success">Plan de suivi enregistré.</p>}
          <dl className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-xl border border-line p-4"><dt className="text-xs font-medium uppercase tracking-wide text-ink-subtle">Cible</dt>
              <dd className="tnum mt-1 text-xl font-semibold text-ink">{c.target_systolic}/{c.target_diastolic} mmHg</dd>
              <dd className="text-xs text-ink-muted">{c.is_default ? "Cible générale (aucun plan actif)" : `Depuis le ${formatDate(c.effective_from)}`}</dd></div>
            <div className="rounded-xl border border-line p-4"><dt className="text-xs font-medium uppercase tracking-wide text-ink-subtle">Mesures par jour</dt>
              <dd className="tnum mt-1 text-xl font-semibold text-ink">{c.monitoring_readings_per_day ?? "—"}</dd>
              <dd className="text-xs text-ink-muted">{c.review_date ? `Révision le ${formatDate(c.review_date)}` : "Pas de date de révision"}</dd></div>
            {c.clinician_guidance && <div className="rounded-xl border border-line p-4 text-sm text-ink sm:col-span-2">{c.clinician_guidance}</div>}
          </dl>
          <Button variant="secondary" onClick={() => start(c)}>{c.is_default ? "Définir un plan de suivi" : "Modifier le plan"}</Button>
        </div>
      )}
    </Section>
  );
}
