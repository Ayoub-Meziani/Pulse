import { useEffect, useState } from "react";
import { Link } from "react-router";
import { useAuth } from "../../auth/AuthContext";
import { listMyPatients } from "../../api/doctor";
import { LevelBadge, OriginBadge } from "../../components/ui/Badge";
import { Card, CardBody, PageHeader } from "../../components/ui/Card";
import Icon from "../../components/ui/Icon";
import StatTile from "../../components/ui/StatTile";
import { EmptyState, Section } from "../../components/ui/States";
import { formatAgo, formatDateTime, initials, round } from "../../lib/format";
import { useResource } from "../../lib/useResource";

// Severe / emergency: red glow and border. Lower levels: a left bar in the level colour. The LevelBadge always
// carries the text, so colour is never the only signal.
const ALARM = new Set(["severe", "emergency"]);
const BAR = { notice: "bg-level-notice", trend: "bg-level-trend", low: "bg-warning" };

function PatientCard({ p, timeZone }) {
  const level = p.highest_active_alert;
  const alarm = ALARM.has(level);
  return (
    <li>
      <Link to={`/doctor/patients/${p.id}`}
        className={`card group relative flex h-full flex-col gap-4 overflow-hidden rounded-2xl border bg-surface p-5 transition-[box-shadow,border-color] duration-200 hover:shadow-lift ${alarm ? "border-emergency shadow-glow-alarm" : "border-line/70 shadow-card hover:border-line-strong"}`}>
        {BAR[level] && <span className={`absolute inset-y-0 left-0 w-1.5 ${BAR[level]}`} aria-hidden="true" />}
        <div className="flex items-center gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-brand-soft text-sm font-bold text-brand">{initials(p.full_name)}</span>
          <div className="min-w-0 flex-1">
            <p className="truncate font-semibold text-ink">{p.full_name}</p>
            <p className="text-sm text-ink-muted">{p.age ? `${p.age} ans · ` : ""}{p.last_measured_at ? `dernière mesure ${formatAgo(p.last_measured_at)}` : "aucune mesure"}</p>
          </div>
          <Icon name="chevron" size={18} className="text-ink-subtle transition-transform group-hover:translate-x-0.5" />
        </div>
        <div className="flex flex-wrap items-end justify-between gap-3 rounded-xl bg-surface-muted/70 px-4 py-3">
          <div className="min-w-0">
            {p.latest_measurement ? (
              <>
                <p className="tnum text-2xl font-extrabold tracking-tight text-ink">{p.latest_measurement.systolic}/{p.latest_measurement.diastolic} <span className="text-xs font-medium text-ink-muted">mmHg</span></p>
                <p className="text-xs text-ink-muted">{formatDateTime(p.latest_measurement.measured_at, timeZone)}</p>
                <div className="mt-1.5"><OriginBadge reading={p.latest_measurement} /></div>
              </>
            ) : <span className="text-sm text-ink-subtle">—</span>}
          </div>
          <p className="tnum text-sm text-ink-muted">
            7 j : {p.avg_systolic_7d === null ? "—" : `${round(p.avg_systolic_7d)}/${round(p.avg_diastolic_7d)}`}
          </p>
        </div>
        <div className="mt-auto flex flex-wrap items-center gap-2">
          {level
            ? <><LevelBadge level={level} /><span className="tnum text-xs text-ink-muted">×{p.active_alert_count}</span></>
            : <span className="text-xs text-ink-subtle">Aucune alerte</span>}
        </div>
      </Link>
    </li>
  );
}

/** The server returns only patients with an active assignment to this doctor, most urgent first. */
export default function DoctorDashboard() {
  const { user } = useAuth();
  const [query, setQuery] = useState("");
  const patients = useResource((signal) => listMyPatients({ signal }), "patients");
  const reload = patients.reload;
  // Conception §8.2: the list refreshes every 15 s. No notification exists: the doctor is not alerted in real time.
  useEffect(() => {
    const id = setInterval(reload, 15000);
    return () => clearInterval(id);
  }, [reload]);

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Espace médecin" title="Mes patients"
        subtitle={(
          <span className="inline-flex items-start gap-2">
            <span className="relative mt-1.5 flex h-2.5 w-2.5 shrink-0" aria-hidden="true">
              <span className="absolute inset-0 animate-pulse-ring rounded-full bg-success" />
              <span className="relative h-2.5 w-2.5 rounded-full bg-success" />
            </span>
            Patients qui vous sont assignés, alerte la plus urgente en premier. Liste actualisée toutes les 15 secondes ; aucune notification n’est envoyée.
          </span>
        )} />
      <Section state={patients} what="vos patients">
        {(list) => {
          if (list.length === 0) {
            return <Card><CardBody className="pt-5"><EmptyState icon="users" title="Aucun patient assigné">Les patients apparaissent ici dès qu'ils vous sont assignés.</EmptyState></CardBody></Card>;
          }
          const q = query.trim().toLowerCase();
          const shown = q ? list.filter((p) => p.full_name.toLowerCase().includes(q)) : list;
          const alerting = list.filter((p) => p.active_alert_count > 0).length;
          return (
            <div className="space-y-5">
              <div className="stagger grid gap-4 sm:grid-cols-2">
                <StatTile label="Patients assignés" value={list.length} icon="users" />
                <StatTile label="Avec une alerte en cours" value={alerting} icon="bell" />
              </div>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="text-sm text-ink-muted">{list.length} patient(s) · {alerting} avec une alerte en cours</p>
                <label className="relative w-full sm:w-80">
                  <span className="sr-only">Rechercher un patient</span>
                  <Icon name="search" size={18} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-ink-subtle" />
                  <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Rechercher un patient"
                    className="field pl-10 text-sm" />
                </label>
              </div>
              <ul className="stagger grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                {shown.map((p) => <PatientCard key={p.id} p={p} timeZone={user.timezone} />)}
              </ul>
              {shown.length === 0 && <p className="text-sm text-ink-muted">Aucun patient ne correspond à « {query} ».</p>}
            </div>
          );
        }}
      </Section>
    </div>
  );
}
