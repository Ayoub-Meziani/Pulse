import { Link } from "react-router";
import { markNotificationRead, listNotifications } from "../api/escalation";
import { useAuth } from "../auth/AuthContext";
import { Card, CardBody, PageHeader } from "../components/ui/Card";
import { EmptyState, Section } from "../components/ui/States";
import { formatDateTime } from "../lib/format";
import { useResource } from "../lib/useResource";

const TEXT = {
  alert_created: "Nouvelle alerte d'un patient",
  alert_raised: "Une alerte d'un patient est devenue plus grave",
  alert_reviewed: "Votre médecin a examiné une alerte",
  alert_resolved: "Votre médecin a clôturé une alerte",
  escalation: "Urgence signalée par un patient",
  escalation_update: "Mise à jour d'une alerte d'urgence",
};

function target(n, role) {
  if (role === "doctor" && n.patient_id) return `/doctor/patients/${n.patient_id}`;
  if (role === "patient" && n.alert_id) return "/patient/alertes";
  return null;
}

/** In-app notifications only: nothing is sent by SMS, e-mail or push yet. */
export default function NotificationsPage() {
  const { user } = useAuth();
  const list = useResource((signal) => listNotifications({ signal }), `notif:${user.id}`);

  function open(n) {
    if (!n.read_at) markNotificationRead(n.id).then(list.reload).catch(() => {});
  }

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="PULSE" title="Notifications" subtitle="Dans l'application uniquement : aucun SMS ni e-mail n'est envoyé." />
      <Card>
        <CardBody className="pt-5">
          <Section state={list} what="vos notifications">
            {(items) => items.length === 0 ? <EmptyState icon="info" title="Aucune notification" /> : (
              <ul className="space-y-2">
                {items.map((n) => {
                  const to = target(n, user.role);
                  const body = (
                    <>
                      <span className={`text-sm ${n.read_at ? "text-ink-muted" : "font-semibold text-ink"}`}>{TEXT[n.kind] ?? n.kind}</span>
                      <span className="text-xs text-ink-subtle">{formatDateTime(n.created_at, user.timezone)}{n.read_at ? "" : " · non lue"}</span>
                    </>
                  );
                  const cls = `flex flex-col gap-0.5 rounded-xl border px-4 py-3 ${n.urgent && !n.read_at ? "border-emergency/50 bg-level-severe-soft/50" : "border-line"}`;
                  return (
                    <li key={n.id}>
                      {to ? <Link to={to} onClick={() => open(n)} className={cls}>{body}</Link>
                        : <button type="button" onClick={() => open(n)} className={`${cls} w-full text-left`}>{body}</button>}
                    </li>
                  );
                })}
              </ul>
            )}
          </Section>
        </CardBody>
      </Card>
    </div>
  );
}
