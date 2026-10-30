import { Link } from "react-router";
const demoPatients = [
  {
    id: 1,
    name: "Amine Benali",
    age: 45,
    systolic: 125,
    diastolic: 80,
    lastMeasurement: "Aujourd'hui, 09:30",
  },
  {
    id: 2,
    name: "Sara Haddad",
    age: 52,
    systolic: 138,
    diastolic: 88,
    lastMeasurement: "Aujourd'hui, 08:15",
  },
  {
    id: 3,
    name: "Karim Mansouri",
    age: 61,
    systolic: 132,
    diastolic: 84,
    lastMeasurement: "Hier, 18:45",
  },
];

export default function DoctorDashboard() {
  return (
    <div className="space-y-8">
      {/* En-tête */}
      <section>
        <p className="text-sm font-semibold text-blue-700">
          ESPACE MÉDECIN
        </p>

        <h1 className="mt-2 text-3xl font-bold tracking-tight text-slate-900">
          Tableau de bord
        </h1>

        <p className="mt-2 text-slate-500">
          Consultez les patients autorisés et suivez leurs mesures.
        </p>
      </section>

      {/* Statistiques */}
      <section className="grid grid-cols-1 gap-5 sm:grid-cols-2">
        <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <p className="text-sm font-medium text-slate-500">
            Patients suivis
          </p>

          <p className="mt-3 text-3xl font-bold text-slate-900">
            {demoPatients.length}
          </p>

          <p className="mt-2 text-sm text-slate-500">
            Patients fictifs pour la démonstration
          </p>
        </article>

        <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <p className="text-sm font-medium text-slate-500">
            Mesures affichées
          </p>

          <p className="mt-3 text-3xl font-bold text-slate-900">
            {demoPatients.length}
          </p>

          <p className="mt-2 text-sm text-slate-500">
            Valeurs de démonstration uniquement
          </p>
        </article>
      </section>

      {/* Liste des patients */}
      <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-200 p-6">
          <h2 className="text-lg font-semibold text-slate-900">
            Liste des patients
          </h2>

          <p className="mt-1 text-sm text-slate-500">
            Vue d'ensemble des dernières mesures disponibles.
          </p>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full min-w-[700px] text-left">
            <thead className="bg-slate-50">
              <tr>
                <th className="px-6 py-4 text-xs font-semibold uppercase tracking-wider text-slate-500">
                  Patient
                </th>

                <th className="px-6 py-4 text-xs font-semibold uppercase tracking-wider text-slate-500">
                  Âge
                </th>

                <th className="px-6 py-4 text-xs font-semibold uppercase tracking-wider text-slate-500">
                  Dernière mesure
                </th>

                <th className="px-6 py-4 text-xs font-semibold uppercase tracking-wider text-slate-500">
                  Date
                </th>

                <th className="px-6 py-4 text-xs font-semibold uppercase tracking-wider text-slate-500">
                  Accès
                </th>
              </tr>
            </thead>

            <tbody className="divide-y divide-slate-100">
              {demoPatients.map((patient) => (
                <tr
                  key={patient.id}
                  className="transition hover:bg-slate-50"
                >
                  <td className="px-6 py-5">
                    <div className="font-medium text-slate-900">
                      {patient.name}
                    </div>

                    <div className="mt-1 text-xs text-slate-500">
                      Patient de démonstration
                    </div>
                  </td>

                  <td className="px-6 py-5 text-sm text-slate-600">
                    {patient.age} ans
                  </td>

                  <td className="px-6 py-5">
                    <span className="font-semibold text-slate-800">
                      {patient.systolic}/{patient.diastolic}
                    </span>

                    <span className="ml-1 text-xs text-slate-500">
                      mmHg
                    </span>
                  </td>

                  <td className="px-6 py-5 text-sm text-slate-600">
                    {patient.lastMeasurement}
                  </td>

                  <td className="px-6 py-5">
                    <Link
                         to={`/doctor/patients/${patient.id}`}
                          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-blue-700"
                     >
                     Consulter
                     </Link>
</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="border-t border-slate-200 bg-slate-50 px-6 py-4">
          <p className="text-xs leading-5 text-slate-500">
            Toutes les identités et les mesures présentées sont fictives.
            Les données réelles seront fournies par le backend.
          </p>
        </div>
      </section>
    </div>
  );
}