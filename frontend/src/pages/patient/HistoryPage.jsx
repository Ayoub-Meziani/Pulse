import { useAuth } from "../../auth/AuthContext";
import { listMeasurements, listSymptomReports } from "../../api/patient";
import BloodPressureChart from "../../components/charts/BloodPressureChart";
import ReadingList from "../../components/readings/ReadingList";
import { ButtonLink } from "../../components/ui/Button";
import { Card, CardBody, CardHeader, PageHeader } from "../../components/ui/Card";
import Icon from "../../components/ui/Icon";
import { EmptyState, Section } from "../../components/ui/States";
import SymptomList from "../../components/symptoms/SymptomList";
import { useResource } from "../../lib/useResource";

export default function HistoryPage() {
  const { user } = useAuth();
  const readings = useResource((signal) => listMeasurements(user.id, { limit: 200, signal }), `h:${user.id}`);
  const symptoms = useResource((signal) => listSymptomReports(user.id, { limit: 50, signal }), `sy:${user.id}`);

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Espace patient" title="Historique"
        subtitle="Toutes vos mesures, avec leur origine, et vos symptômes signalés."
        action={<ButtonLink to="/patient/mesure"><Icon name="plus" size={18} />Nouvelle mesure</ButtonLink>} />

      <Card>
        <CardHeader title="Évolution" />
        <CardBody>
          <Section state={readings} what="vos mesures">
            {(list) => <BloodPressureChart readings={list} timeZone={user.timezone} />}
          </Section>
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Mesures" subtitle="Les mesures jugées invalides par le serveur ne sont pas affichées." />
        <CardBody>
          <Section state={readings} what="vos mesures">
            {(list) => list.length === 0
              ? <EmptyState icon="pulse" title="Aucune mesure enregistrée">Vos mesures apparaîtront ici dès la première saisie.</EmptyState>
              : <ReadingList readings={list} timeZone={user.timezone} />}
          </Section>
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Symptômes signalés" />
        <CardBody>
          <Section state={symptoms} what="vos symptômes">
            {(list) => <SymptomList reports={list} timeZone={user.timezone} />}
          </Section>
        </CardBody>
      </Card>
    </div>
  );
}
