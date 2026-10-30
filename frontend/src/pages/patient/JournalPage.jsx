import { useState } from "react";
import { useAuth } from "../../auth/AuthContext";
import { addJournalEntry, listJournal } from "../../api/patient";
import JournalList from "../../components/journal/JournalList";
import { JOURNAL_CATEGORIES } from "../../lib/journal";
import Button from "../../components/ui/Button";
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

      <Card as="form" onSubmit={submit}>
        <CardHeader title="Nouvelle entrée" />
        <CardBody className="space-y-4">
          <fieldset>
            <legend className="text-sm font-medium text-ink">Catégorie</legend>
            <div className="mt-2 flex flex-wrap gap-2">
              {JOURNAL_CATEGORIES.map(([code, c]) => (
                <button key={code} type="button" onClick={() => setCategory(code)} aria-pressed={category === code}
                  className={`min-h-10 rounded-xl border px-3.5 text-sm font-medium ${category === code ? "border-brand bg-brand-soft text-brand" : "border-line bg-surface text-ink hover:bg-surface-muted"}`}>
                  {c.label}
                </button>
              ))}
            </div>
          </fieldset>
          <label className="block text-sm font-medium text-ink">Votre texte
            <textarea value={text} onChange={(e) => setText(e.target.value)} rows={4} maxLength={4000} required placeholder={current?.placeholder}
              className="mt-1.5 block w-full rounded-xl border border-line px-3.5 py-2.5 text-sm text-ink outline-none focus:border-brand focus:ring-2 focus:ring-brand/20" />
          </label>
          <p className="text-xs text-ink-muted">
            PULSE enregistre ce que vous écrivez sans l'analyser et ne donne pas de conseil alimentaire ou sportif. Pour un malaise,
            utilisez « Signaler des symptômes » ou le bouton Urgence : le journal ne déclenche aucune alerte.
          </p>
          {message && <p role={message.ok ? "status" : "alert"} className={`rounded-xl px-4 py-3 text-sm ${message.ok ? "bg-success-soft text-success" : "bg-danger-soft text-danger"}`}>{message.text}</p>}
          <Button type="submit" disabled={busy || !text.trim()}>{busy ? "Enregistrement…" : "Enregistrer"}</Button>
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Mes entrées"
          action={
            <label className="text-sm text-ink-muted">Filtrer{" "}
              <select value={filter} onChange={(e) => setFilter(e.target.value)} className="ml-1 rounded-lg border border-line bg-surface px-2 py-1.5 text-sm text-ink">
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
