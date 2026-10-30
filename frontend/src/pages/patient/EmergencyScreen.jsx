import { useEffect, useState } from "react";
import { Link } from "react-router";
import { getEmergencyConfig } from "../../api/patient";

// Numbers and wording come from GET /config/emergency. PULSE never calls anyone: the patient taps
// the button and their own phone dials. In demo mode only the configured demo number is tappable,
// so a real emergency number can never be dialled during a demonstration.

function telHref(number) {
  return `tel:${number.replace(/[^0-9+]/g, "")}`;
}

function NumberButton({ entry, primary }) {
  if (!entry.number) {
    return (
      <p className="rounded-xl bg-amber-50 px-5 py-4 text-sm text-amber-900" role="alert">
        {entry.label_fr} : numéro non configuré sur ce serveur.
      </p>
    );
  }
  return (
    <a
      href={telHref(entry.number)}
      className={`block rounded-2xl px-6 py-5 text-center font-bold shadow-sm ${
        primary ? "bg-red-600 text-xl text-white hover:bg-red-700" : "border border-red-200 bg-white text-red-700"
      }`}
    >
      Appeler {entry.number}
      <span className="mt-1 block text-sm font-medium opacity-90">{entry.label_fr}</span>
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
    <section className="space-y-6" aria-labelledby="emergency-title">
      <div className="rounded-2xl border-2 border-red-300 bg-red-50 p-6 sm:p-8">
        <p className="text-sm font-semibold text-red-700">URGENCE</p>
        <h1 id="emergency-title" className="mt-2 text-3xl font-bold text-red-900">
          Appelez les secours maintenant
        </h1>
        {notSaved && (
          <p className="mt-3 text-sm font-medium text-red-900">
            Le serveur est injoignable : votre saisie n'a pas été enregistrée.
          </p>
        )}
        {(reason || nextStep) && (
          <div className="mt-4 text-red-900">
            {reason && <p>{reason}</p>}
            {nextStep && <p className="mt-1 font-semibold">{nextStep}</p>}
            <p className="mt-2 text-xs text-red-700">Consigne du serveur (texte en anglais en attendant la traduction validée).</p>
          </div>
        )}
      </div>

      {config?.demo_mode && (
        <p className="rounded-xl bg-violet-100 px-5 py-3 text-sm font-semibold text-violet-900">
          MODE DÉMO : le bouton appelle le téléphone d'un membre de l'équipe, pas un service d'urgence.
        </p>
      )}

      {!config && !failed && <p className="text-sm text-slate-500" role="status">Chargement des numéros…</p>}
      {failed && (
        <p className="rounded-xl bg-amber-50 px-5 py-4 text-sm text-amber-900" role="alert">
          Les numéros d'urgence n'ont pas pu être chargés. Appelez les secours avec votre téléphone.
        </p>
      )}

      {config && (
        <div className="space-y-4">
          {primary && <NumberButton entry={primary} primary />}
          {others.length > 0 && (
            <div className="rounded-2xl border border-slate-200 bg-white p-5 text-sm text-slate-600">
              <p className="font-medium text-slate-900">Autres numéros</p>
              <ul className="mt-2 space-y-2">
                {others.map((n) => (
                  <li key={n.id}>
                    {config.demo_mode ? (
                      <span>{n.label_fr} : {n.number ?? "non configuré"} (désactivé en mode démo)</span>
                    ) : (
                      <NumberButton entry={n} />
                    )}
                    {!n.verified && <span className="ml-1 text-xs text-amber-700">· numéro non vérifié</span>}
                  </li>
                ))}
              </ul>
            </div>
          )}
          <div className="rounded-2xl bg-slate-100 p-5 text-sm text-slate-700">
            <p>{config.disclaimer_fr}</p>
            <p className="mt-2" dir="rtl" lang="ar">{config.disclaimer_ar}</p>
          </div>
        </div>
      )}

      <Link to="/patient" className="inline-block text-sm font-medium text-blue-700">
        Retour au tableau de bord
      </Link>
    </section>
  );
}
