import Badge from "../ui/Badge";
import { formatDateTime } from "../../lib/format";
import { JOURNAL_LABEL } from "../../lib/journal";

/** JournalOut[]; `renderActions(entry)` adds the doctor's review button. */
export default function JournalList({ entries, timeZone, renderActions }) {
  return (
    <ul className="divide-y divide-line">
      {entries.map((e) => (
        <li key={e.id} className="py-3">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={e.category === "question" ? "brand" : "neutral"}>{JOURNAL_LABEL[e.category] ?? e.category}</Badge>
            {e.doctor_review_status === "reviewed"
              ? <Badge tone="success" icon="check">Lu par le médecin</Badge>
              : <Badge tone="neutral">Pas encore lu</Badge>}
            <span className="ml-auto text-xs text-ink-subtle">{formatDateTime(e.created_at, timeZone)}</span>
          </div>
          <p className="mt-2 whitespace-pre-line text-sm text-ink">{e.entry_text}</p>
          {renderActions && <div className="mt-2">{renderActions(e)}</div>}
        </li>
      ))}
    </ul>
  );
}
