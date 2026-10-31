import { useCallback, useEffect, useId, useRef, useState } from "react";
import { Link } from "react-router";
import { listDoctorAlerts } from "../../api/doctor";
import { getEmergencyCard } from "../../api/patient";
import { FLAG_STATUS, flaggedAlerts, ringingItems, watchAlerts } from "../../lib/alertEvents";
import { alarmMode, pruneReduced, reduceSnapshot } from "../../lib/alarmView";
import { formatAgo, formatDateTime } from "../../lib/format";
import { OriginBadge } from "../ui/Badge";
import { ButtonLink } from "../ui/Button";
import Icon from "../ui/Icon";
import { AlarmBar, AlarmIcon, AlarmOverlay, StatusChip } from "./AlarmOverlay";
import AlertFlag from "./AlertFlag";
import AlertSound, { SoundControls } from "./AlertSound";

const TITLE = { emergency: "URGENCE", severe: "TENSION TRÈS ÉLEVÉE" };

function Fact({ label, children }) {
  return <div><dt className="text-xs font-semibold uppercase tracking-wider text-white/80">{label}</dt><dd className="mt-0.5 text-white">{children}</dd></div>;
}

/**
 * Doctor: every unresolved severe/emergency alert of assigned patients, on every page. An alert the patient has not
 * confirmed yet takes the whole screen in red (with its sound); "Réduire" keeps a red bar until something new
 * arrives. The flag goes when the doctor resolves the alert (existing workflow in the patient's record).
 */
export default function DoctorAlertFlag({ user }) {
  const [alerts, setAlerts] = useState([]);
  const [reduced, setReduced] = useState(null);
  const [cards, setCards] = useState({});  // patient_id -> card, or null when it failed. Never the patient's cache.
  const asked = useRef(new Set());
  const titleId = useId();
  const readingId = useId();

  const refresh = useCallback(async () => {
    try {
      const list = await listDoctorAlerts();
      setAlerts(list);
      setReduced((r) => pruneReduced(r, ringingItems(list)));
    } catch { /* keep what is shown; the next refresh retries */ }
  }, []);

  useEffect(() => watchAlerts(refresh), [refresh]);

  const items = ringingItems(alerts);
  const mode = alarmMode(items, reduced, false);
  const open = flaggedAlerts(alerts).filter((a) => a.status === "open");
  const top = open[0];
  const pid = mode !== "none" ? top?.patient_id : null;

  useEffect(() => {
    if (!pid || asked.current.has(pid)) return;
    asked.current.add(pid);
    getEmergencyCard(pid)
      .then((c) => setCards((m) => ({ ...m, [pid]: c })))
      .catch(() => setCards((m) => ({ ...m, [pid]: null })));
  }, [pid]);

  const reduce = () => setReduced(reduceSnapshot(items));
  const card = top ? cards[top.patient_id] : undefined;
  const r = top?.reading;
  const title = top ? `${TITLE[top.level] ?? "ALERTE"} — ${top.patient_name}` : "";

  return (
    <>
      <AlertSound source="doctor-flag" items={items} />

      {mode === "full" && top && (
        <AlarmOverlay titleId={titleId} readingId={readingId} onReduce={reduce}
          header={<SoundControls canMute inverse />} hint="Réduire pour continuer sur la page. Le son continue.">
          <div className="grid grid-cols-[minmax(0,1fr)] gap-8 lg:grid-cols-[minmax(0,1fr)_24rem]">
            <div className="space-y-6">
              <div className="flex flex-wrap items-center gap-5">
                <AlarmIcon />
                <div className="min-w-0">
                  <h2 id={titleId} tabIndex={-1} data-autofocus style={{ outline: "none" }}
                    className="text-4xl font-black leading-tight tracking-tight sm:text-6xl">{title}</h2>
                  <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2">
                    <StatusChip>{FLAG_STATUS.open.label}</StatusChip>
                    {open.length > 1 && <span className="rounded-full bg-white/15 px-3 py-1 text-sm font-bold">+{open.length - 1} autre(s) alerte(s) en attente</span>}
                  </div>
                  <p className="mt-2 inline-flex items-center gap-1.5 text-sm text-white/90">
                    <Icon name="clock" size={16} />Alerte créée {formatAgo(top.created_at)} · {formatDateTime(top.created_at, user.timezone)}
                  </p>
                </div>
              </div>

              <div id={readingId}>
                {r ? (
                  <>
                    <p className="tnum flex animate-reveal flex-wrap items-baseline gap-x-3 text-7xl font-black leading-none tracking-tight sm:text-9xl">
                      {r.systolic}/{r.diastolic}<span className="text-2xl font-bold tracking-normal text-white/85 sm:text-3xl">mmHg</span>
                    </p>
                    <p className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2 text-white/90">
                      <OriginBadge reading={r} />
                      <span>Mesurée le {formatDateTime(r.measured_at, user.timezone)}</span>
                    </p>
                  </>
                ) : <p className="text-4xl font-black sm:text-5xl">Signes d'alerte déclarés</p>}
              </div>

              {top.next_step && (
                <div className="rounded-2xl border border-white/25 bg-white/10 p-4">
                  <p className="text-lg font-semibold">{top.next_step}</p>
                  <p className="mt-2 text-xs text-white/80">Consigne du serveur (texte en anglais en attendant la traduction validée).</p>
                </div>
              )}

              <ButtonLink to={`/doctor/patients/${top.patient_id}?onglet=alertes`} variant="inverse" onClick={reduce}
                className="min-h-14 px-6 text-base">
                <Icon name="clipboard" size={20} />Ouvrir le dossier
              </ButtonLink>
            </div>

            <aside className="card self-start rounded-3xl border border-white/25 bg-white/10 p-5">
              <h3 className="inline-flex items-center gap-2 text-lg font-bold"><Icon name="user" size={20} />Fiche patient</h3>
              {card === undefined && <p role="status" className="mt-3 text-sm text-white/85">Chargement de la fiche…</p>}
              {card === null && <p className="mt-3 text-sm font-semibold">Fiche patient indisponible</p>}
              {card && (
                <dl className="mt-4 grid gap-y-3 text-sm">
                  <Fact label="Nom">{card.full_name}{card.age ? `, ${card.age} ans` : ""}</Fact>
                  <Fact label="Antécédents">{card.relevant_conditions.join(", ") || "—"}</Fact>
                  <Fact label="Allergies">{card.allergies || "—"}</Fact>
                  <Fact label="Traitement (tel que saisi par le patient)">{card.medication_context || "—"}</Fact>
                  <Fact label="Proche à contacter">
                    {card.primary_contact
                      ? <>{card.primary_contact.name}{card.primary_contact.relationship ? ` (${card.primary_contact.relationship})` : ""} · <span className="tnum">{card.primary_contact.phone}</span></>
                      : "—"}
                  </Fact>
                </dl>
              )}
            </aside>
          </div>

          <p className="mt-8 border-t border-white/20 pt-4 text-sm text-white/90">
            Le patient n'a pas encore confirmé avoir vu l'alerte. PULSE n'appelle pas les secours automatiquement.
          </p>
        </AlarmOverlay>
      )}

      {mode === "bar" && top && (
        <AlarmBar title={title} detail={r ? `${r.systolic}/${r.diastolic} mmHg` : "Signes d'alerte déclarés"}
          ago={formatAgo(top.created_at)} onExpand={() => setReduced(null)} />
      )}

      {alerts.length > 0 && (
        <div className="mb-6 space-y-3">
          {/* The most serious alert in full; the others in one line each, so the page stays reachable. */}
          {alerts.slice(1).length > 0 && (
            <details className="rounded-2xl border border-line bg-surface px-4 py-3 text-sm shadow-card">
              <summary className="min-h-11 cursor-pointer content-center font-semibold text-ink">
                {alerts.length - 1} autre(s) alerte(s) en attente de clôture
              </summary>
              <ul className="mt-2 divide-y divide-line">
                {alerts.slice(1).map((a) => (
                  <li key={a.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                    <span className="text-ink"><strong>{a.level === "emergency" ? "URGENCE" : "TENSION TRÈS ÉLEVÉE"}</strong> — {a.patient_name}
                      {a.reading && <span className="tnum text-ink-muted"> · {a.reading.systolic}/{a.reading.diastolic} mmHg</span>}
                      <span className="text-ink-muted"> · {formatAgo(a.created_at)}</span></span>
                    <Link to={`/doctor/patients/${a.patient_id}?onglet=alertes`} className="inline-flex min-h-11 items-center font-semibold text-brand underline">Ouvrir le dossier</Link>
                  </li>
                ))}
              </ul>
            </details>
          )}
          {alerts.slice(0, 1).map((a) => (
            <AlertFlag key={a.id} alert={a} reading={a.reading} timeZone={user.timezone} who={a.patient_name}>
              <Link to={`/doctor/patients/${a.patient_id}?onglet=alertes`}
                className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-surface px-4 text-sm font-semibold text-brand underline shadow-sm hover:bg-brand-soft">
                <Icon name="chevron" size={16} />Ouvrir le dossier pour examiner et clôturer
              </Link>
            </AlertFlag>
          ))}
        </div>
      )}
    </>
  );
}
