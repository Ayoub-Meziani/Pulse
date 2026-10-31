import { useEffect, useState } from "react";
import { approveBand, listBands, listWearableFlags, listWeeklyReports, rejectBand, reviewFlag, reviewWeeklyReport } from "../../api/doctor";
import Badge from "../ui/Badge";
import Button from "../ui/Button";
import { EmptyState, Section } from "../ui/States";
import {
  BAND_BASIS, BAND_STATISTIC, BAND_STATUS, CONTROL_STATUS, FLAG_KIND, FLAG_REVIEW, FLAG_WINDOW, flagMetricLabel,
  formatDate, formatDateTime, formatPercent, HOME_BP_CATEGORY, REPORT_STATUS, round, WEARABLE_METRIC,
} from "../../lib/format";
import { useResource } from "../../lib/useResource";

// The assigned doctor's view of the ring model outputs (offline jobs in ml/). Advisory only: nothing here is read by
// the rules, alerts or emergency guidance, and nothing notifies anyone. Every value and status is the server's.

const input = "mt-1.5 block w-full rounded-xl border border-line bg-surface px-3.5 py-2.5 text-sm text-ink outline-none focus:border-brand focus:ring-2 focus:ring-brand/20";
// Date-only values ("2026-10-26") parse as UTC midnight: format them in UTC so the day never shifts.
const DAY_TZ = "UTC";

function Notice() {
  return (
    <p className="rounded-xl border border-dashed border-ml/50 bg-ml-soft px-4 py-3 text-sm text-ml">
      Expérimental · non validé cliniquement · jamais une alerte · visible seulement quand cet onglet est ouvert (aucune notification)
    </p>
  );
}

const disabledOnServer = (state) => state.status === "error" && state.error?.status === 404 && state.error.code === "feature_disabled";

/** Section, except that a server not serving the ring models shows an empty state instead of an error. */
function RingSection({ state, what, children }) {
  if (disabledOnServer(state)) {
    return <EmptyState icon="shield" title="Désactivé sur ce serveur">Les sorties des modèles de la bague ne sont pas servies par ce serveur.</EmptyState>;
  }
  return <Section state={state} what={what}>{children}</Section>;
}

function StatusBadge({ map, status }) {
  const s = map[status] ?? { label: status, tone: "neutral" };
  return <Badge tone={s.tone}>{s.label}</Badge>;
}

/** Optional note + one button per decision. actions: [[label, (note) => Promise]]. conflict: text for a 409. */
function ReviewBox({ label, maxLength, actions, conflict, onDone }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function run(send) {
    setBusy(true);
    setError(null);
    try {
      await send(note.trim() || null);
      onDone();
    } catch (e) {
      setError(e.status === 409 ? conflict : "Action impossible. Réessayez.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-2">
      <label className="block text-sm font-medium text-ink">{label} <span className="font-normal text-ink-muted">(facultatif)</span>
        <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} maxLength={maxLength} className={input} />
      </label>
      <div className="flex flex-wrap gap-2">
        {actions.map(([text, send], i) => (
          <Button key={text} variant={i === 0 ? "primary" : "secondary"} disabled={busy} onClick={() => run(send)}>{text}</Button>
        ))}
      </div>
      {error && <p role="alert" className="text-sm text-danger">{error}</p>}
    </div>
  );
}

const ALREADY_REVIEWED = "Déjà examiné par un autre médecin.";

// ---------------------------------------------------------------- flags
function FlagItem({ flag, timeZone, onDone }) {
  const early = flag.kind === "early_warning";
  const unit = WEARABLE_METRIC[flag.metric]?.unit ?? "";
  return (
    <li className={`space-y-2 rounded-xl border p-4 ${early ? "border-ml/50 bg-ml-soft/60" : "border-line"}`}>
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={early ? "ml" : "wear"} icon={early ? "sparkles" : "watch"}>{FLAG_KIND[flag.kind] ?? flag.kind}</Badge>
        <span className="font-medium text-ink">{flagMetricLabel(flag.metric)}</span>
        <StatusBadge map={FLAG_REVIEW} status={flag.review_status} />
        <span className="ml-auto text-xs text-ink-subtle">
          {FLAG_WINDOW[flag.window_kind] ?? flag.window_kind} · {formatDateTime(flag.window_start, timeZone)} → {formatDateTime(flag.window_end, timeZone)}
        </span>
      </div>
      {(flag.value !== null || flag.score !== null) && (
        <p className="tnum text-sm text-ink">
          {flag.value !== null && (early ? `prévision dans 20 min : ${flag.value} ${unit}` : `valeur : ${flag.value} ${unit}`)}
          {flag.value !== null && flag.score !== null && " · "}
          {flag.score !== null && (early ? `probabilité ${formatPercent(flag.score)}` : `score ${flag.score}`)}
        </p>
      )}
      <p className="break-all text-xs text-ink-subtle">{flag.reference_basis} · modèle {flag.model_version}</p>
      {flag.review_status === "open" ? (
        <ReviewBox label="Note" maxLength={2000} conflict={ALREADY_REVIEWED} onDone={onDone} actions={[
          ["Confirmer", (note) => reviewFlag(flag.id, { review_status: "confirmed", review_note: note })],
          ["Écarter", (note) => reviewFlag(flag.id, { review_status: "dismissed", review_note: note })],
        ]} />
      ) : (
        <p className="text-xs text-ink-muted">Examiné {formatDateTime(flag.reviewed_at, timeZone)}{flag.review_note ? ` · « ${flag.review_note} »` : ""}</p>
      )}
    </li>
  );
}

export function RingSignals({ patientId, timeZone }) {
  const flags = useResource((signal) => listWearableFlags(patientId, { limit: 100, signal }), `wf:${patientId}`);
  const reload = flags.reload;
  const off = disabledOnServer(flags);
  // Refreshed every 10 s while this tab is open, like the doctor's patient list. No notification exists.
  useEffect(() => {
    if (off) return undefined;
    const id = setInterval(reload, 10000);
    return () => clearInterval(id);
  }, [reload, off]);

  return (
    <div className="space-y-4">
      <Notice />
      <RingSection state={flags} what="les signaux du bracelet">
        {(list) => list.length === 0 ? <EmptyState icon="watch" title="Aucun signal pour ce patient" /> : (
          <ul className="space-y-3">
            {list.map((f) => <FlagItem key={f.id} flag={f} timeZone={timeZone} onDone={reload} />)}
          </ul>
        )}
      </RingSection>
    </div>
  );
}

// ---------------------------------------------------------------- weekly reports
function Fact({ label, value, hint }) {
  return (
    <div className="rounded-xl border border-line p-3">
      <dt className="text-xs font-medium uppercase tracking-wide text-ink-subtle">{label}</dt>
      <dd className="mt-1 font-semibold text-ink">{value}</dd>
      {hint && <dd className="text-xs text-ink-muted">{hint}</dd>}
    </div>
  );
}

function ReportItem({ report, timeZone, onDone }) {
  const s = report.summary ?? {};
  const bp = s.bp_home ?? {};
  const ring = s.ring ?? {};
  const pop = s.pulse_vs_population;
  const mbp = s.mbp_estimate;
  const nights = Object.entries(WEARABLE_METRIC).flatMap(([m, meta]) => ["night_median", "night_min"]
    .filter((st) => ring[`${m}_${st}`] !== undefined && ring[`${m}_${st}`] !== null)
    .map((st) => ({ key: `${m}_${st}`, text: `${meta.label} (${BAND_STATISTIC[st]}) : ${ring[`${m}_${st}`]} ${meta.unit}` })));

  return (
    <li className="space-y-3 rounded-xl border border-line p-4">
      <div className="flex flex-wrap items-center gap-2">
        <p className="font-semibold text-ink">Semaine du lundi {formatDate(report.week_start, DAY_TZ)}</p>
        <StatusBadge map={REPORT_STATUS} status={report.status} />
      </div>
      <dl className="grid gap-3 sm:grid-cols-3">
        <Fact label="Tension à domicile" value={HOME_BP_CATEGORY[report.home_bp_category] ?? "—"} />
        <Fact label="Contrôle" value={CONTROL_STATUS[report.control_status] ?? report.control_status} />
        <Fact label="Semaine prochaine au-dessus de la cible" value={formatPercent(report.next_week_above_target_prob)} hint="probabilité estimée par le modèle" />
      </dl>
      <p className="text-sm text-ink">
        <span className="font-medium">Mesures à domicile :</span> {bp.valid_readings ?? 0} valide(s)
        {bp.simulated > 0 && <> dont <strong className="text-sim">{bp.simulated} simulée(s)</strong></>}
        {bp.mean_systolic !== undefined && ` · moyenne ${round(bp.mean_systolic)}/${round(bp.mean_diastolic)} mmHg`}
        {Array.isArray(bp.target) && ` · cible ${bp.target[0]}/${bp.target[1]}${bp.target_source === "default" ? " (générale)" : ""}`}
      </p>
      <div className="text-sm text-ink">
        <p><span className="font-medium">Bague :</span> {ring.nights_this_week ?? 0} nuit(s) enregistrée(s) cette semaine</p>
        {nights.length > 0 && <ul className="tnum mt-1 space-y-0.5 text-ink-muted">{nights.map((n) => <li key={n.key}>{n.text}</li>)}</ul>}
        {ring.flags?.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {ring.flags.map((f) => (
              <Badge key={`${f.kind}-${f.review_status}`} tone={f.kind === "early_warning" ? "ml" : "wear"}>
                {FLAG_KIND[f.kind] ?? f.kind} · {(FLAG_REVIEW[f.review_status]?.label ?? f.review_status).toLowerCase()} : {f.count}
              </Badge>
            ))}
          </div>
        )}
      </div>
      {pop && (
        <div className="text-sm text-ink">
          <p><span className="font-medium">Pouls au brassard :</span> <span className="tnum">{pop.mean_cuff_pulse} bpm, {round(pop.percentile)}e percentile</span> (même sexe, {pop.age_band} ans)</p>
          {pop.note && <p className="text-xs text-ink-subtle">{pop.note}</p>}
        </div>
      )}
      {mbp && (
        <p className="tnum rounded-xl border border-dashed border-ml/50 bg-ml-soft px-3 py-2 text-sm text-ml">
          Estimation du modèle pour le {formatDate(mbp.target_date, DAY_TZ)} : {round(mbp.systolic)}/{round(mbp.diastolic)} mmHg (ce n'est pas une mesure)
        </p>
      )}
      {report.status === "ready" ? (
        <ReviewBox label="Commentaire" maxLength={4000} conflict={ALREADY_REVIEWED} onDone={onDone} actions={[
          ["Marquer comme examiné", (comment) => reviewWeeklyReport(report.id, { doctor_comment: comment })],
        ]} />
      ) : (
        <p className="text-sm text-ink-muted">Examiné {formatDateTime(report.reviewed_at, timeZone)}{report.doctor_comment ? ` · « ${report.doctor_comment} »` : ""}</p>
      )}
    </li>
  );
}

export function WeeklyReports({ patientId, timeZone }) {
  const reports = useResource((signal) => listWeeklyReports(patientId, { signal }), `wr:${patientId}`);
  return (
    <div className="space-y-4">
      <Notice />
      <RingSection state={reports} what="les rapports hebdomadaires">
        {(list) => list.length === 0 ? <EmptyState icon="clipboard" title="Aucun rapport hebdomadaire" /> : (
          <ul className="space-y-3">
            {list.map((r) => <ReportItem key={r.id} report={r} timeZone={timeZone} onDone={reports.reload} />)}
          </ul>
        )}
      </RingSection>
    </div>
  );
}

// ---------------------------------------------------------------- personal bands
function BandItem({ band, onDone }) {
  const [edit, setEdit] = useState(null);  // { low, high } as typed
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const meta = WEARABLE_METRIC[band.metric];
  const low = Number(edit?.low);
  const high = Number(edit?.high);
  const editOk = edit !== null && edit.low.trim() !== "" && edit.high.trim() !== ""
    && Number.isFinite(low) && Number.isFinite(high) && low < high;

  async function run(send) {
    setBusy(true);
    setError(null);
    try {
      await send();
      onDone();
    } catch (e) {
      setError(e.code === "invalid_transition" ? "Cette plage n'est plus en proposition." : "Action impossible. Réessayez.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className={`space-y-2 rounded-xl border p-4 ${band.status === "proposed" ? "border-wear/40 bg-wear-soft/40" : "border-line"}`}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium text-ink">{meta?.label ?? band.metric}</span>
        <span className="text-sm text-ink-muted">{BAND_STATISTIC[band.statistic] ?? band.statistic}</span>
        <StatusBadge map={BAND_STATUS} status={band.status} />
      </div>
      <p className="tnum text-lg font-semibold text-ink">{band.low} – {band.high} <span className="text-sm font-normal text-ink-muted">{meta?.unit}</span></p>
      <p className="text-xs text-ink-subtle">
        {BAND_BASIS[band.basis] ?? band.basis}
        {band.proposed_model_version ? ` · modèle ${band.proposed_model_version}` : ""}
        {band.effective_from ? ` · depuis le ${formatDate(band.effective_from, DAY_TZ)}` : ""}
      </p>
      {band.status === "proposed" && (edit ? (
        <div className="space-y-2">
          <div className="grid grid-cols-2 gap-3 sm:w-80">
            <label className="block text-sm font-medium text-ink">Limite basse{meta ? ` (${meta.unit})` : ""}
              <input type="number" step="any" className={input} value={edit.low} onChange={(e) => setEdit({ ...edit, low: e.target.value })} />
            </label>
            <label className="block text-sm font-medium text-ink">Limite haute{meta ? ` (${meta.unit})` : ""}
              <input type="number" step="any" className={input} value={edit.high} onChange={(e) => setEdit({ ...edit, high: e.target.value })} />
            </label>
          </div>
          {!editOk && <p className="text-xs text-ink-muted">La valeur basse doit être inférieure à la valeur haute.</p>}
          <div className="flex flex-wrap gap-2">
            <Button disabled={busy || !editOk} onClick={() => run(() => approveBand(band.id, { low, high }))}>Approuver cette plage</Button>
            <Button variant="ghost" disabled={busy} onClick={() => setEdit(null)}>Annuler</Button>
          </div>
        </div>
      ) : (
        <div className="flex flex-wrap gap-2">
          <Button disabled={busy} onClick={() => run(() => approveBand(band.id))}>Approuver</Button>
          <Button variant="secondary" disabled={busy} onClick={() => setEdit({ low: String(band.low), high: String(band.high) })}>Modifier puis approuver</Button>
          <Button variant="ghost" disabled={busy} onClick={() => run(() => rejectBand(band.id))}>Refuser</Button>
        </div>
      ))}
      {error && <p role="alert" className="text-sm text-danger">{error}</p>}
    </li>
  );
}

export function PersonalBands({ patientId }) {
  const bands = useResource((signal) => listBands(patientId, { signal }), `bands:${patientId}`);
  return (
    <div className="space-y-4">
      <Notice />
      <p className="text-sm text-ink-muted">Le modèle propose des plages personnelles ; seule votre approbation les active. Elles ne servent qu'aux signaux du bracelet.</p>
      <RingSection state={bands} what="les plages personnelles">
        {(list) => list.length === 0 ? <EmptyState icon="watch" title="Aucune plage personnelle" /> : (
          <ul className="space-y-3">
            {list.map((b) => <BandItem key={b.id} band={b} onDone={bands.reload} />)}
          </ul>
        )}
      </RingSection>
    </div>
  );
}
