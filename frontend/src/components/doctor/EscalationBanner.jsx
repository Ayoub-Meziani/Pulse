import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { acknowledgeStep, listDoctorEscalations, markStepDelivered } from "../../api/escalation";
import { formatDateTime } from "../../lib/format";
import Button from "../ui/Button";
import Icon from "../ui/Icon";

const POLL_MS = 15000;

/**
 * Active escalations sent to this doctor (in-app channel). Displaying one sends the delivery receipt;
 * "J'ai vu" is the acknowledgement. Neither means the patient was reached or that help arrived.
 */
export default function EscalationBanner({ timeZone }) {
  const [items, setItems] = useState([]);
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  const receipted = useRef(new Set());

  useEffect(() => {
    let stopped = false;
    const controller = new AbortController();
    async function poll() {
      try {
        const list = await listDoctorEscalations({ signal: controller.signal });
        if (stopped) return;
        setItems(list);
        for (const e of list) {
          if (e.step_status === "sent" && !receipted.current.has(e.step_id)) {
            receipted.current.add(e.step_id);
            markStepDelivered(e.step_id).catch(() => receipted.current.delete(e.step_id));
          }
        }
      } catch {
        /* keep the last list; the next poll retries */
      }
      if (!stopped) setTimeout(poll, POLL_MS);
    }
    poll();
    return () => { stopped = true; controller.abort(); };
  }, []);

  async function acknowledge(e) {
    setBusy(e.step_id);
    setError(null);
    try {
      await acknowledgeStep(e.step_id);
      setItems((list) => list.map((x) => (x.step_id === e.step_id ? { ...x, step_status: "acknowledged", status: "acknowledged" } : x)));
    } catch (err) {
      setError(err.status === 409 ? "Cette alerte a été annulée ou clôturée." : "Confirmation non enregistrée. Réessayez.");
    } finally {
      setBusy(null);
    }
  }

  if (items.length === 0) return null;
  return (
    <section role="alert" aria-label="Alertes d'urgence de vos patients" className="mb-6 space-y-3">
      {items.map((e) => (
        <div key={e.event_id} className="rounded-2xl border-2 border-emergency bg-level-severe-soft p-4">
          <p className="flex flex-wrap items-center gap-2 font-bold text-level-severe">
            <Icon name="alert" size={18} />
            {e.severity === "emergency" ? "Urgence signalée" : "Mesure très élevée à revoir"} : {e.patient_name}
            <span className="text-sm font-normal">· {formatDateTime(e.started_at, timeZone)}</span>
          </p>
          <p className="mt-1 text-sm text-level-severe">
            {e.severity === "emergency"
              ? "Le patient a ouvert l'écran d'urgence. PULSE n'a pas appelé les secours."
              : "Le patient a ouvert l'écran d'urgence après une mesure très élevée, sans signe d'alerte déclaré."}
            {e.location_shared ? " Position partagée dans le rapport." : ""}
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {e.step_status === "acknowledged"
              ? <p className="text-sm font-semibold text-success">Vous avez confirmé avoir vu cette alerte.</p>
              : <Button variant="emergency" disabled={busy === e.step_id} onClick={() => acknowledge(e)}>J'ai vu, je m'en occupe</Button>}
            <Link to={`/doctor/patients/${e.patient_id}`} className="inline-flex min-h-11 items-center px-2 text-sm font-semibold text-brand underline">Ouvrir le dossier</Link>
          </div>
          {e.ack_deadline && e.step_status !== "acknowledged" && (
            <p className="mt-2 text-xs text-level-severe">Sans confirmation avant {formatDateTime(e.ack_deadline, timeZone)}, le patient est invité à appeler lui-même.</p>
          )}
        </div>
      ))}
      {error && <p role="alert" className="text-sm text-danger">{error}</p>}
    </section>
  );
}
