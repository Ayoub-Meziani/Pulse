import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

export default function BloodPressureChart({ data = [] }) {
  return (
    <div className="w-full">
      <div className="mb-6">
        <h3 className="text-lg font-semibold text-slate-900">
          Évolution de la tension
        </h3>

        <p className="mt-1 text-sm text-slate-500">
          Suivez l'évolution de vos mesures dans le temps.
        </p>
      </div>

      {data.length === 0 ? (
        <div className="flex min-h-64 flex-col items-center justify-center rounded-xl border border-dashed border-slate-200 bg-slate-50 px-6 py-10 text-center">
          <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-emerald-50 text-xl text-emerald-700">
            ↗
          </div>

          <h4 className="font-medium text-slate-800">
            Aucune mesure disponible
          </h4>

          <p className="mt-2 max-w-sm text-sm leading-6 text-slate-500">
            Votre graphique apparaîtra ici dès que vos premières mesures
            seront enregistrées.
          </p>
        </div>
      ) : (
        <div className="h-72 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data}>
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="#e2e8f0"
              />

              <XAxis dataKey="day" stroke="#64748b" />

              <YAxis stroke="#64748b" />

              <Tooltip />

              <Legend />

              <Line
                type="monotone"
                dataKey="systolic"
                name="Systolique"
                stroke="#2563eb"
                strokeWidth={2.5}
                connectNulls
              />

              <Line
                type="monotone"
                dataKey="diastolic"
                name="Diastolique"
                stroke="#0d9488"
                strokeWidth={2.5}
                connectNulls
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}