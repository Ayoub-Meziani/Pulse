import { Link, useParams } from "react-router";

export default function PatientDetails() {
  const { patientId } = useParams();

  return (
    <div className="mx-auto max-w-5xl space-y-8">

      {/* Retour */}
      <Link
        to="/doctor"
        className="inline-flex items-center gap-2 text-sm font-medium text-slate-500 transition hover:text-emerald-700"
      >
        <span>←</span>
        Retour au tableau de bord
      </Link>

      {/* En-tête */}
      <section>
        <p className="text-xs font-semibold uppercase tracking-widest text-emerald-700">
          Espace médecin
        </p>

        <h1 className="mt-3 text-3xl font-semibold tracking-tight text-slate-900">
          Dossier patient
        </h1>

        <p className="mt-2 text-sm text-slate-500">
          Consultez les informations et le suivi médical du patient.
        </p>
      </section>

      {/* État vide */}
      <section className="rounded-3xl border border-slate-200 bg-white px-6 py-16 text-center shadow-sm sm:px-12">

        <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-emerald-50 text-2xl text-emerald-700">
          ♡
        </div>

        <h2 className="mt-6 text-xl font-semibold text-slate-900">
          Aucune donnée disponible
        </h2>

        <p className="mx-auto mt-3 max-w-md text-sm leading-6 text-slate-500">
          Les informations de ce patient ne sont pas encore disponibles.
          Elles apparaîtront ici une fois les données médicales connectées.
        </p>

        <div className="mx-auto mt-8 max-w-md rounded-xl bg-slate-50 p-4 text-left">
          <p className="text-xs font-medium uppercase tracking-wider text-slate-400">
            Référence du dossier
          </p>

          <p className="mt-1 break-all text-sm font-medium text-slate-700">
            {patientId}
          </p>
        </div>

        <Link
          to="/doctor"
          className="mt-8 inline-flex items-center justify-center rounded-xl bg-[#142b3b] px-6 py-3 text-sm font-medium text-white transition hover:bg-[#203e52]"
        >
          Retour aux patients
        </Link>

      </section>

    </div>
  );
}
