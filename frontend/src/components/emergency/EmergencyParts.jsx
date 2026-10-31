import { useId } from "react";
import { formatDateTime, originOf } from "../../lib/format";
import Icon from "../ui/Icon";

// Parts shared by the emergency screen and the red alarm. tone="onRed": drawn for the alarm's red background.

/** A tel: link (the phone dials; PULSE never knows whether the call connected). */
export function TelLink({ number, ...rest }) {
  return <a href={`tel:${number.replace(/[^0-9+]/g, "")}`} {...rest} />;
}

const NUMBER_TONES = {
  primary: "btn-shine bg-linear-to-br from-emergency to-alarm-2 text-xl text-white shadow-glow-alarm hover:brightness-110",
  secondary: "border-2 border-emergency/40 bg-surface text-emergency hover:bg-level-severe-soft",
  onRed: "bg-white text-2xl text-alarm-2 shadow-[0_0_0_6px_rgb(255_255_255/0.18),0_18px_48px_-8px_rgb(0_0_0/0.45)] hover:bg-white/95 sm:text-3xl",
};

/** A tel: link the person taps; PULSE logs "tapped", never "called". */
export function NumberButton({ entry, primary, onTap, tone }) {
  if (!entry.number) {
    return <p className="rounded-2xl bg-warning-soft px-5 py-4 text-sm font-medium text-warning" role="alert">{entry.label_fr} : numéro non configuré sur ce serveur.</p>;
  }
  const look = NUMBER_TONES[tone === "onRed" ? "onRed" : primary ? "primary" : "secondary"];
  const big = tone === "onRed" || primary;
  return (
    <TelLink number={entry.number} onClick={onTap}
      className={`flex items-center justify-center gap-3 rounded-2xl px-6 py-4 text-center font-extrabold transition-[transform,box-shadow,filter,background-color] duration-200 active:scale-[.98] ${
        tone === "onRed" ? "min-h-20" : "min-h-16"} ${look}`}>
      <Icon name="phone" size={big ? 30 : 20} />
      <span>Appeler le <span className="tnum">{entry.number}</span><span className="block text-sm font-semibold opacity-90">{entry.label_fr}</span></span>
    </TelLink>
  );
}

/** What a bystander or the emergency services read. compact: one column (inside the alarm's side column). */
export function MedicalCard({ card, offline, tone, compact = false }) {
  const titleId = useId();
  if (!card) return null;
  const r = card.last_reading;
  const onRed = tone === "onRed";
  const dt = onRed ? "text-xs font-semibold uppercase tracking-wider text-white/80" : "text-xs font-semibold uppercase tracking-wider text-ink-subtle";
  const dd = onRed ? "mt-0.5 text-white" : "mt-0.5 text-ink";
  return (
    <section aria-labelledby={titleId}
      className={onRed ? "card rounded-3xl border border-white/25 bg-white/10 p-5 text-white backdrop-blur-sm"
        : "card rounded-2xl border border-line/70 bg-surface p-5 shadow-card sm:p-6"}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id={titleId} className={`inline-flex items-center gap-2 text-lg font-bold ${onRed ? "text-white" : "text-ink"}`}>
          <Icon name="heart" size={20} className={onRed ? "text-white" : "text-emergency"} />Carte médicale
        </h2>
        {offline && (
          <span className={`text-xs font-semibold ${onRed ? "rounded-full bg-white px-2 py-0.5 text-alarm-2" : "text-warning"}`}>
            Affichée depuis ce téléphone (hors ligne)
          </span>
        )}
      </div>
      <p className={`mt-1 text-sm ${onRed ? "text-white/85" : "text-ink-muted"}`}>À lire par la personne qui vous aide ou par les secours.</p>
      <dl className={`mt-4 grid gap-x-6 gap-y-3 text-sm ${compact ? "" : "sm:grid-cols-2"}`}>
        <div><dt className={dt}>Nom</dt><dd className={`${dd} text-base font-bold`}>{card.full_name}{card.age ? `, ${card.age} ans` : ""}</dd></div>
        <div><dt className={dt}>Antécédents</dt><dd className={dd}>{card.relevant_conditions.join(", ") || "—"}</dd></div>
        <div><dt className={dt}>Allergies</dt><dd className={dd}>{card.allergies || "—"}</dd></div>
        <div><dt className={dt}>Traitement (tel que saisi par le patient)</dt><dd className={dd}>{card.medication_context || "—"}</dd></div>
        <div><dt className={dt}>Médecin traitant</dt><dd className={dd}>{card.regular_doctor_name || "—"}{card.regular_clinic ? ` · ${card.regular_clinic}` : ""}</dd></div>
        <div><dt className={dt}>Dernière tension</dt><dd className={dd}>
          {r ? <><span className="tnum font-semibold">{r.systolic}/{r.diastolic} mmHg</span> · {formatDateTime(r.measured_at)} · {originOf(r).label}</> : "—"}
        </dd></div>
      </dl>
    </section>
  );
}
