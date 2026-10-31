import { useCallback, useEffect, useId, useRef, useState, useSyncExternalStore } from "react";
import { confirmAlert, getAlert, getEmergencyCard, listAlerts } from "../../api/patient";
import { FLAG_STATUS, flaggedAlerts, isEmergencyScreenOpen, ringingItems, subscribeEmergencyScreen, watchAlerts } from "../../lib/alertEvents";
import { alarmMode, pruneReduced, reduceSnapshot } from "../../lib/alarmView";
import { flushQueued, incidentStore } from "../../lib/emergencyLog";
import { formatAgo, formatDateTime } from "../../lib/format";
import { closeIncident, openIncident, queueAction } from "../../lib/incident";
import { cacheCard, readCachedCard } from "../../lib/offlineCache";
import { MedicalCard, NumberButton } from "../emergency/EmergencyParts";
import { OriginBadge } from "../ui/Badge";
import Button, { ButtonLink } from "../ui/Button";
import Icon from "../ui/Icon";
import { AlarmBar, AlarmIcon, AlarmOverlay, StatusChip } from "./AlarmOverlay";
import AlertFlag from "./AlertFlag";
import AlertSound, { SoundControls } from "./AlertSound";

const TITLE = { emergency: "URGENCE", severe: "TENSION TRÈS ÉLEVÉE" };

function ConfirmWithPassword({ alertId, onDone, compact = false }) {
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

  // compact: inside the red bar (white text); full: a white card inside the red alarm.
  return (
    <form onSubmit={submit} className={compact ? "flex flex-wrap items-end gap-x-2 gap-y-1" : "card space-y-3 rounded-2xl bg-surface p-4 text-ink shadow-lift sm:p-5"}>
      <label className={`block text-sm font-semibold ${compact ? "min-w-0 flex-1 basis-48 text-white sm:flex-none" : "text-ink"}`}>
        {compact ? "Arrêter le son : votre mot de passe" : "J'ai vu cette alerte : confirmez avec votre mot de passe"}
        <input type="password" autoComplete="current-password" required value={password}
          onChange={(e) => setPassword(e.target.value)}
          className={`field mt-1 block w-full ${compact ? "sm:w-72" : "sm:max-w-xs"}`} />
      </label>
      {!compact && (
        <p className="text-xs text-ink-muted">Cette confirmation arrête le son. Votre médecin verra dans votre dossier que vous avez vu l'alerte : il n'est pas prévenu autrement. Ce n'est pas un avis médical : l'alerte reste affichée jusqu'à sa clôture par votre médecin.</p>
      )}
      {error && <p role="alert" className={`text-sm font-bold ${compact ? "w-full text-white" : "text-danger"}`}>{error}</p>}
      <Button type="submit" variant={compact ? "inverse" : "emergency"} disabled={busy || !password}>{busy ? "Vérification…" : "Confirmer"}</Button>
    </form>
  );
}

/**
 * Patient: the most serious unresolved severe/emergency alert, on every page, with its sound while unconfirmed.
 * An alert waiting for the password takes the whole screen in red (alarmMode): reading, call button, medical card.
 * "Réduire" turns it into a bar at the top of the page, so the symptom check, the recheck timer and the emergency
 * screen stay reachable; something new brings the full screen back. While the emergency screen is open it is
 * always the bar, so the call button there stays at the top.
 */
export default function PatientAlertFlag({ user, config }) {
  const [alerts, setAlerts] = useState([]);
  const [readings, setReadings] = useState({});
  const [reduced, setReduced] = useState(null);
  const [card, setCard] = useState(() => readCachedCard(user.id));
  const [cardOffline, setCardOffline] = useState(false);
  const latest = useRef(0);
  const cardFetched = useRef(false);
  const incident = useRef({});
  const titleId = useId();
  const readingId = useId();
  const compact = useSyncExternalStore(subscribeEmergencyScreen, isEmergencyScreenOpen);

  const refresh = useCallback(async () => {
    const call = ++latest.current;
    try {
      const list = flaggedAlerts(await listAlerts(user.id, { status: "all" }));
      if (call !== latest.current) return;  // an older answer arriving late must not bring back a confirmed alert
      setAlerts(list);
      setReduced((r) => pruneReduced(r, ringingItems(list)));
      const top = list.find((a) => a.status === "open") ?? list[0];
      if (top?.measurement_id) {
        const detail = await getAlert(top.id);
        // The newest reading of the episode: a recheck that reopened the alert is the one to show (its time is shown).
        const m = detail.measurements.at(-1) ?? detail.measurements.find((x) => x.id === top.measurement_id);
        if (m) setReadings((r) => ({ ...r, [top.id]: m }));
      }
    } catch {
      /* offline or server error: keep what is shown; the next refresh retries */
    }
  }, [user.id]);

  useEffect(() => watchAlerts(refresh), [refresh]);

  const items = ringingItems(alerts);
  const mode = alarmMode(items, reduced, compact);

  // The medical card, once, when an alarm shows (the cached copy shows at once and offline).
  useEffect(() => {
    if (mode === "none" || cardFetched.current) return;
    cardFetched.current = true;
    getEmergencyCard(user.id)
      .then((c) => { setCard(c); cacheCard(user.id, c); setCardOffline(false); })
      .catch(() => setCardOffline(true));
  }, [mode, user.id]);

  const top = alerts.find((a) => a.status === "open") ?? alerts[0];
  const reading = top ? readings[top.id] : null;
  const others = alerts.length > 1
    ? <p className="mt-2 text-sm">{alerts.length - 1} autre(s) alerte(s) en attente de clôture (page Alertes).</p> : null;
  const primary = config?.numbers?.find((n) => n.id === config.primary_number_id);

  // Same record as the emergency screen: "tapped", never "called"; queued here and sent in the background.
  function callTapped(entry) {
    const known = incidentStore.read().some((i) => i.id === incident.current[top.id]);
    if (!known) {  // the incident sent earlier left the queue: a new tap opens a new one
      incident.current[top.id] = openIncident(incidentStore, user.id, {
        trigger: top.symptom_report_id ? "symptom" : "severe_reading", alertId: top.id });
    }
    const id = incident.current[top.id];
    queueAction(incidentStore, id, "emergency_call_tapped", `${entry.id}${config.demo_mode ? " (demo)" : ""} · alarme`);
    closeIncident(incidentStore, id);
    flushQueued(user.id);
  }

  return (
    <>
      <AlertSound source="patient-flag" items={items} canMute={false} />

      {mode === "full" && top && (
        <AlarmOverlay titleId={titleId} readingId={readingId} onReduce={() => setReduced(reduceSnapshot(items))}
          header={<SoundControls canMute={false} inverse />}>
          <div className="grid grid-cols-[minmax(0,1fr)] gap-8 lg:grid-cols-[minmax(0,1fr)_24rem]">
            <div className="space-y-6">
              <div className="flex flex-wrap items-center gap-5">
                <AlarmIcon />
                <div className="min-w-0">
                  <h2 id={titleId} tabIndex={-1} data-autofocus style={{ outline: "none" }}
                    className="text-5xl font-black leading-none tracking-tight sm:text-7xl">
                    {TITLE[top.level] ?? "ALERTE"}
                  </h2>
                  <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2">
                    <StatusChip>{FLAG_STATUS.open.label}</StatusChip>
                    <span className="inline-flex items-center gap-1.5 text-sm text-white/90">
                      <Icon name="clock" size={16} />Alerte créée {formatAgo(top.created_at)} · {formatDateTime(top.created_at, user.timezone)}
                    </span>
                  </div>
                </div>
              </div>

              <div id={readingId}>
                {reading ? (
                  <>
                    <p className="tnum flex animate-reveal flex-wrap items-baseline gap-x-3 text-7xl font-black leading-none tracking-tight sm:text-9xl">
                      {reading.systolic}/{reading.diastolic}
                      <span className="text-2xl font-bold tracking-normal text-white/85 sm:text-3xl">mmHg</span>
                    </p>
                    <p className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2 text-white/90">
                      {reading.pulse != null && <span className="tnum font-semibold">Pouls {reading.pulse} bpm</span>}
                      <OriginBadge reading={reading} />
                      <span>Mesurée le {formatDateTime(reading.measured_at, user.timezone)}</span>
                    </p>
                  </>
                ) : top.measurement_id
                  ? <p className="text-2xl font-bold">Mesure de tension · détail en cours de chargement…</p>
                  : <p className="text-4xl font-black sm:text-5xl">Signes d'alerte déclarés</p>}
              </div>

              {top.next_step && (
                <div className="rounded-2xl border border-white/25 bg-white/10 p-4">
                  <p className="text-lg font-semibold">{top.next_step}</p>
                  <p className="mt-2 text-xs text-white/80">Consigne du serveur (texte en anglais en attendant la traduction validée).</p>
                </div>
              )}

              <div className="space-y-3">
                {primary ? (
                  <>
                    <NumberButton entry={primary} primary tone="onRed" onTap={() => callTapped(primary)} />
                    {config.demo_mode && (
                      <p className="rounded-xl border border-dashed border-sim/50 bg-sim-soft px-5 py-3 text-sm font-semibold text-sim">
                        MODE DÉMO : le bouton appelle le numéro de démonstration configuré, pas un service d'urgence.
                      </p>
                    )}
                  </>
                ) : (
                  <p role="alert" className="rounded-2xl bg-white px-5 py-4 text-sm font-semibold text-alarm-2">
                    Les numéros d'urgence n'ont pas pu être chargés : composez le numéro des secours avec votre téléphone.
                  </p>
                )}
                <ButtonLink to="/patient/urgence" variant="outline-inverse" className="w-full sm:w-auto">
                  <Icon name="users" size={18} />Écran d'urgence : prévenir un proche, partager ma position
                </ButtonLink>
              </div>

              <ConfirmWithPassword alertId={top.id} onDone={refresh} />
            </div>

            <aside className="space-y-4">
              <MedicalCard card={card} offline={cardOffline} tone="onRed" compact />
            </aside>
          </div>

          <div className="mt-8 border-t border-white/20 pt-4 text-sm text-white/90">
            <p>PULSE n'appelle pas les secours automatiquement et ne prévient pas votre médecin en temps réel.</p>
            {others}
          </div>
        </AlarmOverlay>
      )}

      {mode === "bar" && top && (
        <AlarmBar title={TITLE[top.level] ?? "ALERTE"}
          detail={reading ? `${reading.systolic}/${reading.diastolic} mmHg` : top.measurement_id ? null : "Signes d'alerte déclarés"}
          ago={formatAgo(top.created_at)} onExpand={compact ? null : () => setReduced(null)}>
          <ConfirmWithPassword alertId={top.id} onDone={refresh} compact />
        </AlarmBar>
      )}

      {mode === "none" && top && !compact && (
        <div className="mb-6">
          <AlertFlag alert={top} reading={reading} timeZone={user.timezone}>{others}</AlertFlag>
        </div>
      )}
    </>
  );
}
