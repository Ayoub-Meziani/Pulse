import { Link, useParams } from "react-router";
import demoPatients from "../../data/demoPatients";


export default function PatientDetails() {
  const { patientId } = useParams();

  const patient = demoPatients.find(
    (item) => item.id === patientId
  );

  if (!patient) {
    return (
      <div className="rounded-2xl bg-white p-8 shadow-sm">
        <h1 className="text-2xl font-bold text-slate-900">
          Patient introuvable
        </h1>

        <Link
          to="/doctor"
          className="mt-4 inline-block text-blue-700 hover:underline"
        >
          Retour au dashboard
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-8">

      {/* Retour */}
      <Link
        to="/doctor"
        className="inline-flex text-sm font-medium text-blue-700 hover:underline"
      >
        ← Retour aux patients
      </Link>

      {/* En-tête */}
      <section>
        <p className="text-sm font-semibold text-blue-700">
          DOSSIER PATIENT · DÉMONSTRATION
        </p>

        <h1 className="mt-2 text-3xl font-bold text-slate-900">
          {patient.name}
        </h1>

        <p className="mt-2 text-slate-500">
          Informations et suivi des mesures.
        </p>
      </section>

      {/* Informations personnelles */}
      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-lg font-semibold text-slate-900">
          Informations personnelles
        </h2>

        <div className="mt-6 grid gap-6 sm:grid-cols-2">
          <div>
            <p className="text-sm text-slate-500">Nom complet</p>
            <p className="mt-1 font-medium">{patient.name}</p>
          </div>

          <div>
            <p className="text-sm text-slate-500">Âge</p>
            <p className="mt-1 font-medium">{patient.age} ans</p>
          </div>

          <div>
            <p className="text-sm text-slate-500">Adresse e-mail</p>
            <p className="mt-1 font-medium">{patient.email}</p>
          </div>

          <div>
            <p className="text-sm text-slate-500">Téléphone</p>
            <p className="mt-1 font-medium">{patient.phone}</p>
          </div>
        </div>
      </section>

      {/* Dernière mesure */}
      <section className="grid gap-5 sm:grid-cols-2">
        <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <p className="text-sm text-slate-500">
            Dernière mesure
          </p>

          <p className="mt-3 text-3xl font-bold text-slate-900">
            {patient.systolic}/{patient.diastolic}
            <span className="ml-2 text-base font-medium text-slate-500">
              mmHg
            </span>
          </p>

          <p className="mt-3 text-sm text-slate-500">
            Valeur fictive de démonstration.
          </p>
        </article>

        <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <p className="text-sm text-slate-500">
            Date de la dernière mesure
          </p>

          <p className="mt-3 text-xl font-semibold text-slate-900">
            {patient.lastMeasurement}
          </p>
        </article>
      </section>

      {/* Historique */}
      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-lg font-semibold text-slate-900">
          Historique des mesures
        </h2>

        <div className="mt-6 flex min-h-48 items-center justify-center rounded-xl border border-dashed border-slate-300 bg-slate-50 p-6 text-center">
          <div>
            <p className="font-medium text-slate-700">
              Historique en préparation
            </p>

            <p className="mt-2 text-sm text-slate-500">
              Les données historiques seront intégrées depuis le backend.
            </p>
          </div>
        </div>
      </section>

    </div>
  );
}