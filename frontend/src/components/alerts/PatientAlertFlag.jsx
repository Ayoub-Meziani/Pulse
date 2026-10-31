import { useCallback, useEffect, useState } from "react";
import { confirmAlert, getAlert, listAlerts } from "../../api/patient";
import { flaggedAlerts, ringingItems, watchAlerts } from "../../lib/alertEvents";
import Button from "../ui/Button";
import AlertFlag from "./AlertFlag";
import AlertSound from "./AlertSound";

function ConfirmWithPassword({ alertId, onDone }) {
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await confirmAlert(alertId, password);
      onDone();
    } catch (e) {
      setError(e.code === "reauthentication_failed" ? "Mot de passe incorrect."
        : e.status === 409 ? "Cette alerte a déjà changé de statut." : "Confirmation non enregistrée. Réessayez.");
    } finally {
      setPassword("");  // never kept, even after an error
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-2 rounded-xl bg-surface p-3">
      <label className="block text-sm font-semibold text-ink">
        J'ai vu cette alerte : confirmez avec votre mot de passe
        <input type="password" autoComplete="current-password" required value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="mt-1 block w-full rounded-xl border border-line px-3 py-2 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand/20 sm:max-w-xs" />
      </label>
      <p className="text-xs text-ink-muted">Cette confirmation arrête le son et prévient votre médecin que vous avez vu l'alerte. Ce n'est pas un avis médical : l'alerte reste affichée jusqu'à sa clôture par votre médecin.</p>
      {error && <p role="alert" className="text-sm font-medium text-danger">{error}</p>}
      <Button type="submit" variant="emergency" disabled={busy || !password}>{busy ? "Vérification…" : "Confirmer"}</Button>
    </form>
  );
}

/** Patient: the most serious unresolved severe/emergency alert, on every page, with its sound while unconfirmed. */
export default function PatientAlertFlag({ user }) {
  const [alerts, setAlerts] = useState([]);
  const [readings, setReadings] = useState({});

  const refresh = useCallback(async () => {
    try {
      const list = flaggedAlerts(await listAlerts(user.id, { status: "all" }));
      setAlerts(list);
      const top = list[0];
      if (top?.measurement_id) {
        const detail = await getAlert(top.id);
        const m = detail.measurements.find((x) => x.id === top.measurement_id) ?? detail.measurements[0];
        if (m) setReadings((r) => ({ ...r, [top.id]: m }));
      }
    } catch {
      /* offline or server error: keep what is shown; the next refresh retries */
    }
  }, [user.id]);

  useEffect(() => watchAlerts(refresh), [refresh]);

  const top = alerts[0];
  return (
    <>
      <AlertSound source="patient-flag" items={ringingItems(alerts)} />
      {top && (
        <div className="mb-6">
          <AlertFlag alert={top} reading={readings[top.id]} timeZone={user.timezone}>
            {top.status === "open" && <ConfirmWithPassword alertId={top.id} onDone={refresh} />}
            {alerts.length > 1 && <p className="mt-2 text-sm text-ink-muted">{alerts.length - 1} autre(s) alerte(s) en attente de clôture (page Alertes).</p>}
          </AlertFlag>
        </div>
      )}
    </>
  );
}
