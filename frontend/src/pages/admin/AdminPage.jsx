import { useAuth } from "../../auth/AuthContext";
import { getEmergencyConfig } from "../../api/patient";
import Badge from "../../components/ui/Badge";
import { Card, CardBody, CardHeader, PageHeader } from "../../components/ui/Card";
import { Section } from "../../components/ui/States";
import { useResource } from "../../lib/useResource";

/**
 * Minimal administrator view. The API gives an administrator no access to patient records (403), so this
 * page shows only the account and the public configuration. Nothing here grants a permission.
 */
export default function AdminPage() {
  const { user } = useAuth();
  const config = useResource((signal) => getEmergencyConfig({ signal }), "admin-config");
  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Administration" title="Compte administrateur"
        subtitle="Les dossiers médicaux ne sont pas accessibles depuis un compte administrateur." />
      <div className="stagger grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader icon="user" title="Votre compte" />
          <CardBody>
            <dl className="divide-y divide-line rounded-xl border border-line px-4 text-sm">
              <div className="flex justify-between gap-3 py-2.5"><dt className="text-ink-muted">Nom</dt><dd className="text-ink">{user.full_name}</dd></div>
              <div className="flex justify-between gap-3 py-2.5"><dt className="text-ink-muted">Email</dt><dd className="break-all text-right text-ink">{user.email}</dd></div>
              <div className="flex justify-between gap-3 py-2.5"><dt className="text-ink-muted">Rôle</dt><dd><Badge tone="brand">Administrateur</Badge></dd></div>
              <div className="flex justify-between gap-3 py-2.5"><dt className="text-ink-muted">Fuseau horaire</dt><dd className="text-ink">{user.timezone}</dd></div>
            </dl>
          </CardBody>
        </Card>
        <Card>
          <CardHeader icon="phone" title="Configuration d'urgence publiée" subtitle="Lue depuis GET /config/emergency" />
          <CardBody>
            <Section state={config} what="la configuration">
              {(c) => (
                <div className="space-y-3 text-sm">
                  <p className="flex flex-wrap items-center gap-2">Mode démonstration : <Badge tone={c.demo_mode ? "sim" : "neutral"}>{c.demo_mode ? "activé" : "désactivé"}</Badge></p>
                  <ul className="divide-y divide-line rounded-xl border border-line px-4">
                    {c.numbers.map((n) => (
                      <li key={n.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5">
                        <span className="font-medium text-ink">{n.label_fr}{n.id === c.primary_number_id ? " (principal)" : ""}</span>
                        <span className="tnum text-ink-muted">{n.number ?? "non configuré"}</span>
                        <Badge tone={n.verified ? "success" : "warning"}>{n.verified ? "confirmé" : "non confirmé"}</Badge>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </Section>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
