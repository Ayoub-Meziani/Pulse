import { useState } from "react";
import { useAuth } from "../../auth/AuthContext";
import { listAlerts, transitionAlert } from "../../api/patient";
import AlertList from "../../components/alerts/AlertList";
import Button from "../../components/ui/Button";
import Icon from "../../components/ui/Icon";
import { Card, CardBody, PageHeader } from "../../components/ui/Card";
import { EmptyState, Section } from "../../components/ui/States";
import Tabs from "../../components/ui/Tabs";
import { useResource } from "../../lib/useResource";

const FILTERS = [["active", "En cours"], ["all", "Toutes"]];

/** Patient alerts from the API. The patient can only acknowledge an open alert; review and closure are the doctor's. */
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
      <div className="-mx-3">
        <Tabs items={FILTERS} value={filter} onChange={setFilter} label="Filtre" variant="segmented" idPrefix="alerts-filter" />
      </div>
      {error && <p role="alert" className="rounded-xl bg-danger-soft px-4 py-3 text-sm text-danger">{error}</p>}
      <Card role="tabpanel" id="alerts-filter-panel" aria-labelledby={`alerts-filter-tab-${filter}`} className="animate-fade-in" key={filter}>
        <CardBody className="pt-5">
          <Section state={alerts} what="vos alertes">
            {(list) => list.length === 0 ? (
              <EmptyState icon="bell" title={filter === "active" ? "Aucune alerte en cours" : "Aucune alerte"}>
                Les alertes apparaissent ici quand une mesure ou un symptôme le justifie.
              </EmptyState>
            ) : (
              <AlertList alerts={list} timeZone={user.timezone}
                renderActions={(a) => a.status === "open" && (
                  a.level === "severe" || a.level === "emergency"
                    ? <p className="flex items-start gap-2 text-sm font-medium text-ink"><Icon name="shield" size={18} className="mt-0.5 shrink-0 text-level-severe" />Confirmez cette alerte avec votre mot de passe dans l'alarme rouge (bandeau en haut de la page).</p>
                    : <Button variant="secondary" disabled={busy === a.id} onClick={() => acknowledge(a)}>
                      {busy === a.id ? "Envoi…" : "J'ai pris connaissance de cette alerte"}
                    </Button>
                )} />
            )}
          </Section>
        </CardBody>
      </Card>
    </div>
  );
}
