import { useState } from "react";
import { Link } from "react-router";
import { useAuth } from "../../auth/AuthContext";
import { listMyPatients } from "../../api/doctor";
import { LevelBadge, OriginBadge } from "../../components/ui/Badge";
import { Card, CardBody, PageHeader } from "../../components/ui/Card";
import Icon from "../../components/ui/Icon";
import { EmptyState, Section } from "../../components/ui/States";
import { formatAgo, formatDateTime, initials, round } from "../../lib/format";
import { useResource } from "../../lib/useResource";

/** The server returns only patients with an active assignment to this doctor, most urgent first. */
export default function DoctorDashboard() {
  const { user } = useAuth();
  const [query, setQuery] = useState("");
  const patients = useResource((signal) => listMyPatients({ signal }), "patients");

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Espace médecin" title="Mes patients"
        subtitle="Patients qui vous sont assignés, alerte la plus urgente en premier." />
      <Card>
        <CardBody className="pt-5">
          <Section state={patients} what="vos patients">
            {(list) => {
              if (list.length === 0) {
                return <EmptyState icon="users" title="Aucun patient assigné">Les patients apparaissent ici dès qu'ils vous sont assignés.</EmptyState>;
              }
              const q = query.trim().toLowerCase();
              const shown = q ? list.filter((p) => p.full_name.toLowerCase().includes(q)) : list;
              const alerting = list.filter((p) => p.active_alert_count > 0).length;
              return (
                <div className="space-y-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <p className="text-sm text-ink-muted">{list.length} patient(s) · {alerting} avec une alerte en cours</p>
                    <label className="relative w-full sm:w-72">
                      <span className="sr-only">Rechercher un patient</span>
                      <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Rechercher un patient"
                        className="w-full rounded-xl border border-line bg-surface px-3.5 py-2.5 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand/20" />
                    </label>
                  </div>
                  <ul className="divide-y divide-line rounded-xl border border-line">
                    {shown.map((p) => (
                      <li key={p.id}>
                        <Link to={`/doctor/patients/${p.id}`} className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-4 hover:bg-canvas sm:flex-nowrap">
                          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-brand-soft text-sm font-semibold text-brand">{initials(p.full_name)}</span>
                          <div className="min-w-0 flex-1">
                            <p className="truncate font-semibold text-ink">{p.full_name}</p>
                            <p className="text-sm text-ink-muted">{p.age ? `${p.age} ans · ` : ""}{p.last_measured_at ? `dernière mesure ${formatAgo(p.last_measured_at)}` : "aucune mesure"}</p>
                          </div>
                          <div className="w-full sm:w-44">
                            {p.latest_measurement ? (
                              <>
                                <p className="tnum font-semibold text-ink">{p.latest_measurement.systolic}/{p.latest_measurement.diastolic} <span className="text-xs font-normal text-ink-muted">mmHg</span></p>
                                <p className="text-xs text-ink-muted">{formatDateTime(p.latest_measurement.measured_at, user.timezone)}</p>
                                <div className="mt-1"><OriginBadge reading={p.latest_measurement} /></div>
                              </>
                            ) : <span className="text-sm text-ink-subtle">—</span>}
                          </div>
                          <div className="tnum w-28 text-sm text-ink-muted">
                            7 j : {p.avg_systolic_7d === null ? "—" : `${round(p.avg_systolic_7d)}/${round(p.avg_diastolic_7d)}`}
                          </div>
                          <div className="flex w-40 items-center justify-end gap-2">
                            {p.highest_active_alert
                              ? <><LevelBadge level={p.highest_active_alert} /><span className="text-xs text-ink-muted">×{p.active_alert_count}</span></>
                              : <span className="text-xs text-ink-subtle">Aucune alerte</span>}
                            <Icon name="chevron" size={18} className="text-ink-subtle" />
                          </div>
                        </Link>
                      </li>
                    ))}
                  </ul>
                  {shown.length === 0 && <p className="text-sm text-ink-muted">Aucun patient ne correspond à « {query} ».</p>}
                </div>
              );
            }}
          </Section>
        </CardBody>
      </Card>
    </div>
  );
}
