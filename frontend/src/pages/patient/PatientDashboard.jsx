import BloodPressureChart from "../../components/charts/BloodPressureChart";
import AlertCard from "../../components/alerts/AlertCard";
import StatCard from "../../components/cards/StatCard";
export default function PatientDashboard() {
  return (
    <div className="space-y-8">

      {/* En-tête */}
      {/* <section>
        <p className="text-sm font-medium text-blue-700">
          ESPACE PATIENT
        </p>

        <h1 className="mt-2 text-3xl font-bold tracking-tight text-slate-900">
          Bonjour, bienvenue sur PulseCare
        </h1>

        <p className="mt-2 text-slate-500">
          Retrouvez vos mesures et suivez leur évolution.
        </p>
      </section> */}

      {/* Cartes principales */}
      <section className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">

  <StatCard
    title="Dernière mesure"
    value="-- / --"
    unit="mmHg"
    description="Aucune mesure réelle reçue."
  />

  <StatCard
    title="État du capteur"
    value="Inconnu"
    unit=""
    description="Connexion en attente."
  />

  <StatCard
    title="Historique"
    value="0"
    unit="mesure(s)"
    description="Aucune donnée enregistrée."
  />

</section>
<section>
  <div className="mb-4">
    <h2 className="text-xl font-bold text-slate-900">
      Notifications
    </h2>

    <p className="mt-1 text-sm text-slate-500">
      Retrouvez ici les informations concernant votre suivi.
    </p>
  </div>

  <AlertCard
    title="Notifications en préparation"
    message="Cette notification est un exemple d'interface. Les alertes réelles seront intégrées après la connexion au backend."
    variant="info"
  />
</section>


      {/* Zone du graphique */}
      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
  <BloodPressureChart />
</section>

      {/* Historique */}
      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">

        <h2 className="text-lg font-semibold text-slate-900">
          Historique des mesures
        </h2>

        <p className="mt-1 text-sm text-slate-500">
          Retrouvez ici les mesures précédemment enregistrées.
        </p>

        <div className="mt-6 rounded-xl bg-slate-50 px-5 py-10 text-center">
          <p className="text-sm text-slate-500">
            Aucune donnée disponible.
          </p>
        </div>

      </section>

    </div>
  );
}