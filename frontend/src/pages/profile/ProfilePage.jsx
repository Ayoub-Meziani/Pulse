import { useAuth } from "../../auth/AuthContext";
import { getCarePlan, getProfile, listTrustedContacts } from "../../api/patient";
import Badge from "../../components/ui/Badge";
import { Card, CardBody, CardHeader, PageHeader } from "../../components/ui/Card";
import { Section } from "../../components/ui/States";
import { formatDate } from "../../lib/format";
import { useResource } from "../../lib/useResource";

function Row({ label, children }) {
  return (
    <div className="grid gap-1 py-3 sm:grid-cols-3">
      <dt className="text-sm text-ink-muted">{label}</dt>
      <dd className="text-sm text-ink sm:col-span-2">{children || <span className="text-ink-subtle">Non renseigné</span>}</dd>
    </div>
  );
}

/** Read-only view of what the API stores for the patient. Trusted contacts are listed only; PULSE does not notify them. */
export default function ProfilePage() {
  const { user } = useAuth();
  const profile = useResource((signal) => getProfile(user.id, { signal }), `pr:${user.id}`);
  const plan = useResource((signal) => getCarePlan(user.id, { signal }), `cp:${user.id}`);
  const contacts = useResource((signal) => listTrustedContacts(user.id, { signal }), `tc:${user.id}`);

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Espace patient" title="Mon profil" />
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Informations" />
          <CardBody>
            <Section state={profile} what="votre profil">
              {(p) => (
                <dl className="divide-y divide-line">
                  <Row label="Nom">{p.full_name}</Row>
                  <Row label="Email">{p.email}</Row>
                  <Row label="Fuseau horaire">{p.timezone}</Row>
                  <Row label="Année de naissance">{p.birth_year}</Row>
                  <Row label="Médecin traitant">{p.regular_doctor_name}{p.regular_clinic ? ` · ${p.regular_clinic}` : ""}</Row>
                  <Row label="Antécédents déclarés">{p.relevant_conditions.join(", ")}</Row>
                  <Row label="Allergies">{p.allergies}</Row>
                  <Row label="Partage de la position">{p.consent_location ? "Autorisé en cas d'urgence" : "Non autorisé"}</Row>
                </dl>
              )}
            </Section>
          </CardBody>
        </Card>
        <div className="space-y-4">
          <Card>
            <CardHeader title="Plan de suivi" />
            <CardBody>
              <Section state={plan} what="votre plan de suivi">
                {(c) => (
                  <dl className="divide-y divide-line">
                    <Row label="Cible">
                      <span className="tnum font-semibold">{c.target_systolic}/{c.target_diastolic} mmHg</span>{" "}
                      {c.is_default ? <Badge>Cible générale</Badge> : <Badge tone="brand">Fixée par votre médecin</Badge>}
                    </Row>
                    <Row label="Mesures par jour">{c.monitoring_readings_per_day}</Row>
                    <Row label="Consigne du médecin">{c.clinician_guidance}</Row>
                    <Row label="Prochaine révision">{c.review_date && formatDate(c.review_date)}</Row>
                  </dl>
                )}
              </Section>
            </CardBody>
          </Card>
          <Card>
            <CardHeader title="Personnes de confiance" subtitle="Visibles sur votre carte d'urgence. PULSE ne les contacte pas automatiquement." />
            <CardBody>
              <Section state={contacts} what="vos contacts">
                {(list) => list.length === 0 ? <p className="text-sm text-ink-muted">Aucun contact enregistré.</p> : (
                  <ul className="divide-y divide-line">
                    {list.map((c) => (
                      <li key={c.id} className="flex flex-wrap items-center justify-between gap-2 py-3 text-sm">
                        <span className="font-medium text-ink">{c.name}{c.relationship ? <span className="font-normal text-ink-muted"> · {c.relationship}</span> : null}</span>
                        <span className="tnum text-ink-muted">{c.phone}</span>
                        {!c.active && <Badge>Inactif</Badge>}
                      </li>
                    ))}
                  </ul>
                )}
              </Section>
            </CardBody>
          </Card>
        </div>
      </div>
    </div>
  );
}
