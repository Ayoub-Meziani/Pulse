import { useState } from "react";
import { useAuth } from "../../auth/AuthContext";
import { listAlerts, transitionAlert } from "../../api/patient";
import AlertList from "../../components/alerts/AlertList";
import AlertTimeline from "../../components/alerts/AlertTimeline";
import DismissNotice from "../../components/alerts/DismissNotice";
import Button from "../../components/ui/Button";
import { Card, CardBody, PageHeader } from "../../components/ui/Card";
import { EmptyState, Section } from "../../components/ui/States";
import { useResource } from "../../lib/useResource";

const FILTERS = [["active", "En cours"], ["all", "Toutes"]];

/** Patient alerts from the API. The patient can acknowledge an open alert and dismiss a notice (with a reason);
 * review and closure are the doctor's. */
export default function AlertsPage() {
  const { user } = useAuth();
  const [filter, setFilter] = useState("active");
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  const alerts = useResource((signal) => listAlerts(user.id, { status: filter, signal }), `al:${user.id}:${filter}`);

  async function acknowledge(alert) {
    setBusy(alert.id);
    setError(null);
    try {
      await transitionAlert(alert.id, "acknowledged");
      alerts.reload();
    } catch (e) {
      setError(e.status === 409 ? "Cette alerte a déjà changé de statut." : "Impossible de mettre à jour l'alerte. Réessayez.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Espace patient" title="Alertes"
        subtitle="Créées par les règles de sécurité à partir de vos mesures et symptômes. Votre médecin les examine." />
      <div className="inline-flex rounded-xl border border-line bg-surface p-1" role="tablist" aria-label="Filtre">
        {FILTERS.map(([value, text]) => (
          <button key={value} type="button" role="tab" aria-selected={filter === value} onClick={() => setFilter(value)}
            className={`min-h-10 rounded-lg px-4 text-sm font-semibold ${filter === value ? "bg-brand text-white" : "text-ink-muted hover:text-ink"}`}>
            {text}
          </button>
        ))}
      </div>
      {error && <p role="alert" className="rounded-xl bg-danger-soft px-4 py-3 text-sm text-danger">{error}</p>}
      <Card>
        <CardBody className="pt-5">
          <Section state={alerts} what="vos alertes">
            {(list) => list.length === 0 ? (
              <EmptyState icon="bell" title={filter === "active" ? "Aucune alerte en cours" : "Aucune alerte"}>
                Les alertes apparaissent ici quand une mesure ou un symptôme le justifie.
              </EmptyState>
            ) : (
              <AlertList alerts={list} timeZone={user.timezone}
                renderActions={(a) => (
                  <>
                    {a.status === "open" && (
                      <Button variant="secondary" disabled={busy === a.id} onClick={() => acknowledge(a)}>
                        {busy === a.id ? "Envoi…" : "J'ai pris connaissance de cette alerte"}
                      </Button>
                    )}
                    <DismissNotice alert={a} onDone={alerts.reload} />
                    <AlertTimeline alertId={a.id} timeZone={user.timezone} />
                  </>
                )} />
            )}
          </Section>
        </CardBody>
      </Card>
    </div>
  );
}
