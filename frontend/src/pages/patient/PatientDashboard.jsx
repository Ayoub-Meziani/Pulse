import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router";
import { useAuth } from "../../auth/AuthContext";
import { getProfile, getSummary, listAlerts, listMeasurements, listNotes } from "../../api/patient";
import AlertList from "../../components/alerts/AlertList";
import BloodPressureChart from "../../components/charts/BloodPressureChart";
import ReadingList from "../../components/readings/ReadingList";
import { OriginBadge, ValidationBadge } from "../../components/ui/Badge";
import { ButtonLink } from "../../components/ui/Button";
import { Card, CardBody, CardHeader } from "../../components/ui/Card";
import Icon from "../../components/ui/Icon";
import StatTile from "../../components/ui/StatTile";
import { ErrorState, Loading, Section } from "../../components/ui/States";
import RingImportPanel from "../../components/wearables/RingImportPanel";
import WearablePanel from "../../components/wearables/WearablePanel";
import { formatAgo, formatDate, formatDateTime, round, TREND } from "../../lib/format";
import { useResource } from "../../lib/useResource";

// Inside the night hero. No count-up and no gauge against the target: the value is shown as the server stored it.
function LatestReading({ readings, timeZone, target }) {
  if (readings.status !== "ok") {
    return readings.status === "loading" ? <Loading /> : <ErrorState what="vos mesures" error={readings.error} onRetry={readings.retry} />;
  }
  const latest = readings.data[0];
  if (!latest) {
    return (
      <div className="rounded-2xl border border-dashed border-white/20 p-5">
        <p className="font-semibold text-white">Aucune mesure pour le moment</p>
        <p className="mt-1 text-sm text-ink-muted">Saisissez la tension affichée par votre tensiomètre pour commencer votre suivi.</p>
        <ButtonLink to="/patient/mesure" variant="inverse" className="mt-4"><Icon name="plus" size={18} />Ajouter ma première mesure</ButtonLink>
      </div>
    );
  }
  return (
    <div>
      <p className="flex flex-wrap items-baseline gap-x-3 font-extrabold tracking-tight text-white">
        <span className="tnum animate-reveal text-6xl sm:text-7xl">
          {latest.systolic}<span className="text-ink-subtle">/</span>{latest.diastolic}
        </span>
        <span className="text-base font-medium text-ink-muted">mmHg</span>
      </p>
      <p className="mt-2 text-sm text-ink-muted">
        {formatDateTime(latest.measured_at, timeZone)} · {formatAgo(latest.measured_at)}
        {latest.pulse ? <> · pouls <span className="tnum">{latest.pulse}</span> bpm</> : ""}
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        <OriginBadge reading={latest} />
        <ValidationBadge status={latest.validation_status} />
        {target && (
          <span className="inline-flex items-center gap-1 rounded-full border border-white/15 bg-white/10 px-2.5 py-0.5 text-xs font-semibold text-white/90">
            Votre cible : <span className="tnum">{target.systolic}/{target.diastolic}</span> mmHg
          </span>
        )}
      </div>
    </div>
  );
}

const capitalize = (text) => (typeof text === "string" && text ? text[0].toUpperCase() + text.slice(1) : text);

function Summary({ summary }) {
  return (
    <Section state={summary} what="le résumé">
      {(s) => {
        const sim = s.count_7d_simulated > 0;
        return (
          <div className={`stagger grid grid-cols-2 gap-3 sm:gap-4 ${sim ? "lg:grid-cols-5" : "lg:grid-cols-4"}`}>
            <StatTile label="Moyenne 7 jours" icon="pulse" unit={s.avg_systolic_7d === null ? null : "mmHg"}
              value={s.avg_systolic_7d === null ? "—" : `${round(s.avg_systolic_7d)}/${round(s.avg_diastolic_7d)}`} />
            <StatTile label="Tendance" icon="history" value={capitalize(TREND[s.trend] ?? s.trend)} />
            <StatTile label="Mesures valides" icon="check" value={s.count_7d}
              hint={`mesure(s) valides sur 7 jours${s.count_needs_review_7d > 0 ? ` · ${s.count_needs_review_7d} à vérifier` : ""}`} />
            {sim && <StatTile tone="sim" label="Dont simulées" icon="flask" value={s.count_7d_simulated} hint="simulée(s), pas des mesures réelles" />}
            <StatTile label="Votre cible" icon="shield" unit="mmHg" value={`${s.target.systolic}/${s.target.diastolic}`}
              hint={s.target.is_default ? "Cible générale" : "Fixée par votre médecin"} />
          </div>
        );
      }}
    </Section>
  );
}

function DoctorCard({ profile, notes, timeZone }) {
  const advice = notes.status === "ok" ? notes.data.filter((n) => n.advice || n.follow_up_at) : [];
  return (
    <Card>
      <CardHeader title="Votre suivi médical" icon="user" />
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
              <li key={n.id} className="rounded-xl border-l-4 border-brand bg-brand-soft/60 p-3 text-sm">
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
  const location = useLocation();
  const [ringImports, setRingImports] = useState(0);  // a new key reloads the ring panel (devices and samples)

  // /patient#bracelet (from the navigation) scrolls to the ring card, again once the sections above have loaded
  // (they change the height of the page).
  const loaded = [readings, summary, alerts, profile, notes].filter((r) => r.status !== "loading").length;
  useEffect(() => {
    if (location.hash) document.getElementById(location.hash.slice(1))?.scrollIntoView();
  }, [location.hash, loaded]);

  const link = "inline-flex min-h-11 items-center gap-1 text-sm font-semibold text-brand hover:underline";
  return (
    <div className="space-y-6">
      <Card variant="night" className="relative isolate overflow-hidden p-6 sm:p-8">
        <span aria-hidden="true" className="pointer-events-none absolute -right-20 -top-28 -z-10 h-80 w-80 animate-float rounded-full bg-brand/40 blur-3xl" />
        <span aria-hidden="true" className="pointer-events-none absolute -bottom-32 left-1/3 -z-10 h-72 w-72 animate-float rounded-full bg-glow/20 blur-3xl [animation-delay:-9s]" />
        <div className="grid gap-8 lg:grid-cols-[1fr_auto] lg:items-end">
          <div className="min-w-0 animate-fade-up">
            <p className="inline-flex rounded-full bg-white/10 px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wider text-glow">Espace patient</p>
            <h1 className="mt-3 text-3xl font-extrabold tracking-tight text-white sm:text-4xl">Bonjour {firstName}</h1>
            <p className="mt-2 max-w-xl text-ink-muted">Votre suivi repose sur les mesures et les symptômes que vous saisissez. Un bracelet est facultatif.</p>
            <div className="mt-5 flex flex-wrap gap-2">
              <ButtonLink to="/patient/mesure"><Icon name="plus" size={18} />Nouvelle mesure</ButtonLink>
              <ButtonLink to="/patient/mesure?mode=symptomes" variant="outline-inverse">Signaler des symptômes</ButtonLink>
            </div>
          </div>
          <section aria-labelledby="latest-title" className="min-w-0 lg:min-w-80">
            <h2 id="latest-title" className="text-xs font-semibold uppercase tracking-wider text-ink-muted">Dernière mesure</h2>
            <div className="mt-2"><LatestReading readings={readings} timeZone={tz} target={summary.data?.target} /></div>
          </section>
        </div>
      </Card>

      <section aria-labelledby="week-title">
        <h2 id="week-title" className="mb-3 text-base font-semibold text-ink">Sur 7 jours</h2>
        <Summary summary={summary} />
      </section>

      <Card aria-labelledby="alerts-title">
        <CardHeader id="alerts-title" title="Alertes en cours" icon="bell"
          action={<Link to="/patient/alertes" className={link}>Toutes les alertes<Icon name="chevron" size={16} /></Link>} />
        <CardBody>
          <Section state={alerts} what="les alertes">
            {(list) => list.length === 0
              ? <p className="text-sm text-ink-muted">Aucune alerte en cours.</p>
              : <AlertList alerts={list.slice(0, 3)} timeZone={tz} />}
          </Section>
        </CardBody>
      </Card>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card variant="elevated" className="min-w-0 lg:col-span-2">
          <CardHeader title="Évolution de la tension" subtitle="Vos dernières mesures" icon="pulse" />
          <CardBody>
            <Section state={readings} what="le graphique">
              {(list) => <BloodPressureChart readings={list} timeZone={tz} target={summary.data?.target} />}
            </Section>
          </CardBody>
        </Card>
        <DoctorCard profile={profile} notes={notes} timeZone={tz} />
      </div>

      <Card>
        <CardHeader title="Mesures récentes" icon="history"
          action={<Link to="/patient/historique" className={link}>Tout l'historique<Icon name="chevron" size={16} /></Link>} />
        <CardBody>
          <Section state={readings} what="vos mesures">
            {(list) => list.length === 0
              ? <p className="text-sm text-ink-muted">Aucune mesure enregistrée.</p>
              : <ReadingList readings={list} timeZone={tz} limit={6} />}
          </Section>
        </CardBody>
      </Card>

      <Card id="bracelet">
        <CardHeader title="Bracelet (facultatif)" subtitle="Données complémentaires, sans effet sur les alertes" icon="watch" />
        <CardBody className="space-y-5">
          <WearablePanel key={ringImports} patientId={id} timeZone={tz} />
          <RingImportPanel patientId={id} onImported={() => setRingImports((n) => n + 1)} />
        </CardBody>
      </Card>
    </div>
  );
}
