import { useId } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { formatDateTime, formatShortDate, originOf } from "../../lib/format";

// Recharts needs colour attributes, so the chart colours are hex constants (same values as the design tokens).
const COLORS = { systolic: "#1d4ed8", diastolic: "#0e7c86" };
const AXIS = "#5f6b78";
const GRID = "#eef2f6";
const TARGET = "#9aa7b5";

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
    <div className="glass rounded-xl p-3 text-sm shadow-lift">
      <p className="tnum font-semibold text-ink">{r.systolic}/{r.diastolic} mmHg{r.pulse ? ` · ${r.pulse} bpm` : ""}</p>
      <p className="text-ink-muted">{formatDateTime(r.measured_at, timeZone)}</p>
      <p className="mt-1 text-ink-muted">{originOf(r).label}{r.validation_status === "needs_review" ? " · à vérifier" : ""}</p>
    </div>
  );
}

const DOTS = { systolic: dotFor(COLORS.systolic), diastolic: dotFor(COLORS.diastolic) };

function targetLabel(text) {
  return { value: text, position: "right", fill: AXIS, fontSize: 11, fontWeight: 600 };
}

/** Props: readings (MeasurementOut[], any order), timeZone (IANA), target ({systolic, diastolic}) optional. */
export default function BloodPressureChart({ readings, timeZone, target }) {
  const gradient = `bp-area-${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;
  const data = [...readings]
    .filter((r) => r.validation_status !== "invalid")
    .sort((a, b) => new Date(a.measured_at) - new Date(b.measured_at))
    .map((r) => ({ ...r, day: formatShortDate(r.measured_at, timeZone) }));
  const hasSimulated = data.some((r) => originOf(r).simulated);

  if (data.length === 0) {
    return <p className="rounded-xl bg-surface-muted/60 px-5 py-10 text-center text-sm text-ink-muted">Le graphique apparaîtra après la première mesure.</p>;
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
          <ComposedChart data={data} margin={{ top: 8, right: target ? 64 : 8, bottom: 0, left: -12 }}>
            <defs>
              <linearGradient id={gradient} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={COLORS.systolic} stopOpacity={0.12} />
                <stop offset="100%" stopColor={COLORS.systolic} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke={GRID} vertical={false} />
            <XAxis dataKey="day" stroke={AXIS} tickLine={false} axisLine={false} fontSize={12} minTickGap={16} />
            <YAxis domain={[(min) => Math.floor((min - 10) / 10) * 10, (max) => Math.ceil((max + 10) / 10) * 10]}
              stroke={AXIS} tickLine={false} axisLine={false} fontSize={12} width={44} />
            {target && <ReferenceLine y={target.systolic} stroke={TARGET} strokeDasharray="5 4" label={targetLabel(`Cible ${target.systolic}`)} />}
            {target && <ReferenceLine y={target.diastolic} stroke={TARGET} strokeDasharray="5 4" label={targetLabel(`Cible ${target.diastolic}`)} />}
            <Tooltip content={<ReadingTooltip timeZone={timeZone} />} cursor={{ stroke: TARGET, strokeDasharray: "4 4" }}
              isAnimationActive={false} />
            {/* Decorative only: no legend entry, no tooltip value, no dots. */}
            <Area type="monotone" dataKey="systolic" stroke="none" fill={`url(#${gradient})`} legendType="none"
              tooltipType="none" dot={false} activeDot={false} isAnimationActive={false} />
            <Line type="monotone" dataKey="systolic" name="Systolique" stroke={COLORS.systolic} strokeWidth={2.5}
              strokeLinecap="round" strokeLinejoin="round" dot={DOTS.systolic} activeDot={false} isAnimationActive={false} />
            <Line type="monotone" dataKey="diastolic" name="Diastolique" stroke={COLORS.diastolic} strokeWidth={2.5}
              strokeLinecap="round" strokeLinejoin="round" dot={DOTS.diastolic} activeDot={false} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
