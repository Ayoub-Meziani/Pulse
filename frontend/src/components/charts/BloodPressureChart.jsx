import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { formatDateTime, formatShortDate, originOf } from "../../lib/format";

const COLORS = { systolic: "#0b5cad", diastolic: "#0e7c86" };

// Simulated readings are drawn hollow so they are never mistaken for measurements; readings the database
// flagged "à vérifier" get a ring. Invalid readings are not drawn (the API leaves them out by default).
function dotFor(color) {
  return function Dot({ cx, cy, payload }) {
    if (cx === undefined || cy === undefined) return null;
    const simulated = originOf(payload).simulated;
    const review = payload.validation_status === "needs_review";
    return (
      <g key={`${payload.id}-${color}`}>
        {review && <circle cx={cx} cy={cy} r={7} fill="none" stroke="#7a5000" strokeWidth={1.5} />}
        <circle cx={cx} cy={cy} r={3.5} stroke={color} strokeWidth={2} fill={simulated ? "#ffffff" : color} />
      </g>
    );
  };
}

function ReadingTooltip({ active, payload, timeZone }) {
  if (!active || !payload?.length) return null;
  const r = payload[0].payload;
  return (
    <div className="rounded-lg border border-line bg-surface p-3 text-sm shadow-md">
      <p className="tnum font-semibold text-ink">{r.systolic}/{r.diastolic} mmHg{r.pulse ? ` · ${r.pulse} bpm` : ""}</p>
      <p className="text-ink-muted">{formatDateTime(r.measured_at, timeZone)}</p>
      <p className="mt-1 text-ink-muted">{originOf(r).label}{r.validation_status === "needs_review" ? " · à vérifier" : ""}</p>
    </div>
  );
}

const DOTS = { systolic: dotFor(COLORS.systolic), diastolic: dotFor(COLORS.diastolic) };

/** Props: readings (MeasurementOut[], any order), timeZone (IANA), target ({systolic, diastolic}) optional. */
export default function BloodPressureChart({ readings, timeZone, target }) {
  const data = [...readings]
    .filter((r) => r.validation_status !== "invalid")
    .sort((a, b) => new Date(a.measured_at) - new Date(b.measured_at))
    .map((r) => ({ ...r, day: formatShortDate(r.measured_at, timeZone) }));
  const hasSimulated = data.some((r) => originOf(r).simulated);

  if (data.length === 0) {
    return <p className="rounded-xl bg-canvas px-5 py-10 text-center text-sm text-ink-muted">Le graphique apparaîtra après la première mesure.</p>;
  }

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-muted">
        <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full" style={{ background: COLORS.systolic }} />Systolique</span>
        <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full" style={{ background: COLORS.diastolic }} />Diastolique</span>
        {target && <span className="inline-flex items-center gap-1.5"><span className="h-0 w-4 border-t-2 border-dashed border-ink-subtle" />Cible {target.systolic}/{target.diastolic}</span>}
        {hasSimulated && <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full border-2 border-sim bg-white" />Point creux = valeur simulée</span>}
      </div>
      <div className="h-64 w-full sm:h-72" role="img" aria-label={`Graphique de ${data.length} mesures de tension`}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e6ebf1" vertical={false} />
            <XAxis dataKey="day" stroke="#66737f" tickLine={false} fontSize={12} minTickGap={16} />
            <YAxis domain={[(min) => Math.floor((min - 10) / 10) * 10, (max) => Math.ceil((max + 10) / 10) * 10]}
              stroke="#66737f" tickLine={false} fontSize={12} width={44} />
            {target && <ReferenceLine y={target.systolic} stroke="#9aa7b5" strokeDasharray="5 4" />}
            {target && <ReferenceLine y={target.diastolic} stroke="#9aa7b5" strokeDasharray="5 4" />}
            <Tooltip content={<ReadingTooltip timeZone={timeZone} />} />
            <Line type="monotone" dataKey="systolic" name="Systolique" stroke={COLORS.systolic} strokeWidth={2.5}
              dot={DOTS.systolic} activeDot={false} isAnimationActive={false} />
            <Line type="monotone" dataKey="diastolic" name="Diastolique" stroke={COLORS.diastolic} strokeWidth={2.5}
              dot={DOTS.diastolic} activeDot={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
