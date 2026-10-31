import { useState } from "react";
import { dismissAlert } from "../../api/patient";
import { canDismiss } from "../../lib/alerts";
import { DISMISSAL_REASONS } from "../../lib/format";
import Button from "../ui/Button";

const NOTE_MAX = 500;

/**
 * "Écarter" form for a notice alert. The reason is required; "other" needs a note. The alert is kept in
 * the history and the doctor still sees it. Severe, trend and emergency alerts never show this form.
 */
export default function DismissNotice({ alert, onDone }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  if (!canDismiss(alert)) return null;
  if (!open) return <Button variant="ghost" onClick={() => setOpen(true)}>Écarter cette alerte…</Button>;

  const needsNote = reason === "other";
  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await dismissAlert(alert.id, reason, note.trim() || undefined);
      setOpen(false);
      onDone();
    } catch (e) {
      setError(e.status === 409 ? "Cette alerte ne peut plus être écartée (son statut ou son niveau a changé)."
        : e.status === 422 ? "Choisissez une raison (et précisez-la pour « Autre »)." : "Action impossible. Réessayez.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="w-full space-y-3 rounded-xl border border-line p-3">
      <fieldset>
        <legend className="text-sm font-semibold text-ink">Pourquoi écarter cette alerte ?</legend>
        <div className="mt-2 space-y-1.5">
          {DISMISSAL_REASONS.map(([value, label]) => (
            <label key={value} className="flex min-h-10 items-center gap-2 text-sm text-ink">
              <input type="radio" name={`reason-${alert.id}`} value={value} checked={reason === value}
                onChange={() => setReason(value)} />
              {label}
            </label>
          ))}
        </div>
      </fieldset>
      <label className="block text-sm font-medium text-ink">Précision{needsNote ? " (obligatoire)" : " (facultative)"}
        <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} maxLength={NOTE_MAX}
          className="mt-1 block w-full rounded-xl border border-line px-3 py-2 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand/20" />
      </label>
      <p className="text-xs text-ink-muted">L'alerte reste dans l'historique et votre médecin la verra toujours.</p>
      {error && <p role="alert" className="text-sm text-danger">{error}</p>}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={busy || !reason || (needsNote && !note.trim())}>
          {busy ? "Envoi…" : "Écarter l'alerte"}
        </Button>
        <Button variant="ghost" onClick={() => setOpen(false)}>Annuler</Button>
      </div>
    </form>
  );
}
