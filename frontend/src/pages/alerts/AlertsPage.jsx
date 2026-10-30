export default function AlertsPage({ alerts = [] }) {
  const unreadAlerts = alerts.filter(
    (alert) => !alert.isRead
  );

  return (
    <div className="space-y-8">
      {/* Header */}
      <section>
        <p className="text-xs font-semibold uppercase tracking-widest text-emerald-700">
          Centre de notifications
        </p>

        <h1 className="mt-2 text-3xl font-bold tracking-tight text-slate-900">
          Mes alertes
        </h1>

        <p className="mt-2 text-slate-500">
          Retrouvez les notifications liées à votre suivi médical.
        </p>
      </section>

      {/* Statistics */}
      <section className="grid gap-5 sm:grid-cols-2">
        <article className="rounded-2xl border border-slate-200 bg-white p-6">
          <p className="text-sm text-slate-500">
            Notifications
          </p>

          <p className="mt-3 text-3xl font-bold text-slate-900">
            {alerts.length}
          </p>
        </article>

        <article className="rounded-2xl border border-slate-200 bg-white p-6">
          <p className="text-sm text-slate-500">
            Non lues
          </p>

          <p className="mt-3 text-3xl font-bold text-slate-900">
            {unreadAlerts.length}
          </p>
        </article>
      </section>

      {/* Notifications */}
      <section className="rounded-2xl border border-slate-200 bg-white p-6 sm:p-8">
        <h2 className="text-lg font-semibold text-slate-900">
          Historique des notifications
        </h2>

        {alerts.length === 0 ? (
          <div className="mt-6 flex min-h-56 flex-col items-center justify-center rounded-xl border border-dashed border-slate-200 bg-slate-50 px-6 py-10 text-center">
            <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-emerald-50 text-xl text-emerald-700">
              ◷
            </div>

            <h3 className="font-medium text-slate-800">
              Aucune notification
            </h3>

            <p className="mt-2 max-w-sm text-sm leading-6 text-slate-500">
              Vos notifications apparaîtront ici lorsqu'elles seront disponibles.
            </p>
          </div>
        ) : (
          <div className="mt-6 space-y-4">
            {alerts.map((alert) => (
              <article
                key={alert.id}
                className="flex flex-col gap-3 rounded-xl border border-slate-200 p-5 sm:flex-row sm:items-start sm:justify-between"
              >
                <div>
                  <h3 className="font-semibold text-slate-900">
                    {alert.title}
                  </h3>

                  <p className="mt-2 text-sm leading-6 text-slate-600">
                    {alert.message}
                  </p>

                  <p className="mt-3 text-xs text-slate-400">
                    {alert.date}
                  </p>
                </div>

                <span className="w-fit rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600">
                  {alert.isRead ? "Lue" : "Non lue"}
                </span>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}