const demoAlerts = [
  {
    id: 1,
    title: "Nouvelle mesure enregistrée",
    message: "Une nouvelle mesure a été ajoutée à votre historique.",
    date: "Aujourd'hui, 09:30",
    type: "info",
    status: "Lue",
  },
  {
    id: 2,
    title: "Suivi de votre tension",
    message: "Pensez à effectuer vos mesures selon les recommandations de votre professionnel de santé.",
    date: "Hier, 18:00",
    type: "warning",
    status: "Non lue",
  },
  {
    id: 3,
    title: "Connexion du capteur",
    message: "Le statut de votre capteur sera disponible après son intégration.",
    date: "26 octobre 2026",
    type: "info",
    status: "Lue",
  },
];

const styles = {
  info: {
    badge: "bg-blue-100 text-blue-700",
    dot: "bg-blue-500",
    label: "Information",
  },
  warning: {
    badge: "bg-amber-100 text-amber-700",
    dot: "bg-amber-500",
    label: "Attention",
  },
};

export default function AlertsPage() {
  return (
    <div className="space-y-8">

      {/* Header */}
      <section>
        <p className="text-sm font-semibold text-blue-700">
          CENTRE DE NOTIFICATIONS
        </p>

        <h1 className="mt-2 text-3xl font-bold text-slate-900">
          Mes alertes
        </h1>

        <p className="mt-2 text-slate-500">
          Retrouvez les notifications liées à votre suivi.
        </p>
      </section>

      {/* Statistics */}
      <section className="grid gap-5 sm:grid-cols-2">
        <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <p className="text-sm text-slate-500">
            Notifications
          </p>

          <p className="mt-3 text-3xl font-bold text-slate-900">
            {demoAlerts.length}
          </p>
        </article>

        <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <p className="text-sm text-slate-500">
            Non lues
          </p>

          <p className="mt-3 text-3xl font-bold text-slate-900">
            {demoAlerts.filter(
              (alert) => alert.status === "Non lue"
            ).length}
          </p>
        </article>
      </section>

      {/* Notifications list */}
      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">

        <h2 className="text-lg font-semibold text-slate-900">
          Historique des notifications
        </h2>

        <div className="mt-6 space-y-4">

          {demoAlerts.map((alert) => {
            const style = styles[alert.type];

            return (
              <article
                key={alert.id}
                className="flex flex-col gap-4 rounded-xl border border-slate-200 p-5 transition hover:bg-slate-50 sm:flex-row sm:items-start sm:justify-between"
              >
                <div className="flex gap-4">

                  <span
                    className={`mt-2 h-2.5 w-2.5 shrink-0 rounded-full ${style.dot}`}
                  />

                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="font-semibold text-slate-900">
                        {alert.title}
                      </h3>

                      <span
                        className={`rounded-full px-3 py-1 text-xs font-medium ${style.badge}`}
                      >
                        {style.label}
                      </span>
                    </div>

                    <p className="mt-2 text-sm leading-6 text-slate-600">
                      {alert.message}
                    </p>

                    <p className="mt-3 text-xs text-slate-400">
                      {alert.date}
                    </p>
                  </div>

                </div>

                <span className="w-fit rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600">
                  {alert.status}
                </span>

              </article>
            );
          })}

        </div>
      </section>

      <p className="text-xs text-slate-400">
        Toutes les notifications affichées sont fictives.
        Les alertes réelles seront fournies par le backend.
      </p>

    </div>
  );
}