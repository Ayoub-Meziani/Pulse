import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { useAuth } from "../../auth/AuthContext";
import { getEmergencyCard, getEmergencyConfig } from "../../api/patient";
import { MedicalCard, NumberButton, TelLink } from "../../components/emergency/EmergencyParts";
import Button from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import Icon from "../../components/ui/Icon";
import { emergencyScreenOpened } from "../../lib/alertEvents";
import { flushQueued, incidentStore as store } from "../../lib/emergencyLog";
import { closeIncident, openIncident, queueAction, queuePatch } from "../../lib/incident";
import { cacheCard, cacheConfig, readCachedCard, readCachedConfig } from "../../lib/offlineCache";

// Emergency screen (conception §7.3). Order: call the emergency number, the trusted contact, the medical card a
// bystander can read, outcome. It renders from the server or, offline, from the device cache, and never waits
// for the incident record: every tap is queued and sent in the background. PULSE never calls anyone and never
// knows whether a call connected or a message was sent; the record says "tapped" / "opened".
// In demo mode only the configured demo number is tappable.

const OUTCOMES = [
  ["felt_better", "Je me sens mieux"],
  ["called_emergency", "J'ai appelé les secours"],
  ["went_to_hospital", "Je suis allé(e) aux urgences"],
  ["family_came", "Un proche est venu m'aider"],
  ["false_alarm", "Fausse alerte"],
];

function locate(timeoutMs = 8000) {
  return new Promise((resolve) => {
    if (!navigator.geolocation) { resolve({ status: "denied" }); return; }
    navigator.geolocation.getCurrentPosition(
      (p) => resolve({ status: "granted", lat: p.coords.latitude, lon: p.coords.longitude, accuracy: Math.round(p.coords.accuracy) }),
      (e) => resolve({ status: e.code === 3 ? "timeout" : "denied" }),
      { enableHighAccuracy: true, timeout: timeoutMs, maximumAge: 60000 },
    );
  });
}

function ContactCard({ contact, onCall, onShare, sharing, location, landmark, setLandmark, shareResult }) {
  return (
    <Card className="p-5 sm:p-6" aria-labelledby="contact-title">
      <h2 id="contact-title" className="inline-flex items-center gap-2 text-lg font-bold text-ink">
        <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand-soft text-brand"><Icon name="users" size={18} /></span>
        Prévenir un proche
      </h2>
      {contact ? (
        <>
          <p className="mt-1 text-sm text-ink-muted">Après avoir appelé les secours, ou en même temps. Cela ne remplace pas l'appel aux secours.</p>
          <TelLink number={contact.phone} onClick={onCall}
            className="mt-4 flex min-h-12 items-center justify-center gap-2 rounded-xl border border-line bg-surface px-4 font-semibold text-ink shadow-sm transition-colors hover:border-line-strong hover:bg-surface-muted">
            <Icon name="phone" size={18} />Appeler {contact.name}{contact.relationship ? ` (${contact.relationship})` : ""}
          </TelLink>
        </>
      ) : <p className="mt-1 text-sm text-ink-muted">Aucun proche enregistré. Vous pouvez en ajouter un dans votre profil.</p>}
      <label className="mt-4 block text-sm font-medium text-ink">Où suis-je ? <span className="font-normal text-ink-muted">(repère, facultatif)</span>
        <input value={landmark} onChange={(e) => setLandmark(e.target.value)} maxLength={200} placeholder="Ex. : entrée du marché, 2e étage"
          className="field mt-1.5 block w-full" />
      </label>
      <Button onClick={onShare} disabled={sharing} className="mt-3 min-h-12 w-full text-base">
        <Icon name="users" size={18} />{sharing ? "Recherche de la position…" : "Partager ma position"}
      </Button>
      <p className="mt-2 text-xs text-ink-muted">Votre position est demandée seulement maintenant, avec votre accord, et partagée par votre téléphone : vous choisissez à qui l'envoyer.</p>
      {location?.status === "granted" && (
        <p className="mt-3 text-sm text-ink">Position : <span className="tnum">{location.lat.toFixed(5)}, {location.lon.toFixed(5)}</span> (± {location.accuracy} m) ·{" "}
          <a className="font-semibold text-brand underline" target="_blank" rel="noreferrer" href={`https://maps.google.com/?q=${location.lat},${location.lon}`}>Ouvrir dans Maps</a></p>
      )}
      {location && location.status !== "granted" && (
        <p className="mt-3 text-sm text-warning">Position indisponible ({location.status === "timeout" ? "délai dépassé" : "refusée"}). Indiquez un repère ci-dessus.</p>
      )}
      {shareResult && <p className="mt-2 whitespace-pre-line text-sm text-ink-muted" role="status">{shareResult}</p>}
    </Card>
  );
}

export default function EmergencyScreen({ reason, nextStep, notSaved = false, initialConfig = null, trigger = "manual", alertId = null, symptoms = [] }) {
  const { user } = useAuth();
  const [config, setConfig] = useState(initialConfig ?? readCachedConfig());
  useEffect(() => emergencyScreenOpened(), []);  // the alert flag above shrinks to one line
  const [configOffline, setConfigOffline] = useState(false);
  const [card, setCard] = useState(() => readCachedCard(user.id));
  const [cardOffline, setCardOffline] = useState(false);
  const [location, setLocation] = useState(null);
  const [landmark, setLandmark] = useState("");
  const [sharing, setSharing] = useState(false);
  const [shareResult, setShareResult] = useState(null);
  const [outcome, setOutcome] = useState(null);
  const incident = useRef(null);

  const flush = () => flushQueued(user.id);
  const log = (action, detail = null) => {
    if (incident.current) { queueAction(store, incident.current, action, detail); flush(); }
  };

  // The incident record starts when the screen opens; nothing on screen waits for it.
  useEffect(() => {
    if (!incident.current) {
      incident.current = openIncident(store, user.id, { trigger, alertId, symptoms });
      queueAction(store, incident.current, "screen_opened", trigger);
      flush();
    }
    const retry = () => flush();
    window.addEventListener("online", retry);
    return () => window.removeEventListener("online", retry);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    if (!initialConfig) {
      getEmergencyConfig({ signal: controller.signal })
        .then((c) => { setConfig(c); cacheConfig(c); setConfigOffline(false); })
        .catch((e) => { if (e?.name !== "AbortError") setConfigOffline(true); });
    } else {
      cacheConfig(initialConfig);
    }
    getEmergencyCard(user.id, { signal: controller.signal })
      .then((c) => { setCard(c); cacheCard(user.id, c); setCardOffline(false); })
      .catch((e) => { if (e?.name !== "AbortError") setCardOffline(true); });
    return () => controller.abort();
  }, [initialConfig, user.id]);

  const primary = config?.numbers.find((n) => n.id === config.primary_number_id);
  const others = config?.numbers.filter((n) => n.id !== config.primary_number_id) ?? [];

  async function share() {
    setSharing(true);
    setShareResult(null);
    const pos = await locate();
    setLocation(pos);
    log(pos.status === "granted" ? "location_granted" : pos.status === "timeout" ? "location_timeout" : "location_denied");
    if (pos.status === "granted" && incident.current) {
      queuePatch(store, incident.current, { location: { lat: pos.lat, lon: pos.lon }, location_shared_with_consent: true });
      flush();
    }
    const r = card?.last_reading;
    const hhmm = (d) => new Date(d).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
    const text = [
      `PULSE : ${card?.full_name ?? user.full_name} a besoin d'aide.`,
      pos.status === "granted" ? `Position : https://maps.google.com/?q=${pos.lat},${pos.lon} (${hhmm(Date.now())}).` : null,
      landmark.trim() ? `Repère : ${landmark.trim()}.` : null,
      r ? `Dernière tension : ${r.systolic}/${r.diastolic} à ${hhmm(r.measured_at)}.` : null,
      primary?.number ? `Appelez-le/la ou appelez le ${primary.number}.` : null,
    ].filter(Boolean).join(" ");
    try {
      if (navigator.share) {
        await navigator.share({ text });
        log("share_opened", "share_sheet");
        setShareResult("Le partage a été ouvert sur votre téléphone. PULSE ne sait pas si le message est parti.");
      } else {
        const phone = card?.primary_contact?.phone?.replace(/[^0-9+]/g, "") ?? "";
        log("share_opened", "sms_composer");
        setShareResult("L'application SMS s'ouvre avec le message. Appuyez sur Envoyer : PULSE ne sait pas si le message est parti.");
        window.location.href = `sms:${phone}?body=${encodeURIComponent(text)}`;
      }
    } catch (e) {
      log("share_failed", String(e?.name ?? "error"));
      try {
        await navigator.clipboard.writeText(text);
        setShareResult("Partage annulé. Le message a été copié : collez-le dans une application de messagerie.");
      } catch {
        setShareResult(`Partage impossible. Lisez ce message à voix haute :\n${text}`);
      }
    } finally {
      setSharing(false);
    }
  }

  function reportOutcome(code, label) {
    setOutcome(label);
    if (incident.current) {
      queuePatch(store, incident.current, { reported_outcome: label, ended_at: new Date().toISOString() });
      queueAction(store, incident.current, "outcome_reported", code);
      closeIncident(store, incident.current);
      flush();
    }
  }

  return (
    <section className="mx-auto max-w-2xl space-y-5" aria-labelledby="emergency-title">
      <div className="alarm relative overflow-hidden rounded-3xl bg-alarm p-6 text-white shadow-glow-alarm sm:p-8">
        <div aria-hidden="true" className="pointer-events-none absolute -right-10 -top-10 h-48 w-48">
          {["0s", "0.66s", "1.33s"].map((d) => (
            <span key={d} className="absolute inset-0 animate-pulse-ring rounded-full border-2 border-white/30" style={{ animationDelay: d }} />
          ))}
        </div>
        <div className="relative">
          <p className="inline-flex items-center gap-2 rounded-full bg-white px-3 py-1 text-sm font-bold uppercase tracking-wider text-alarm-2"><Icon name="alert" size={18} />Urgence</p>
          <h1 id="emergency-title" className="mt-3 text-3xl font-black leading-tight tracking-tight sm:text-4xl">Si vous vous sentez mal, appelez les secours maintenant</h1>
          <p className="mt-2 text-lg font-semibold text-white/90">Appelez d'abord les secours, puis prévenez un proche.</p>
          {notSaved && <p className="mt-3 rounded-xl bg-white/15 px-4 py-2 font-semibold">Le serveur est injoignable : votre saisie n'a pas été enregistrée.</p>}
          {(reason || nextStep) && (
            <div className="mt-4 rounded-2xl border border-white/25 bg-white/10 p-4">
              {reason && <p>{reason}</p>}
              {nextStep && <p className="mt-1 font-semibold">{nextStep}</p>}
              <p className="mt-2 text-xs text-white/80">Consigne du serveur (texte en anglais en attendant la traduction validée).</p>
            </div>
          )}
        </div>
      </div>

      {config?.demo_mode && (
        <p className="rounded-xl border border-dashed border-sim/50 bg-sim-soft px-5 py-3 text-sm font-semibold text-sim">
          MODE DÉMO : le bouton appelle le numéro de démonstration configuré, pas un service d'urgence.
        </p>
      )}
      {!config && !configOffline && <p className="text-sm text-ink-muted" role="status">Chargement des numéros…</p>}
      {!config && configOffline && (
        <p className="rounded-xl bg-warning-soft px-5 py-4 text-sm font-medium text-warning" role="alert">
          Les numéros d'urgence n'ont pas pu être chargés. Composez le numéro des secours avec votre téléphone.
        </p>
      )}
      {config && primary && <NumberButton entry={primary} primary onTap={() => log("emergency_call_tapped", `${primary.id}${config.demo_mode ? " (demo)" : ""}`)} />}

      <ContactCard contact={card?.primary_contact} sharing={sharing} location={location} landmark={landmark} setLandmark={setLandmark}
        shareResult={shareResult} onShare={share} onCall={() => log("contact_call_tapped")} />

      <MedicalCard card={card} offline={cardOffline} />

      {config && (
        <Card className="p-5 text-sm text-ink sm:p-6">
          <p>{config.disclaimer_fr}</p>
          <p className="mt-3 text-base leading-7" dir="rtl" lang="ar">{config.disclaimer_ar}</p>
          {configOffline && <p className="mt-2 text-xs text-warning">Configuration affichée depuis ce téléphone (hors ligne).</p>}
        </Card>
      )}

      <Card className="p-5 sm:p-6" aria-labelledby="outcome-title">
        <h2 id="outcome-title" className="text-lg font-bold text-ink">Que s'est-il passé ?</h2>
        <p className="mt-1 text-sm text-ink-muted">Votre réponse est ajoutée au dossier de cet épisode. Votre médecin le consultera lors du suivi ; il n'est pas prévenu en temps réel.</p>
        {outcome ? (
          <p className="mt-3 flex items-center gap-2 rounded-xl bg-success-soft px-4 py-3 text-sm font-medium text-success" role="status">
            <Icon name="check" size={18} className="shrink-0" />
            Noté : « {outcome} ». Enregistré sur ce téléphone et envoyé au serveur dès que la connexion le permet.
          </p>
        ) : (
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            {OUTCOMES.map(([code, label]) => (
              <button key={code} type="button" onClick={() => reportOutcome(code, label)}
                className="group flex min-h-14 items-center gap-3 rounded-2xl border-2 border-line bg-surface px-4 text-left text-sm font-semibold text-ink transition-[border-color,background-color,transform] duration-200 hover:border-brand hover:bg-brand-soft active:scale-[.98]">
                <span aria-hidden="true" className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border-2 border-line-strong text-transparent transition-colors group-hover:border-brand group-hover:text-brand">
                  <Icon name="check" size={14} strokeWidth={3} />
                </span>
                {label}
              </button>
            ))}
          </div>
        )}
      </Card>

      {config && others.length > 0 && (
        <Card className="p-5 text-sm text-ink-muted sm:p-6">
          <p className="font-semibold text-ink">Autres numéros</p>
          <ul className="mt-3 space-y-2">
            {others.map((n) => (
              <li key={n.id}>
                {config.demo_mode
                  ? <span>{n.label_fr} : <span className="tnum font-medium text-ink">{n.number ?? "non configuré"}</span> (désactivé en mode démo)</span>
                  : <NumberButton entry={n} onTap={() => log("emergency_call_tapped", n.id)} />}
                {!n.verified && <span className="ml-1 text-xs font-medium text-warning">· numéro non confirmé</span>}
              </li>
            ))}
          </ul>
        </Card>
      )}

      <p className="text-xs text-ink-subtle">Prototype : PULSE n'appelle personne et ne détecte pas de malaise. Les appels et les partages se font depuis votre téléphone.</p>
      <Link to="/patient" className="inline-flex min-h-11 items-center gap-1 text-sm font-semibold text-brand hover:underline"><Icon name="back" size={18} />Retour au tableau de bord</Link>
    </section>
  );
}
