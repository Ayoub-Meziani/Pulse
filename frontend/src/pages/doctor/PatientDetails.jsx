import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { useAuth } from "../../auth/AuthContext";
import { addNote, getLatestPrediction } from "../../api/doctor";
import {
  getProfile, getSummary, listAlerts, listMeasurements, listNotes, listSymptomReports, transitionAlert,
} from "../../api/patient";
import AlertList from "../../components/alerts/AlertList";
import BloodPressureChart from "../../components/charts/BloodPressureChart";
import ReadingList from "../../components/readings/ReadingList";
import SymptomList from "../../components/symptoms/SymptomList";
import Badge from "../../components/ui/Badge";
import Button from "../../components/ui/Button";
import { Card, CardBody, CardHeader } from "../../components/ui/Card";
import Icon from "../../components/ui/Icon";
import StatTile from "../../components/ui/StatTile";
import Tabs from "../../components/ui/Tabs";
import { EmptyState, ErrorState, Loading, Section } from "../../components/ui/States";
import WearablePanel from "../../components/wearables/WearablePanel";
import { DoctorCarePlan, DoctorEmergencies, DoctorJournal } from "../../components/doctor/DoctorRecordSections";
import { PersonalBands, RingSignals, WeeklyReports } from "../../components/doctor/RingReview";
import { formatDate, formatDateTime, initials, round, TREND } from "../../lib/format";
import { watchAlerts } from "../../lib/alertEvents";
import { useResource } from "../../lib/useResource";

const TABS = [
  ["apercu", "Vue d'ensemble"], ["mesures", "Mesures"], ["symptomes", "Symptômes"], ["alertes", "Alertes"],
  ["urgences", "Urgences"], ["journal", "Journal"], ["bracelet", "Bracelet"], ["signaux", "Signaux bracelet"],
  ["rapport", "Rapport hebdo"], ["plages", "Plages"], ["estimation", "Estimation"],
  ["notes", "Notes"], ["plan", "Plan de suivi"],
];

function SummaryStats({ summary }) {
  return (
    <Section state={summary} what="le résumé">
      {(s) => (
        <div className="stagger grid grid-cols-1 gap-3 min-[420px]:grid-cols-2 lg:grid-cols-4">
          <StatTile label="Moyenne 7 j" icon="pulse"
            value={s.avg_systolic_7d === null ? "—" : `${round(s.avg_systolic_7d)}/${round(s.avg_diastolic_7d)}`}
            unit={s.avg_systolic_7d === null ? undefined : "mmHg"}
            hint={`${s.count_7d} valides : ${s.count_7d_measured} mesurées, ${s.count_7d_simulated} simulées`} />
          <StatTile label="Moyenne 30 j" icon="history"
            value={s.avg_systolic_30d === null ? "—" : `${round(s.avg_systolic_30d)}/${round(s.avg_diastolic_30d)}`}
            unit={s.avg_systolic_30d === null ? undefined : "mmHg"} />
          <StatTile label="Au-dessus de la cible (7 j)" icon="clipboard"
            value={s.pct_above_target_7d === null ? "—" : `${round(s.pct_above_target_7d)} %`}
            hint={`Cible ${s.target.systolic}/${s.target.diastolic}${s.target.is_default ? " (générale)" : ""}`} />
          <StatTile label="Tendance" icon="refresh" value={TREND[s.trend] ?? s.trend}
            hint={s.count_needs_review_7d ? `${s.count_needs_review_7d} mesure(s) à vérifier` : "Statistiques descriptives"} />
        </div>
      )}
    </Section>
  );
}

function DoctorAlertActions({ alert, onDone }) {
  const [closing, setClosing] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const needsNote = alert.level === "severe" || alert.level === "emergency";

  async function move(to) {
    setBusy(true);
    setError(null);
    try {
      await transitionAlert(alert.id, to, to === "resolved" ? note.trim() || undefined : undefined);
      onDone();
    } catch (e) {
      setError(e.status === 422 ? "Ajoutez une note de suivi pour clôturer cette alerte." : e.status === 409 ? "Le statut a déjà changé." : "Action impossible. Réessayez.");
    } finally {
      setBusy(false);
    }
  }

  if (alert.status === "resolved") return null;
  return (
    <div className="w-full space-y-2">
      <div className="flex flex-wrap gap-2">
        {(alert.status === "open" || alert.status === "acknowledged") && (
          <Button variant="secondary" disabled={busy} onClick={() => move("reviewed")}><Icon name="check" size={16} />Marquer comme examinée</Button>
        )}
        {alert.status === "reviewed" && !closing && <Button variant="secondary" onClick={() => setClosing(true)}>Clôturer…</Button>}
      </div>
      {closing && (
        <div className="space-y-2">
          <label className="block text-sm font-medium text-ink">Note de suivi{needsNote ? " (obligatoire)" : " (facultative)"}
            <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} maxLength={2000}
              className="field mt-1.5 text-sm" />
          </label>
          <div className="flex flex-wrap gap-2">
            <Button disabled={busy || (needsNote && !note.trim())} onClick={() => move("resolved")}>Clôturer l'alerte</Button>
            <Button variant="ghost" onClick={() => setClosing(false)}>Annuler</Button>
          </div>
        </div>
      )}
      {error && <p role="alert" className="text-sm text-danger">{error}</p>}
    </div>
  );
}

function AlertsBlock({ patientId, status, timeZone }) {
  const alerts = useResource((signal) => listAlerts(patientId, { status, signal }), `da:${patientId}:${status}`);
  const { reload } = alerts;
  // Same rhythm as the doctor's alert flag, so an alert flagged there can be reached here at once.
  useEffect(() => watchAlerts(reload), [reload]);
  return (
    <Section state={alerts} what="les alertes">
      {(list) => list.length === 0
        ? <p className="text-sm text-ink-muted">{status === "active" ? "Aucune alerte en cours." : "Aucune alerte."}</p>
        : <AlertList alerts={list} timeZone={timeZone} renderActions={(a) => <DoctorAlertActions alert={a} onDone={alerts.reload} />} />}
    </Section>
  );
}

function PredictionCard({ patientId, timeZone }) {
  const p = useResource((signal) => getLatestPrediction(patientId, { signal }), `pred:${patientId}`);
  return (
    <div className="space-y-4">
      <p className="flex gap-2 rounded-xl border border-dashed border-ml/50 bg-ml-soft px-4 py-3 text-sm text-ml">
        <Icon name="sparkles" size={18} />
        <span>Estimation expérimentale d'un modèle entraîné sur des données synthétiques. Ce n'est ni une mesure ni un
        diagnostic ; elle n'est pas validée cliniquement et n'intervient dans aucune alerte ni consigne d'urgence.</span>
      </p>
      <Section state={p} what="l'estimation">
        {(e) => {
          if (e.status === "model_unavailable") {
            return <EmptyState icon="sparkles" title="Aucune estimation disponible">Le modèle approuvé n'a pas produit d'estimation à jour pour ce patient.</EmptyState>;
          }
          if (e.status === "insufficient_history") {
            return <EmptyState icon="sparkles" title="Historique insuffisant">Pas assez de mesures récentes pour une estimation (modèle {e.model_version}).</EmptyState>;
          }
          return (
            <div className="rounded-2xl border border-dashed border-ml/50 bg-surface p-5">
              <Badge tone="ml" icon="sparkles">Estimation, pas une mesure</Badge>
              <p className="mt-3 text-sm text-ink-muted">Moyenne du matin estimée pour le {formatDate(e.target_date)}</p>
              <p className="tnum mt-1 text-4xl font-extrabold tracking-tight text-ml">{round(e.predicted_systolic)}/{round(e.predicted_diastolic)} <span className="text-base font-medium">mmHg</span></p>
              {e.interval && (
                <p className="tnum mt-1 text-sm text-ink-muted">
                  Intervalle : {round(e.interval.systolic[0])}–{round(e.interval.systolic[1])} / {round(e.interval.diastolic[0])}–{round(e.interval.diastolic[1])} mmHg
                </p>
              )}
              <p className="mt-3 text-xs text-ink-subtle">Modèle {e.model_version} · {e.trained_on} · calculée {formatDateTime(e.generated_at, timeZone)}</p>
            </div>
          );
        }}
      </Section>
    </div>
  );
}

function Notes({ patientId, timeZone }) {
  const notes = useResource((signal) => listNotes(patientId, { signal }), `notes:${patientId}`);
  const [note, setNote] = useState("");
  const [advice, setAdvice] = useState("");
  const [followUp, setFollowUp] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function save(event) {
    event.preventDefault();
    if (!note.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      await addNote(patientId, { note: note.trim(), advice: advice.trim() || null,
        follow_up_at: followUp ? new Date(`${followUp}T09:00`).toISOString() : null });
      setNote(""); setAdvice(""); setFollowUp("");
      notes.reload();
    } catch {
      setError("La note n'a pas été enregistrée. Réessayez.");
    } finally {
      setBusy(false);
    }
  }

  const input = "field mt-1.5 text-sm";
  return (
    <div className="space-y-5">
      <form onSubmit={save} className="space-y-3 rounded-2xl border border-line bg-surface-muted/50 p-4 sm:p-5">
        <label className="block text-sm font-medium text-ink">Note privée <span className="font-normal text-ink-muted">(visible uniquement par les médecins assignés)</span>
          <textarea required value={note} onChange={(e) => setNote(e.target.value)} rows={3} maxLength={8000} className={input} />
        </label>
        <label className="block text-sm font-medium text-ink">Conseil au patient <span className="font-normal text-ink-muted">(facultatif, visible par le patient)</span>
          <textarea value={advice} onChange={(e) => setAdvice(e.target.value)} rows={2} maxLength={4000} className={input} />
        </label>
        <label className="block text-sm font-medium text-ink sm:w-60">Date de suivi <span className="font-normal text-ink-muted">(facultative)</span>
          <input type="date" value={followUp} onChange={(e) => setFollowUp(e.target.value)} className={input} />
        </label>
        {error && <p role="alert" className="text-sm text-danger">{error}</p>}
        <Button type="submit" disabled={busy || !note.trim()}>{busy ? "Enregistrement…" : "Enregistrer la note"}</Button>
      </form>
      <Section state={notes} what="les notes">
        {(list) => list.length === 0 ? <p className="text-sm text-ink-muted">Aucune note.</p> : (
          <ul className="stagger space-y-3">
            {list.map((n) => (
              <li key={n.id} className="rounded-2xl border border-line bg-surface p-4 text-sm shadow-card">
                <p className="text-xs text-ink-muted">{n.doctor_name} · {formatDateTime(n.created_at, timeZone)}</p>
                {n.note && <p className="mt-2 whitespace-pre-line text-ink">{n.note}</p>}
                {n.advice && <p className="mt-2 rounded-lg bg-brand-soft/60 px-3 py-2 text-ink"><span className="font-medium">Conseil au patient :</span> {n.advice}</p>}
                {n.follow_up_at && <p className="mt-2 text-ink-muted">Suivi prévu le {formatDate(n.follow_up_at, timeZone)}</p>}
              </li>
            ))}
          </ul>
        )}
      </Section>
    </div>
  );
}

export default function PatientDetails() {
  const { patientId } = useParams();
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const tab = TABS.some(([k]) => k === params.get("onglet")) ? params.get("onglet") : "apercu";
  const tz = user.timezone;
  const profile = useResource((signal) => getProfile(patientId, { signal }), `prof:${patientId}`);
  const summary = useResource((signal) => getSummary(patientId, { signal }), `sum:${patientId}`);
  const readings = useResource((signal) => listMeasurements(patientId, { limit: 200, includeInvalid: tab === "mesures", signal }),
    `read:${patientId}:${tab === "mesures"}`);
  const symptoms = useResource((signal) => listSymptomReports(patientId, { limit: 100, signal }), `sym:${patientId}`);

  if (profile.status === "loading") return <Loading />;
  if (profile.status === "error") {
    return (
      <div className="space-y-4">
        <Link to="/doctor" className="inline-flex items-center gap-1 text-sm font-semibold text-brand"><Icon name="back" size={18} />Mes patients</Link>
        <ErrorState what="ce dossier" error={profile.error} onRetry={profile.retry} />
      </div>
    );
  }
  const p = profile.data;

  return (
    <div className="space-y-5">
      <Link to="/doctor" className="inline-flex items-center gap-1 text-sm font-semibold text-brand"><Icon name="back" size={18} />Mes patients</Link>
      <Card variant="elevated" className="animate-fade-up overflow-hidden">
        <div className="flex flex-wrap items-center gap-4 p-5 sm:p-6">
          <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-linear-to-br from-brand to-brand-hover text-lg font-bold text-white shadow-glow-brand" aria-hidden="true">{initials(p.full_name)}</span>
          <div className="min-w-0 flex-1">
            <p className="text-xs font-semibold uppercase tracking-wider text-brand">Dossier patient</p>
            <h1 className="mt-0.5 break-words text-2xl font-extrabold tracking-tight text-ink sm:text-3xl">{p.full_name}</h1>
            <p className="break-all text-sm text-ink-muted">{p.birth_year ? `Né(e) en ${p.birth_year} · ` : ""}{p.email}</p>
          </div>
          {p.allergies && <Badge tone="warning" icon="alert" className="whitespace-normal!">Allergies : {p.allergies}</Badge>}
        </div>
        {p.relevant_conditions.length > 0 && (
          <ul className="flex flex-wrap gap-2 border-t border-line/70 px-5 py-3 sm:px-6" aria-label="Antécédents">
            {p.relevant_conditions.map((c) => <li key={c}><Badge tone="brand">{c}</Badge></li>)}
          </ul>
        )}
      </Card>

      <Tabs items={TABS} value={tab} label="Sections du dossier" idPrefix="dossier"
        onChange={(key) => setParams(key === "apercu" ? {} : { onglet: key }, { replace: true })} />

      <div role="tabpanel" id="dossier-panel" aria-labelledby={`dossier-tab-${tab}`} key={tab} className="animate-fade-up">
      {tab === "apercu" && (
        <div className="space-y-4">
          <SummaryStats summary={summary} />
          <Card>
            <CardHeader icon="pulse" title="Évolution de la tension" />
            <CardBody>
              <Section state={readings} what="les mesures">
                {(list) => <BloodPressureChart readings={list} timeZone={tz} target={summary.data?.target} />}
              </Section>
            </CardBody>
          </Card>
          <Card>
            <CardHeader icon="bell" title="Alertes en cours" />
            <CardBody><AlertsBlock patientId={patientId} status="active" timeZone={tz} /></CardBody>
          </Card>
        </div>
      )}
      {tab === "mesures" && (
        <Card>
          <CardHeader icon="history" title="Mesures" subtitle="Toutes les mesures, y compris celles jugées invalides par le serveur." />
          <CardBody>
            <Section state={readings} what="les mesures">
              {(list) => list.length === 0 ? <p className="text-sm text-ink-muted">Aucune mesure.</p> : <ReadingList readings={list} timeZone={tz} />}
            </Section>
          </CardBody>
        </Card>
      )}
      {tab === "symptomes" && (
        <Card>
          <CardHeader icon="note" title="Symptômes signalés" subtitle="Le lien vers la mesure correspondante n'est pas encore enregistré." />
          <CardBody><Section state={symptoms} what="les symptômes">{(list) => <SymptomList reports={list} timeZone={tz} />}</Section></CardBody>
        </Card>
      )}
      {tab === "alertes" && (
        <Card>
          <CardHeader icon="bell" title="Historique des alertes" />
          <CardBody><AlertsBlock patientId={patientId} status="all" timeZone={tz} /></CardBody>
        </Card>
      )}
      {tab === "bracelet" && (
        <Card>
          <CardHeader icon="watch" title="Bracelet et appareils" subtitle="Données complémentaires, sans effet sur les alertes." />
          <CardBody><WearablePanel patientId={patientId} timeZone={tz} emptyText="Ce patient n'utilise pas de bracelet. Son suivi repose sur ses mesures saisies." /></CardBody>
        </Card>
      )}
      {tab === "signaux" && (
        <Card>
          <CardHeader icon="watch" title="Signaux du bracelet" subtitle="Actualisés toutes les 10 secondes tant que cet onglet est ouvert." />
          <CardBody><RingSignals patientId={patientId} timeZone={tz} /></CardBody>
        </Card>
      )}
      {tab === "rapport" && (
        <Card>
          <CardHeader icon="clipboard" title="Rapport hebdomadaire" />
          <CardBody><WeeklyReports patientId={patientId} timeZone={tz} /></CardBody>
        </Card>
      )}
      {tab === "plages" && (
        <Card>
          <CardHeader icon="watch" title="Plages personnelles du bracelet" />
          <CardBody><PersonalBands patientId={patientId} /></CardBody>
        </Card>
      )}
      {tab === "estimation" && (
        <Card>
          <CardHeader icon="sparkles" title="Estimation expérimentale" />
          <CardBody><PredictionCard patientId={patientId} timeZone={tz} /></CardBody>
        </Card>
      )}
      {tab === "notes" && (
        <Card>
          <CardHeader icon="note" title="Notes de suivi" />
          <CardBody><Notes patientId={patientId} timeZone={tz} /></CardBody>
        </Card>
      )}
      {tab === "plan" && (
        <Card>
          <CardHeader icon="clipboard" title="Plan de suivi" />
          <CardBody><DoctorCarePlan patientId={patientId} /></CardBody>
        </Card>
      )}
      {tab === "urgences" && (
        <Card>
          <CardHeader icon="phone" title="Épisodes d'urgence" />
          <CardBody><DoctorEmergencies patientId={patientId} timeZone={tz} /></CardBody>
        </Card>
      )}
      {tab === "journal" && (
        <Card>
          <CardHeader icon="note" title="Journal du patient" />
          <CardBody><DoctorJournal patientId={patientId} timeZone={tz} /></CardBody>
        </Card>
      )}
      </div>
    </div>
  );
}
