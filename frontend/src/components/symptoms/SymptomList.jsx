import Badge from "../ui/Badge";
import { formatDateTime, SYMPTOM_LABEL } from "../../lib/format";

/** SymptomReportOut[]. The link to a reading is not stored yet (B24), so none is shown. */
export default function SymptomList({ reports, timeZone }) {
  if (reports.length === 0) return <p className="text-sm text-ink-muted">Aucun symptôme signalé.</p>;
  return (
    <ul className="divide-y divide-line">
      {reports.map((r) => (
        <li key={r.id} className={`flex flex-wrap items-center gap-2 py-3 ${r.source === "simulated" ? "border-l-2 border-dashed border-l-sim pl-3" : ""}`}>
          <span className="tnum w-full text-sm text-ink-muted sm:w-48">{formatDateTime(r.reported_at, timeZone)}</span>
          {r.symptoms.length === 0
            ? <span className="text-sm text-ink">Aucun des symptômes listés</span>
            : r.symptoms.map((s) => <Badge key={s} tone="neutral">{SYMPTOM_LABEL[s] ?? s}</Badge>)}
          {r.source === "simulated" && <Badge tone="sim" icon="flask">Simulé</Badge>}
        </li>
      ))}
    </ul>
  );
}
