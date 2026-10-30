import { useEffect, useState } from "react";
import { Link } from "react-router";
import { getEmergencyConfig } from "../../api/patient";
import Icon from "../../components/ui/Icon";

// Numbers and wording come from GET /config/emergency. PULSE never calls anyone: the patient taps
// the button and their own phone dials. In demo mode only the configured demo number is tappable,
// so a real emergency number can never be dialled during a demonstration. This screen never depends
// on a model or on the patient's data: it works with the public configuration alone.

function telHref(number) {
  return `tel:${number.replace(/[^0-9+]/g, "")}`;
}

function NumberButton({ entry, primary }) {
  if (!entry.number) {
    return (
      <p className="rounded-xl bg-warning-soft px-5 py-4 text-sm text-warning" role="alert">
        {entry.label_fr} : numéro non configuré sur ce serveur.
      </p>
    );
  }
  return (
    <a href={telHref(entry.number)}
      className={`flex min-h-16 items-center justify-center gap-3 rounded-2xl px-6 py-4 text-center font-bold shadow-sm ${
        primary ? "bg-emergency text-xl text-white hover:bg-emergency-hover" : "border-2 border-emergency/40 bg-surface text-emergency"
      }`}>
      <Icon name="phone" size={primary ? 26 : 20} />
      <span>
        Appeler le {entry.number}
        <span className="block text-sm font-medium opacity-90">{entry.label_fr}</span>
      </span>
    </a>
  );
}

export default function EmergencyScreen({ reason, nextStep, notSaved = false, initialConfig = null }) {
  const [config, setConfig] = useState(initialConfig);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (initialConfig) return undefined;
    const controller = new AbortController();
    getEmergencyConfig({ signal: controller.signal })
      .then(setConfig)
      .catch((error) => {
        if (error?.name !== "AbortError") setFailed(true);
      });
    return () => controller.abort();
  }, [initialConfig]);

  const primary = config?.numbers.find((n) => n.id === config.primary_number_id);
  const others = config?.numbers.filter((n) => n.id !== config.primary_number_id) ?? [];

  return (
    <section className="mx-auto max-w-2xl space-y-5" aria-labelledby="emergency-title">
      <div className="rounded-2xl border-2 border-emergency bg-level-severe-soft p-5 sm:p-7">
        <p className="inline-flex items-center gap-2 text-sm font-bold uppercase tracking-wider text-emergency"><Icon name="alert" size={18} />Urgence</p>
        <h1 id="emergency-title" className="mt-2 text-2xl font-bold text-level-severe sm:text-3xl">
          Si vous vous sentez mal, appelez les secours maintenant
        </h1>
        {notSaved && (
          <p className="mt-3 font-medium text-level-severe">Le serveur est injoignable : votre saisie n'a pas été enregistrée.</p>
        )}
        {(reason || nextStep) && (
          <div className="mt-4 rounded-xl bg-surface/70 p-4 text-level-severe">
            {reason && <p>{reason}</p>}
            {nextStep && <p className="mt-1 font-semibold">{nextStep}</p>}
            <p className="mt-2 text-xs opacity-80">Consigne du serveur (texte en anglais en attendant la traduction validée).</p>
          </div>
        )}
      </div>

      {config?.demo_mode && (
        <p className="rounded-xl border border-dashed border-sim/50 bg-sim-soft px-5 py-3 text-sm font-semibold text-sim">
          MODE DÉMO : le bouton appelle le numéro de démonstration configuré, pas un service d'urgence.
        </p>
      )}

      {!config && !failed && <p className="text-sm text-ink-muted" role="status">Chargement des numéros…</p>}
      {failed && (
        <p className="rounded-xl bg-warning-soft px-5 py-4 text-sm font-medium text-warning" role="alert">
          Les numéros d'urgence n'ont pas pu être chargés. Composez le numéro des secours avec votre téléphone.
        </p>
      )}

      {config && (
        <div className="space-y-4">
          {primary && <NumberButton entry={primary} primary />}
          <div className="rounded-2xl border border-line bg-surface p-5 text-sm text-ink">
            <p>{config.disclaimer_fr}</p>
            <p className="mt-3 text-base leading-7" dir="rtl" lang="ar">{config.disclaimer_ar}</p>
          </div>
          {others.length > 0 && (
            <div className="rounded-2xl border border-line bg-surface p-5 text-sm text-ink-muted">
              <p className="font-semibold text-ink">Autres numéros</p>
              <ul className="mt-3 space-y-2">
                {others.map((n) => (
                  <li key={n.id}>
                    {config.demo_mode ? (
                      <span>{n.label_fr} : <span className="tnum font-medium text-ink">{n.number ?? "non configuré"}</span> (désactivé en mode démo)</span>
                    ) : (
                      <NumberButton entry={n} />
                    )}
                    {!n.verified && <span className="ml-1 text-xs font-medium text-warning">· numéro non confirmé</span>}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      <Link to="/patient" className="inline-flex items-center gap-1 text-sm font-semibold text-brand"><Icon name="back" size={18} />Retour au tableau de bord</Link>
    </section>
  );
}
