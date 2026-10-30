export default function DoctorDashboard() {
return ( <div className="mx-auto max-w-7xl space-y-10">


  {/* Welcome section */}
  <section className="flex flex-col justify-between gap-5 sm:flex-row sm:items-end">
    <div>
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-emerald-700">
        Espace médical
      </p>

      <h1 className="mt-3 text-3xl font-semibold tracking-tight text-[#142b3b] sm:text-4xl">
        Tableau de bord
      </h1>

      <p className="mt-3 max-w-xl text-sm leading-6 text-slate-500">
        Retrouvez les informations de suivi et gérez vos patients depuis
        un espace centralisé.
      </p>
    </div>

    <div className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3">
      <span className="h-2.5 w-2.5 rounded-full bg-amber-400" />
      <span className="text-sm font-medium text-slate-600">
        Données en attente de connexion
      </span>
    </div>
  </section>

  {/* Overview cards */}
  <section className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">

    <article className="rounded-2xl border border-slate-200 bg-white p-6">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-slate-500">
          Patients suivis
        </p>

        <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-50 text-lg text-emerald-700">
          ♧
        </span>
      </div>

      <p className="mt-6 text-2xl font-semibold text-[#142b3b]">
        —
      </p>

      <p className="mt-2 text-xs text-slate-400">
        En attente des données du serveur
      </p>
    </article>

    <article className="rounded-2xl border border-slate-200 bg-white p-6">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-slate-500">
          Mesures enregistrées
        </p>

        <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-50 text-lg text-blue-700">
          ◷
        </span>
      </div>

      <p className="mt-6 text-2xl font-semibold text-[#142b3b]">
        —
      </p>

      <p className="mt-2 text-xs text-slate-400">
        En attente des données du serveur
      </p>
    </article>

    <article className="rounded-2xl border border-slate-200 bg-white p-6 sm:col-span-2 lg:col-span-1">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-slate-500">
          Alertes médicales
        </p>

        <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-amber-50 text-lg text-amber-700">
          !
        </span>
      </div>

      <p className="mt-6 text-2xl font-semibold text-[#142b3b]">
        —
      </p>

      <p className="mt-2 text-xs text-slate-400">
        En attente des données du serveur
      </p>
    </article>

  </section>

  {/* Patients section */}
  <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white">

    <div className="flex flex-col justify-between gap-3 border-b border-slate-100 px-6 py-6 sm:flex-row sm:items-center">
      <div>
        <h2 className="text-lg font-semibold text-[#142b3b]">
          Patients
        </h2>

        <p className="mt-1 text-sm text-slate-500">
          Accédez aux dossiers et aux informations de suivi.
        </p>
      </div>

      <span className="w-fit rounded-lg bg-slate-100 px-3 py-2 text-xs font-medium text-slate-500">
        Liste non disponible
      </span>
    </div>

    <div className="flex min-h-72 flex-col items-center justify-center px-6 py-12 text-center">

      <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-slate-50 text-2xl text-slate-400">
        ♙
      </div>

      <h3 className="mt-5 text-base font-semibold text-[#142b3b]">
        Aucun patient à afficher
      </h3>

      <p className="mt-2 max-w-sm text-sm leading-6 text-slate-500">
        Les patients autorisés apparaîtront ici lorsque les données
        seront disponibles.
      </p>

    </div>

  </section>

  {/* Information */}
  <section className="flex flex-col gap-4 rounded-2xl border border-emerald-100 bg-emerald-50/60 p-6 sm:flex-row sm:items-start">

    <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-white text-lg text-emerald-700">
      i
    </span>

    <div>
      <h3 className="text-sm font-semibold text-[#142b3b]">
        Espace de suivi médical
      </h3>

      <p className="mt-1 text-sm leading-6 text-slate-600">
        Les statistiques, les dossiers patients et les mesures seront
        affichés à partir des données disponibles sur le serveur.
        Aucune donnée fictive n'est utilisée dans cet espace.
      </p>
    </div>

  </section>

</div>


);
}