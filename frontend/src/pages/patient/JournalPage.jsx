import { useState } from "react";
import { useAuth } from "../../auth/AuthContext";
import { addJournalEntry, listJournal } from "../../api/patient";
import JournalList from "../../components/journal/JournalList";
import { JOURNAL_CATEGORIES } from "../../lib/journal";
import Button from "../../components/ui/Button";
import Icon from "../../components/ui/Icon";
import { Card, CardBody, CardHeader, PageHeader } from "../../components/ui/Card";
import { EmptyState, Section } from "../../components/ui/States";
import { useResource } from "../../lib/useResource";

const FILTERS = [["", "Tout"], ...JOURNAL_CATEGORIES.map(([code, c]) => [code, c.label])];

/**
 * Journal (conception §14.1): the patient notes meals, physical activity, symptoms, medication or a question for the
 * doctor. These are the patient's own words: PULSE does not analyse them and gives no diet or exercise advice;
 * nothing here creates an alert. The assigned doctor reads the entries and answers through follow-up advice.
 */
export default function JournalPage() {
  const { user } = useAuth();
  const [category, setCategory] = useState("food");
  const [text, setText] = useState("");
  const [filter, setFilter] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(null);
  const entries = useResource((signal) => listJournal(user.id, { category: filter || undefined, signal }), `j:${user.id}:${filter}`);

  async function submit(event) {
    event.preventDefault();
    if (busy || !text.trim()) return;
    setBusy(true);
    setMessage(null);
    try {
      await addJournalEntry(user.id, { category, entry_text: text.trim() });
      setText("");
      setMessage({ ok: true, text: "Entrée enregistrée. Votre médecin la verra lors du suivi." });
      entries.reload();
    } catch (e) {
      setMessage({ ok: false, text: e.status === 422 ? "Le texte est vide ou trop long (4 000 caractères au maximum)." : "L'entrée n'a pas été enregistrée. Réessayez." });
    } finally {
      setBusy(false);
    }
  }

  const current = JOURNAL_CATEGORIES.find(([code]) => code === category)?.[1];

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Espace patient" title="Journal"
        subtitle="Notez vos repas, votre activité physique, vos symptômes ou une question pour votre médecin." />

      <Card as="form" variant="elevated" onSubmit={submit}>
        <CardHeader title="Nouvelle entrée" icon="note" />
        <CardBody className="space-y-4">
          <fieldset>
            <legend className="text-sm font-medium text-ink">Catégorie</legend>
            <div className="mt-2 flex flex-wrap gap-2">
              {JOURNAL_CATEGORIES.map(([code, c]) => (
                <button key={code} type="button" onClick={() => setCategory(code)} aria-pressed={category === code}
                  className={`min-h-11 rounded-full border px-4 text-sm font-semibold transition-[background-color,border-color,color,box-shadow] duration-200 ${category === code ? "border-brand bg-linear-to-br from-brand to-brand-hover text-white shadow-glow-brand" : "border-line bg-surface text-ink hover:border-line-strong hover:bg-surface-muted"}`}>
                  {c.label}
                </button>
              ))}
            </div>
          </fieldset>
          <label className="block text-sm font-medium text-ink">Votre texte
            <textarea value={text} onChange={(e) => setText(e.target.value)} rows={4} maxLength={4000} required placeholder={current?.placeholder}
              className="field mt-1.5 text-sm" />
          </label>
          <p className="flex gap-2 rounded-xl bg-surface-muted px-3 py-2.5 text-xs text-ink-muted">
            <Icon name="info" size={16} className="shrink-0" /><span>PULSE enregistre ce que vous écrivez sans l'analyser et ne donne pas de conseil alimentaire ou sportif. Pour un malaise,
            utilisez « Signaler des symptômes » ou le bouton Urgence : le journal ne déclenche aucune alerte.</span>
          </p>
          {message && <p role={message.ok ? "status" : "alert"} className={`rounded-xl px-4 py-3 text-sm ${message.ok ? "bg-success-soft text-success" : "bg-danger-soft text-danger"}`}>{message.text}</p>}
          <Button type="submit" disabled={busy || !text.trim()}>{busy ? "Enregistrement…" : "Enregistrer"}</Button>
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Mes entrées" icon="history"
          action={
            <label className="flex items-center gap-2 text-sm text-ink-muted">Filtrer{" "}
              <select value={filter} onChange={(e) => setFilter(e.target.value)} className="field w-auto py-2 text-sm">
                {FILTERS.map(([code, label]) => <option key={code} value={code}>{label}</option>)}
              </select>
            </label>
          } />
        <CardBody>
          <Section state={entries} what="votre journal">
            {(list) => list.length === 0
              ? <EmptyState icon="note" title="Aucune entrée">Vos repas, activités et questions apparaîtront ici.</EmptyState>
              : <JournalList entries={list} timeZone={user.timezone} />}
          </Section>
        </CardBody>
      </Card>
    </div>
  );
}
