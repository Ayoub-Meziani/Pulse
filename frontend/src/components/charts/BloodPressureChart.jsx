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
import { formatDateTime, formatShortDate, SOURCE } from "../../lib/format";

const COLORS = { systolic: "#2563eb", diastolic: "#0d9488" };

// Simulated readings are drawn as hollow points so they are never mistaken for measurements.
function dotFor(color) {
  return function Dot({ cx, cy, payload }) {
    if (cx === undefined || cy === undefined) return null;
    const simulated = payload.provenance === "simulated";
    return (
      <circle
        key={payload.id}
        cx={cx}
        cy={cy}
        r={4}
        stroke={color}
        strokeWidth={2}
        fill={simulated ? "#ffffff" : color}
      />
    );
  };
}

function ReadingTooltip({ active, payload, timeZone }) {
  if (!active || !payload?.length) return null;
  const r = payload[0].payload;
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3 text-sm shadow-md">
      <p className="font-semibold text-slate-900">{r.systolic} / {r.diastolic} mmHg</p>
      <p className="text-slate-500">{formatDateTime(r.measured_at, timeZone)}</p>
      <p className="mt-1 text-slate-600">
        {r.provenance === "simulated" ? "Simulée" : SOURCE[r.source] ?? r.source}
      </p>
    </div>
  );
}

const DOTS = { systolic: dotFor(COLORS.systolic), diastolic: dotFor(COLORS.diastolic) };

/** Props: readings (MeasurementOut[], any order), timeZone (IANA, from /me). */
export default function BloodPressureChart({ readings, timeZone }) {
  const data = [...readings]
    .sort((a, b) => new Date(a.measured_at) - new Date(b.measured_at))
    .map((r) => ({ ...r, day: formatShortDate(r.measured_at, timeZone) }));
  const hasSimulated = data.some((r) => r.provenance === "simulated");

  return (
    <div className="w-full">
      <div className="mb-5 flex items-center justify-between gap-3">
        <div>
          <h3 className="font-semibold text-slate-900">Évolution de la tension</h3>
          <p className="mt-1 text-sm text-slate-500">
            {data.length > 0 ? `${data.length} dernière(s) mesure(s) enregistrée(s)` : "Aucune mesure à afficher"}
          </p>
        </div>

        {hasSimulated && (
          <span className="shrink-0 rounded-full bg-violet-100 px-3 py-1 text-xs font-semibold text-violet-800">
            DONNÉES SIMULÉES
          </span>
        )}
      </div>

      {data.length === 0 ? (
        <div className="rounded-xl bg-slate-50 px-5 py-10 text-center text-sm text-slate-500">
          Le graphique apparaîtra après votre première mesure.
        </div>
      ) : (
        <div className="h-72 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="day" stroke="#64748b" />
              <YAxis domain={[(min) => Math.floor(min - 10), (max) => Math.ceil(max + 10)]} stroke="#64748b" />
              <Tooltip content={<ReadingTooltip timeZone={timeZone} />} />
              <Legend />
              <Line type="monotone" dataKey="systolic" name="Systolique" stroke={COLORS.systolic}
                strokeWidth={3} dot={DOTS.systolic} isAnimationActive={false} />
              <Line type="monotone" dataKey="diastolic" name="Diastolique" stroke={COLORS.diastolic}
                strokeWidth={3} dot={DOTS.diastolic} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {hasSimulated && (
        <p className="mt-3 text-xs text-slate-500">
          Les points creux sont des valeurs simulées : elles ne sont pas des mesures réelles.
        </p>
      )}
    </div>
  );
}
