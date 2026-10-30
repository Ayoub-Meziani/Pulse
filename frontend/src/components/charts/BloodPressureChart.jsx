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

const demoData = [
  { day: "Lun", systolic: 125, diastolic: 80 },
  { day: "Mar", systolic: 130, diastolic: 84 },
  { day: "Mer", systolic: 122, diastolic: 78 },
  { day: "Jeu", systolic: 135, diastolic: 86 },
  { day: "Ven", systolic: 128, diastolic: 82 },
  { day: "Sam", systolic: 124, diastolic: 79 },
  { day: "Dim", systolic: 126, diastolic: 81 },
];

export default function BloodPressureChart() {
  return (
    <div className="w-full">
      <div className="mb-5 flex items-center justify-between">
        <div>
          <h3 className="font-semibold text-slate-900">
            Évolution de la tension
          </h3>
          <p className="mt-1 text-sm text-slate-500">
            Exemple de données sur 7 jours
          </p>
        </div>

        <span className="rounded-full bg-amber-50 px-3 py-1 text-xs font-medium text-amber-700">
          DONNÉES DE DÉMO
        </span>
      </div>

      <div className="h-72 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={demoData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />

            <XAxis dataKey="day" stroke="#64748b" />

            <YAxis domain={[60, 160]} stroke="#64748b" />

            <Tooltip />

            <Legend />

            <Line
              type="monotone"
              dataKey="systolic"
              name="Systolique"
              stroke="#2563eb"
              strokeWidth={3}
            />

            <Line
              type="monotone"
              dataKey="diastolic"
              name="Diastolique"
              stroke="#0d9488"
              strokeWidth={3}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <p className="mt-3 text-xs text-slate-400">
        Ces valeurs sont fictives et ne représentent pas des mesures médicales.
      </p>
    </div>
  );
}