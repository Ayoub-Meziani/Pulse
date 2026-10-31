import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router";
import { listMyPatients, listWearableFlags } from "../../api/doctor";
import { flagMetricLabel, formatAgo, formatPercent } from "../../lib/format";
import Icon from "../ui/Icon";

const EVERY = 30000;
const SHOWN = 5;
const disabled = (e) => e?.status === 404 && e.code === "feature_disabled";
const supported = typeof Notification !== "undefined";

/**
 * Doctor, on every page: open live early warnings (live-v1) of the assigned patients, checked every 30 s.
 * Advisory only: a purple banner, plus a browser notification for each NEW warning if the doctor allowed it.
 * No sound, nothing for the patient, never an alert (D18). Stops on a server that does not serve the ring models.
 * A warning leaves the banner when the doctor confirms or dismisses it in "Signaux bracelet".
 */
export default function DoctorRingWatch() {
  const navigate = useNavigate();
  const [warnings, setWarnings] = useState([]);  // [{ flag, patient }], newest first
  const [permission, setPermission] = useState(supported ? Notification.permission : "unsupported");
  const seen = useRef(null);  // ids already known; null before the first check, so old warnings never notify

  useEffect(() => {
    let stopped = false;
    let timer;
    async function check() {
      try {
        const patients = await listMyPatients();
        const lists = await Promise.all(patients.map((patient) =>
          listWearableFlags(patient.id, { kind: "early_warning", review_status: "open", limit: 20 }).then(
            (flags) => flags.map((flag) => ({ flag, patient })),
            (e) => { if (disabled(e)) throw e; return []; },  // e.g. assignment ended meanwhile
          )));
        if (stopped) return;
        const all = lists.flat().sort((a, b) => new Date(b.flag.created_at) - new Date(a.flag.created_at));
        if (seen.current && supported && Notification.permission === "granted") {
          for (const { flag, patient } of all.filter((w) => !seen.current.has(w.flag.id))) {
            const n = new Notification(`Signal précoce — ${patient.full_name}`, {
              body: `${flagMetricLabel(flag.metric)}${flag.score !== null ? ` · probabilité ${formatPercent(flag.score)}` : ""}`
                + " · modèle expérimental, pas une alerte",
              tag: flag.id,
            });
            n.onclick = () => { window.focus(); navigate(`/doctor/patients/${patient.id}?onglet=signaux`); };
          }
        }
        seen.current = new Set(all.map((w) => w.flag.id));
        setWarnings(all);
      } catch (e) {
        if (disabled(e)) return;  // not served here: stop checking
      }
      if (!stopped) timer = setTimeout(check, EVERY);
    }
    check();
    return () => { stopped = true; clearTimeout(timer); };
  }, [navigate]);

  if (warnings.length === 0) return null;
  return (
    <div className="mb-6 space-y-2 rounded-2xl border border-dashed border-ml/50 bg-ml-soft px-4 py-3 text-sm text-ml">
      <p className="flex flex-wrap items-center gap-2 font-semibold">
        <Icon name="sparkles" size={18} />
        {warnings.length} signal(aux) précoce(s) du bracelet à examiner
        <span className="font-normal">· expérimental, pas une alerte</span>
      </p>
      <ul className="space-y-1">
        {warnings.slice(0, SHOWN).map(({ flag, patient }) => (
          <li key={flag.id} className="flex flex-wrap items-center gap-x-2">
            <strong>{patient.full_name}</strong>
            <span>· {flagMetricLabel(flag.metric)}{flag.score !== null ? ` · probabilité ${formatPercent(flag.score)}` : ""} · {formatAgo(flag.created_at)}</span>
            <Link to={`/doctor/patients/${patient.id}?onglet=signaux`} className="inline-flex min-h-11 items-center font-semibold underline">Examiner</Link>
          </li>
        ))}
      </ul>
      {warnings.length > SHOWN && <p>+{warnings.length - SHOWN} autre(s)</p>}
      {permission === "default" && (
        <button type="button" onClick={() => Notification.requestPermission().then(setPermission)}
          className="inline-flex min-h-11 items-center gap-2 font-semibold underline">
          <Icon name="bell" size={16} />Recevoir aussi une notification du navigateur pour chaque nouveau signal
        </button>
      )}
      {permission === "denied" && <p className="text-xs">Notifications bloquées dans ce navigateur : seul ce bandeau s'affiche.</p>}
    </div>
  );
}
