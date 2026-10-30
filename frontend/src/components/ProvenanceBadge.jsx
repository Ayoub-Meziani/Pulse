import { PROVENANCE } from "../lib/format";

export default function ProvenanceBadge({ provenance }) {
  const style = PROVENANCE[provenance] ?? { label: provenance, tone: "bg-slate-100 text-slate-700" };
  return (
    <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold ${style.tone}`}>
      {style.label}
    </span>
  );
}
