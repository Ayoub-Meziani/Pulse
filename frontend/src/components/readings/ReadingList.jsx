import { OriginBadge, ValidationBadge } from "../ui/Badge";
import { formatDateTime, originOf } from "../../lib/format";

const simulated = (r) => originOf(r).simulated === true;

/**
 * Blood-pressure readings (MeasurementOut[]). A timeline from md down, a table from md. Origin and
 * validation are always shown; values are never coloured as "normal/abnormal" here (that is the server's call).
 * Simulated rows keep a dashed violet marker next to their badge.
 */
export default function ReadingList({ readings, timeZone, limit }) {
  const rows = limit ? readings.slice(0, limit) : readings;
  const value = (r) => (r.validation_status === "invalid" ? "text-ink-subtle line-through" : "text-ink");
  return (
    <>
      <ol className="stagger relative space-y-3 before:absolute before:bottom-2 before:left-[7px] before:top-2 before:w-px before:bg-line md:hidden">
        {rows.map((r) => (
          <li key={r.id} className="relative flex gap-3">
            <span aria-hidden="true" className={`relative z-[1] mt-4 h-[15px] w-[15px] shrink-0 rounded-full border-2 bg-surface ${
              simulated(r) ? "border-dashed border-sim" : "border-brand"
            }`} />
            <div className={`flex min-w-0 flex-1 items-start justify-between gap-3 rounded-xl border px-3.5 py-3 ${
              simulated(r) ? "border-dashed border-sim/50 bg-sim-soft/40" : "border-line bg-surface"
            }`}>
              <div className="min-w-0">
                <p className={`tnum text-xl font-bold tracking-tight ${value(r)}`}>
                  {r.systolic}/{r.diastolic} <span className="text-sm font-normal text-ink-muted">mmHg</span>
                </p>
                <p className="text-sm text-ink-muted">
                  {formatDateTime(r.measured_at, timeZone)}{r.pulse ? <> · <span className="tnum">{r.pulse}</span> bpm</> : ""}
                </p>
              </div>
              <div className="flex flex-col items-end gap-1">
                <OriginBadge reading={r} />
                <ValidationBadge status={r.validation_status} />
              </div>
            </div>
          </li>
        ))}
      </ol>

      <div className="hidden overflow-x-auto md:block">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-line text-xs uppercase tracking-wide text-ink-subtle">
              <th scope="col" className="py-2.5 pl-3 pr-4 font-semibold">Date et heure</th>
              <th scope="col" className="py-2.5 pr-4 font-semibold">Tension</th>
              <th scope="col" className="py-2.5 pr-4 font-semibold">Pouls</th>
              <th scope="col" className="py-2.5 pr-4 font-semibold">Origine</th>
              <th scope="col" className="py-2.5 font-semibold">Contrôle</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {rows.map((r) => (
              <tr key={r.id} className={`transition-colors hover:bg-surface-muted/60 ${simulated(r) ? "bg-sim-soft/40" : ""}`}>
                <td className={`py-3 pl-3 pr-4 text-ink-muted ${simulated(r) ? "border-l-2 border-dashed border-l-sim" : "border-l-2 border-l-transparent"}`}>
                  {formatDateTime(r.measured_at, timeZone)}
                </td>
                <td className={`tnum py-3 pr-4 text-base font-bold ${value(r)}`}>
                  {r.systolic}/{r.diastolic} <span className="text-sm font-normal text-ink-muted">mmHg</span>
                </td>
                <td className="tnum py-3 pr-4 text-ink-muted">{r.pulse ? `${r.pulse} bpm` : "—"}</td>
                <td className="py-3 pr-4"><OriginBadge reading={r} /></td>
                <td className="py-3"><ValidationBadge status={r.validation_status} />{r.validation_status === "valid" && <span className="text-ink-subtle">—</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
