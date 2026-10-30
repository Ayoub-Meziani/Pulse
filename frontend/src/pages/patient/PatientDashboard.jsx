import { useEffect, useState } from "react";
import { Link } from "react-router";
import { useAuth } from "../../auth/AuthContext";
import { getSummary, listActiveAlerts, listMeasurements } from "../../api/patient";
import AlertCard from "../../components/alerts/AlertCard";
import StatCard from "../../components/cards/StatCard";
import BloodPressureChart from "../../components/charts/BloodPressureChart";
import ProvenanceBadge from "../../components/ProvenanceBadge";
import { ALERT_LEVEL, ALERT_STATUS, formatDateTime, round, SOURCE, TREND } from "../../lib/format";

const IDLE = { status: "loading", data: null };

// One section's request: loading -> ok | error. A failed section does not hide the others.
function useSection(load, patientId) {
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState({ key: null, status: "loading", data: null });
  const key = `${patientId}:${attempt}`;
  useEffect(() => {
    const controller = new AbortController();
    load(patientId, { signal: controller.signal })
      .then((data) => setResult({ key, status: "ok", data }))
      .catch((error) => {
        if (error?.name !== "AbortError") setResult({ key, status: "error", data: null });
      });
    return () => controller.abort();
  }, [load, patientId, key]);
  // An answer for an older request (or none yet) counts as loading.
  return [result.key === key ? result : IDLE, () => setAttempt((n) => n + 1)];
}

function SectionError({ what, onRetry }) {
  return (
    <div role="alert" className="rounded-xl bg-red-50 px-5 py-4 text-sm text-red-800">
      Impossible de charger {what} pour le moment.{" "}
      <button type="button" onClick={onRetry} className="font-medium underline">Réessayer</button>
    </div>
  );
}

function averages(s, days) {
  const sys = round(s[`avg_systolic_${days}d`]);
  const dia = round(s[`avg_diastolic_${days}d`]);
  return sys === null || dia === null ? "-- / --" : `${sys} / ${dia}`;
}

function lastReadingText(readings, latest, tz) {
  if (readings.status === "loading") return "Chargement…";
  if (readings.status === "error") return "Indisponible.";
  if (!latest) return "Aucune mesure enregistrée.";
  const origin = latest.provenance === "simulated" ? "SIMULÉE" : SOURCE[latest.source] ?? latest.source;
  const review = latest.validation_status === "needs_review" ? " · à vérifier" : "";
  return `${formatDateTime(latest.measured_at, tz)} · ${origin}${review}`;
}

function sevenDayText(summary) {
  if (summary.status === "loading") return "Chargement…";
  if (summary.status === "error") return "Indisponible.";
  return `${summary.data.count_7d} mesure(s) · tendance : ${TREND[summary.data.trend] ?? summary.data.trend}`;
}

function targetText(summary) {
  if (summary.status === "loading") return "Chargement…";
  if (summary.status === "error") return "Indisponible.";
  const t = summary.data.target;
  return `Objectif : ${t.systolic} / ${t.diastolic} mmHg${t.is_default ? " (par défaut)" : ""}`;
}

export default function PatientDashboard() {
  const { user } = useAuth();
  const [readings, retryReadings] = useSection(listMeasurements, user.id);
  const [summary, retrySummary] = useSection(getSummary, user.id);
  const [alerts, retryAlerts] = useSection(listActiveAlerts, user.id);
  const tz = user.timezone;

  const list = readings.data ?? [];
  const latest = list[0];

  return (
    <div className="space-y-8">
      <section>
        <p className="text-sm font-medium text-blue-700">ESPACE PATIENT</p>
        <h1 className="mt-2 text-3xl font-bold tracking-tight text-slate-900">Bonjour, {user.full_name}</h1>
        <p className="mt-2 text-slate-600">
          Votre suivi repose sur les mesures et les symptômes que vous saisissez. Un bracelet connecté est facultatif.
        </p>
        <div className="mt-5 flex flex-wrap gap-3">
          <Link to="/patient/mesure" className="rounded-lg bg-blue-700 px-5 py-2.5 font-semibold text-white">
            Nouvelle mesure
          </Link>
          <Link to="/patient/mesure?mode=symptomes" className="rounded-lg border border-slate-300 bg-white px-5 py-2.5 font-semibold text-slate-800">
            Signaler des symptômes
          </Link>
          <Link to="/patient/urgence" className="rounded-lg bg-red-600 px-5 py-2.5 font-semibold text-white">
            Urgence
          </Link>
        </div>
      </section>

      <section className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3" aria-label="Résumé">
        <StatCard
          title="Dernière mesure"
          value={latest ? `${latest.systolic} / ${latest.diastolic}` : "-- / --"}
          unit="mmHg"
          description={lastReadingText(readings, latest, tz)}
        />
        <StatCard
          title="Moyenne sur 7 jours"
          value={summary.data ? averages(summary.data, 7) : "-- / --"}
          unit="mmHg"
          description={sevenDayText(summary)}
        />
        <StatCard
          title="Moyenne sur 30 jours"
          value={summary.data ? averages(summary.data, 30) : "-- / --"}
          unit="mmHg"
          description={targetText(summary)}
        />
      </section>
      {summary.status === "error" && <SectionError what="le résumé" onRetry={retrySummary} />}

      <section>
        <div className="mb-4">
          <h2 className="text-xl font-bold text-slate-900">Alertes</h2>
          <p className="mt-1 text-sm text-slate-500">Alertes en cours sur votre suivi.</p>
        </div>
        {alerts.status === "loading" && <p className="text-sm text-slate-500" role="status">Chargement…</p>}
        {alerts.status === "error" && <SectionError what="les alertes" onRetry={retryAlerts} />}
        {alerts.status === "ok" && alerts.data.length === 0 && (
          <div className="rounded-xl bg-slate-50 px-5 py-6 text-center text-sm text-slate-500">
            Aucune alerte active.
          </div>
        )}
        {alerts.status === "ok" && alerts.data.length > 0 && (
          <div className="space-y-3">
            {alerts.data.map((a) => {
              const level = ALERT_LEVEL[a.level] ?? { title: a.level, variant: "info" };
              return (
                <AlertCard
                  key={a.id}
                  title={`${level.title} · ${ALERT_STATUS[a.status] ?? a.status}`}
                  message={`${a.reason} ${a.next_step}`.trim()}
                  variant={level.variant}
                />
              );
            })}
          </div>
        )}
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
        {readings.status === "loading" && <p className="text-sm text-slate-500" role="status">Chargement du graphique…</p>}
        {readings.status === "error" && <SectionError what="le graphique" onRetry={retryReadings} />}
        {readings.status === "ok" && <BloodPressureChart readings={list} timeZone={tz} />}
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
        <h2 className="text-lg font-semibold text-slate-900">Historique des mesures</h2>
        <p className="mt-1 text-sm text-slate-500">Vos mesures les plus récentes, avec leur origine.</p>

        {readings.status === "loading" && <p className="mt-6 text-sm text-slate-500" role="status">Chargement…</p>}
        {readings.status === "error" && <div className="mt-6"><SectionError what="l'historique" onRetry={retryReadings} /></div>}
        {readings.status === "ok" && list.length === 0 && (
          <div className="mt-6 rounded-xl bg-slate-50 px-5 py-10 text-center">
            <p className="text-sm text-slate-500">Aucune donnée disponible.</p>
          </div>
        )}
        {readings.status === "ok" && list.length > 0 && (
          <div className="mt-6 overflow-x-auto">
            <table className="w-full min-w-[34rem] text-left text-sm">
              <thead className="text-slate-500">
                <tr>
                  <th className="pb-2 pr-4 font-medium">Date</th>
                  <th className="pb-2 pr-4 font-medium">Tension</th>
                  <th className="pb-2 pr-4 font-medium">Pouls</th>
                  <th className="pb-2 pr-4 font-medium">Origine</th>
                  <th className="pb-2 font-medium">Contrôle</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-900">
                {list.slice(0, 20).map((r) => (
                  <tr key={r.id}>
                    <td className="py-2 pr-4">{formatDateTime(r.measured_at, tz)}</td>
                    <td className="py-2 pr-4 font-medium">{r.systolic} / {r.diastolic} mmHg</td>
                    <td className="py-2 pr-4">{r.pulse ?? "—"}</td>
                    <td className="py-2 pr-4">
                      <ProvenanceBadge provenance={r.provenance} />{" "}
                      <span className="text-slate-500">{SOURCE[r.source] ?? r.source}</span>
                    </td>
                    <td className="py-2">{r.validation_status === "needs_review" ? "À vérifier" : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
