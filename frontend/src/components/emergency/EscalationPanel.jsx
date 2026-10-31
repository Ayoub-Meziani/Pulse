import { useEffect, useState } from "react";
import { answerAlarm, cancelEscalation, getEscalation } from "../../api/escalation";
import { ESCALATION_STATUS, isActive, stepStatus, stepWho, visibleSteps } from "../../lib/escalation";
import Button from "../ui/Button";

const POLL_MS = 5000;
const CANCEL_REASONS = [["false_alarm", "Fausse alerte"], ["feel_better", "Je me sens mieux"]];

/**
 * "Qui est prévenu" on the emergency screen. It shows the server's record and nothing more. It never blocks
 * the call button above it: while the episode is not on the server yet, it says that nobody is notified.
 */
export default function EscalationPanel({ eventId, getCreated, enabled }) {
  const [escalation, setEscalation] = useState(null);
  const [offline, setOffline] = useState(false);
  const [busy, setBusy] = useState(false);
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!eventId) return undefined;
    let stopped = false;
    const controller = new AbortController();
    async function poll() {
      if (stopped) return;
      if (getCreated()) {
        try {
          const x = await getEscalation(eventId, { signal: controller.signal });
          if (!stopped) { setEscalation(x); setOffline(false); }
          if (!isActive(x)) return;  // closed or never escalated: nothing will change
        } catch (e) {
          if (e?.name === "AbortError") return;
          if (!stopped) setOffline(true);
        }
      }
      setTimeout(poll, POLL_MS);
    }
    poll();
    return () => { stopped = true; controller.abort(); };
  }, [eventId, getCreated]);

  async function act(call) {
    setBusy(true);
    setError(null);
    try { setEscalation(await call()); setConfirmCancel(false); }
    catch { setError("Action non enregistrée. Réessayez ; en cas de doute, appelez le 14."); }
    finally { setBusy(false); }
  }

  if (!enabled) {
    return (
      <section className="rounded-2xl border border-line bg-surface p-5" aria-labelledby="who-title">
        <h2 id="who-title" className="text-lg font-bold text-ink">Qui est prévenu ?</h2>
        <p className="mt-1 text-sm text-ink">Personne n'est prévenu automatiquement par PULSE. Appelez vous-même les secours et votre proche.</p>
      </section>
    );
  }

  const active = isActive(escalation);
  return (
    <section className="rounded-2xl border border-line bg-surface p-5" aria-labelledby="who-title" aria-live="polite">
      <h2 id="who-title" className="text-lg font-bold text-ink">Qui est prévenu ?</h2>
      {!escalation && (
        <p className="mt-1 text-sm text-ink">
          {offline ? "Hors ligne : personne n'est encore prévenu par PULSE. Appelez le 14." : "Enregistrement de l'alerte… Personne n'est encore prévenu."}
        </p>
      )}
      {escalation && !escalation.eligible && (
        <p className="mt-1 text-sm text-ink">PULSE ne prévient personne pour cet épisode. Appelez vous-même les secours et votre proche.</p>
      )}
      {escalation?.eligible && (
        <>
          <p className="mt-1 text-sm font-semibold text-ink">{ESCALATION_STATUS[escalation.status] ?? escalation.status}</p>
          <ul className="mt-3 space-y-2 text-sm">
            {visibleSteps(escalation).map((s) => (
              <li key={s.id} className="flex flex-wrap justify-between gap-x-3 rounded-xl bg-surface-muted px-3 py-2">
                <span className="font-medium text-ink">{stepWho(s)}</span>
                <span className="text-ink-muted">{stepStatus(s)}</span>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-xs text-ink-muted">Une notification n'est pas un appel : si personne ne confirme, appelez vous-même.</p>
        </>
      )}
      {active && (
        <div className="mt-4 space-y-3">
          <div className="flex flex-wrap gap-2">
            <Button variant="emergency" disabled={busy || escalation.patient_response === "need_help"}
              onClick={() => act(() => answerAlarm(eventId, "need_help"))}>J'ai besoin d'aide</Button>
            <Button variant="secondary" disabled={busy || escalation.patient_response === "ok"}
              onClick={() => act(() => answerAlarm(eventId, "ok"))}>Je vais bien</Button>
            {!confirmCancel && <Button variant="ghost" disabled={busy} onClick={() => setConfirmCancel(true)}>Annuler l'alerte…</Button>}
          </div>
          {confirmCancel && (
            <div className="rounded-xl border border-line p-3">
              <p className="text-sm font-semibold text-ink">Annuler l'alerte ? Votre médecin verra qu'elle a été annulée.</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {CANCEL_REASONS.map(([code, label]) => (
                  <Button key={code} variant="secondary" disabled={busy} onClick={() => act(() => cancelEscalation(eventId, code))}>{label}</Button>
                ))}
                <Button variant="ghost" onClick={() => setConfirmCancel(false)}>Garder l'alerte</Button>
              </div>
            </div>
          )}
          {error && <p role="alert" className="text-sm text-danger">{error}</p>}
        </div>
      )}
    </section>
  );
}
