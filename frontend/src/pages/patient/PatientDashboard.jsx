import { Link } from "react-router";
import { useAuth } from "../../auth/AuthContext";
import { getProfile, getSummary, listAlerts, listMeasurements, listNotes } from "../../api/patient";
import AlertList from "../../components/alerts/AlertList";
import BloodPressureChart from "../../components/charts/BloodPressureChart";
import ReadingList from "../../components/readings/ReadingList";
import { OriginBadge, ValidationBadge } from "../../components/ui/Badge";
import { ButtonLink } from "../../components/ui/Button";
import { Card, CardBody, CardHeader, PageHeader } from "../../components/ui/Card";
import Icon from "../../components/ui/Icon";
import { EmptyState, ErrorState, Loading, Section } from "../../components/ui/States";
import WearablePanel from "../../components/wearables/WearablePanel";
import { formatAgo, formatDate, formatDateTime, round, TREND } from "../../lib/format";
import { useResource } from "../../lib/useResource";

function LatestReading({ readings, timeZone }) {
  if (readings.status !== "ok") {
    return readings.status === "loading" ? <Loading /> : <ErrorState what="vos mesures" error={readings.error} onRetry={readings.retry} />;
  }
  const latest = readings.data[0];
  if (!latest) {
    return (
      <EmptyState icon="pulse" title="Aucune mesure pour le moment"
        action={<ButtonLink to="/patient/mesure"><Icon name="plus" size={18} />Ajouter ma première mesure</ButtonLink>}>
        Saisissez la tension affichée par votre tensiomètre pour commencer votre suivi.
      </EmptyState>
    );
  }
  return (
    <div>
      <p className="tnum text-5xl font-bold tracking-tight text-ink">
        {latest.systolic}<span className="text-ink-subtle">/</span>{latest.diastolic}
        <span className="ml-2 text-base font-medium text-ink-muted">mmHg</span>
      </p>
      <p className="mt-2 text-sm text-ink-muted">
        {formatDateTime(latest.measured_at, timeZone)} · {formatAgo(latest.measured_at)}
        {latest.pulse ? ` · pouls ${latest.pulse} bpm` : ""}
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        <OriginBadge reading={latest} />
        <ValidationBadge status={latest.validation_status} />
      </div>
    </div>
  );
}

function Summary({ summary }) {
  return (
    <Section state={summary} what="le résumé">
      {(s) => (
        <dl className="grid grid-cols-2 gap-4">
          <div>
            <dt className="text-xs font-medium uppercase tracking-wide text-ink-subtle">Moyenne 7 jours</dt>
            <dd className="tnum mt-1 text-2xl font-semibold text-ink">
              {s.avg_systolic_7d === null ? "—" : `${round(s.avg_systolic_7d)}/${round(s.avg_diastolic_7d)}`}
            </dd>
          </div>
          <div>
            <dt className="text-xs font-medium uppercase tracking-wide text-ink-subtle">Tendance</dt>
            <dd className="mt-1 text-lg font-semibold text-ink first-letter:uppercase">{TREND[s.trend] ?? s.trend}</dd>
          </div>
          <div className="col-span-2 text-sm text-ink-muted">
            {s.count_7d} mesure(s) valides sur 7 jours
            {s.count_7d_simulated > 0 && <> dont <strong className="text-sim">{s.count_7d_simulated} simulée(s)</strong></>}
            {s.count_needs_review_7d > 0 && <> · {s.count_needs_review_7d} à vérifier</>}
            <br />Votre cible : {s.target.systolic}/{s.target.diastolic} mmHg{s.target.is_default ? " (cible générale)" : " (fixée par votre médecin)"}
          </div>
        </dl>
      )}
    </Section>
  );
}

function DoctorCard({ profile, notes, timeZone }) {
  const advice = notes.status === "ok" ? notes.data.filter((n) => n.advice || n.follow_up_at) : [];
  return (
    <Card>
      <CardHeader title="Votre suivi médical" />
      <CardBody className="space-y-4">
        <Section state={profile} what="votre profil">
          {(p) => p.regular_doctor_name ? (
            <div className="flex items-center gap-3">
              <span className="flex h-10 w-10 items-center justify-center rounded-full bg-brand-soft text-brand"><Icon name="user" /></span>
              <div>
                <p className="font-medium text-ink">{p.regular_doctor_name}</p>
                <p className="text-sm text-ink-muted">Médecin traitant{p.regular_clinic ? ` · ${p.regular_clinic}` : ""}</p>
              </div>
            </div>
          ) : <p className="text-sm text-ink-muted">Aucun médecin traitant renseigné.</p>}
        </Section>
        {notes.status === "error" && <ErrorState what="les conseils" error={notes.error} onRetry={notes.retry} />}
        {advice.length > 0 && (
          <ul className="space-y-3">
            {advice.slice(0, 2).map((n) => (
              <li key={n.id} className="rounded-xl bg-brand-soft/60 p-3 text-sm">
                {n.advice && <p className="text-ink">{n.advice}</p>}
                <p className="mt-1 text-xs text-ink-muted">
                  {n.doctor_name} · {formatDate(n.created_at, timeZone)}
                  {n.follow_up_at && ` · prochain suivi le ${formatDate(n.follow_up_at, timeZone)}`}
                </p>
              </li>
            ))}
          </ul>
        )}
      </CardBody>
    </Card>
  );
}

export default function PatientDashboard() {
  const { user } = useAuth();
  const id = user.id;
  const tz = user.timezone;
  const readings = useResource((signal) => listMeasurements(id, { limit: 60, signal }), `m:${id}`);
  const summary = useResource((signal) => getSummary(id, { signal }), `s:${id}`);
  const alerts = useResource((signal) => listAlerts(id, { status: "active", signal }), `a:${id}`);
  const profile = useResource((signal) => getProfile(id, { signal }), `p:${id}`);
  const notes = useResource((signal) => listNotes(id, { signal }), `n:${id}`);
  const firstName = (user.full_name ?? "").split(" ")[0];

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Espace patient" title={`Bonjour ${firstName}`}
        subtitle="Votre suivi repose sur les mesures et les symptômes que vous saisissez. Un bracelet est facultatif."
        action={
          <div className="flex flex-wrap gap-2">
            <ButtonLink to="/patient/mesure"><Icon name="plus" size={18} />Nouvelle mesure</ButtonLink>
            <ButtonLink to="/patient/mesure?mode=symptomes" variant="secondary">Signaler des symptômes</ButtonLink>
          </div>
        } />

      <div className="grid gap-4 lg:grid-cols-5">
        <Card className="lg:col-span-3">
          <CardHeader title="Dernière mesure" />
          <CardBody><LatestReading readings={readings} timeZone={tz} /></CardBody>
        </Card>
        <Card className="lg:col-span-2">
          <CardHeader title="Sur 7 jours" />
          <CardBody><Summary summary={summary} /></CardBody>
        </Card>
      </div>

      <Card aria-labelledby="alerts-title">
        <CardHeader id="alerts-title" title="Alertes en cours"
          action={<Link to="/patient/alertes" className="text-sm font-semibold text-brand">Toutes les alertes</Link>} />
        <CardBody>
          <Section state={alerts} what="les alertes">
            {(list) => list.length === 0
              ? <p className="text-sm text-ink-muted">Aucune alerte en cours.</p>
              : <AlertList alerts={list.slice(0, 3)} timeZone={tz} />}
          </Section>
        </CardBody>
      </Card>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader title="Évolution de la tension" subtitle="Vos dernières mesures" />
          <CardBody>
            <Section state={readings} what="le graphique">
              {(list) => <BloodPressureChart readings={list} timeZone={tz} target={summary.data?.target} />}
            </Section>
          </CardBody>
        </Card>
        <DoctorCard profile={profile} notes={notes} timeZone={tz} />
      </div>

      <Card>
        <CardHeader title="Mesures récentes"
          action={<Link to="/patient/historique" className="text-sm font-semibold text-brand">Tout l'historique</Link>} />
        <CardBody>
          <Section state={readings} what="vos mesures">
            {(list) => list.length === 0
              ? <p className="text-sm text-ink-muted">Aucune mesure enregistrée.</p>
              : <ReadingList readings={list} timeZone={tz} limit={6} />}
          </Section>
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Bracelet (facultatif)" subtitle="Données complémentaires, sans effet sur les alertes" />
        <CardBody><WearablePanel patientId={id} timeZone={tz} /></CardBody>
      </Card>
    </div>
  );
}
