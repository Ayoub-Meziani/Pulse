import { listDevices, listWearableSamples } from "../../api/patient";
import { useResource } from "../../lib/useResource";
import { DEVICE_TYPE, formatDateTime, WEARABLE_METRIC } from "../../lib/format";
import Badge from "../ui/Badge";
import { EmptyState, Section } from "../ui/States";

function Stat({ metric, samples, timeZone }) {
  const rows = samples.filter((s) => s.metric === metric);
  if (rows.length === 0) return null;
  const meta = WEARABLE_METRIC[metric];
  const latest = rows[0];
  const values = rows.map((s) => s.value);
  const simulated = rows.some((s) => s.source === "simulated");
  return (
    <div className="rounded-xl border border-wear/25 bg-wear-soft/60 p-4">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-medium text-wear">{meta.label}</p>
        {simulated && <Badge tone="sim" icon="flask">Simulé</Badge>}
      </div>
      <p className="tnum mt-2 text-2xl font-semibold text-ink">
        {latest.value} <span className="text-sm font-normal text-ink-muted">{meta.unit}</span>
      </p>
      <p className="mt-1 text-xs text-ink-muted">
        Dernière valeur {formatDateTime(latest.measured_at, timeZone)} · {rows.length} valeurs, de {Math.min(...values)} à {Math.max(...values)} {meta.unit}
      </p>
    </div>
  );
}

/**
 * Optional wearable data of one patient. Never blood pressure, never an alert or emergency input: shown in
 * its own colour family, away from the blood-pressure chart.
 */
export default function WearablePanel({ patientId, timeZone, emptyText }) {
  const devices = useResource((signal) => listDevices(patientId, { signal }), `dev:${patientId}`);
  const samples = useResource((signal) => listWearableSamples(patientId, { limit: 500, signal }), `ws:${patientId}`);

  return (
    <Section state={devices} what="les appareils">
      {(list) => list.length === 0 ? (
        <EmptyState icon="watch" title="Aucun bracelet ni appareil connecté">
          {emptyText ?? "Le suivi repose sur les mesures de tension saisies. Un bracelet est facultatif."}
        </EmptyState>
      ) : (
        <div className="space-y-4">
          <ul className="flex flex-wrap gap-2">
            {list.map((d) => (
              <li key={d.id} className="inline-flex items-center gap-2 rounded-xl border border-line px-3 py-2 text-sm">
                <span className="font-medium text-ink">{d.label ?? DEVICE_TYPE[d.device_type]}</span>
                <span className="text-ink-muted">{DEVICE_TYPE[d.device_type]}</span>
                {d.is_simulated && <Badge tone="sim" icon="flask">Simulé</Badge>}
              </li>
            ))}
          </ul>
          <Section state={samples} what="les données du bracelet">
            {(rows) => rows.length === 0 ? (
              <p className="text-sm text-ink-muted">Aucune donnée reçue de cet appareil.</p>
            ) : (
              <div className="grid gap-3 sm:grid-cols-2">
                {Object.keys(WEARABLE_METRIC).map((m) => <Stat key={m} metric={m} samples={rows} timeZone={timeZone} />)}
              </div>
            )}
          </Section>
          <p className="text-xs text-ink-muted">
            Données indicatives : la fréquence cardiaque et la SpO₂ ne sont pas des mesures de tension et ne
            déclenchent aucune alerte ni consigne d'urgence.
          </p>
        </div>
      )}
    </Section>
  );
}
