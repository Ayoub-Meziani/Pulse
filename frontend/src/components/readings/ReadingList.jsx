import { OriginBadge, ValidationBadge } from "../ui/Badge";
import { formatDateTime } from "../../lib/format";

/**
 * Blood-pressure readings (MeasurementOut[]). A table from md, stacked cards on phones. Origin and
 * validation are always shown; values are never coloured as "normal/abnormal" here (that is the server's call).
 */
export default function ReadingList({ readings, timeZone, limit }) {
  const rows = limit ? readings.slice(0, limit) : readings;
  return (
    <>
      <ul className="divide-y divide-line md:hidden">
        {rows.map((r) => (
          <li key={r.id} className="flex items-start justify-between gap-3 py-3">
            <div className="min-w-0">
              <p className={`tnum text-lg font-semibold ${r.validation_status === "invalid" ? "text-ink-subtle line-through" : "text-ink"}`}>
                {r.systolic}/{r.diastolic} <span className="text-sm font-normal text-ink-muted">mmHg</span>
              </p>
              <p className="text-sm text-ink-muted">
                {formatDateTime(r.measured_at, timeZone)}{r.pulse ? ` · ${r.pulse} bpm` : ""}
              </p>
            </div>
            <div className="flex flex-col items-end gap-1">
              <OriginBadge reading={r} />
              <ValidationBadge status={r.validation_status} />
            </div>
          </li>
        ))}
      </ul>

      <div className="hidden overflow-x-auto md:block">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-line text-xs uppercase tracking-wide text-ink-subtle">
              <th scope="col" className="py-2.5 pr-4 font-semibold">Date et heure</th>
              <th scope="col" className="py-2.5 pr-4 font-semibold">Tension</th>
              <th scope="col" className="py-2.5 pr-4 font-semibold">Pouls</th>
              <th scope="col" className="py-2.5 pr-4 font-semibold">Origine</th>
              <th scope="col" className="py-2.5 font-semibold">Contrôle</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {rows.map((r) => (
              <tr key={r.id}>
                <td className="py-3 pr-4 text-ink-muted">{formatDateTime(r.measured_at, timeZone)}</td>
                <td className={`tnum py-3 pr-4 font-semibold ${r.validation_status === "invalid" ? "text-ink-subtle line-through" : "text-ink"}`}>
                  {r.systolic}/{r.diastolic} <span className="font-normal text-ink-muted">mmHg</span>
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
