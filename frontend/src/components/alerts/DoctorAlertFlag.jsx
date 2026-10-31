import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router";
import { listDoctorAlerts } from "../../api/doctor";
import { ringingItems, watchAlerts } from "../../lib/alertEvents";
import AlertFlag from "./AlertFlag";
import AlertSound from "./AlertSound";

/**
 * Doctor: every unresolved severe/emergency alert of assigned patients, on every page. Sound while a patient has
 * not confirmed yet. The flag goes when the doctor resolves the alert (existing workflow in the patient's record).
 */
export default function DoctorAlertFlag({ user }) {
  const [alerts, setAlerts] = useState([]);

  const refresh = useCallback(async () => {
    try { setAlerts(await listDoctorAlerts()); } catch { /* keep what is shown; the next refresh retries */ }
  }, []);

  useEffect(() => watchAlerts(refresh), [refresh]);

  return (
    <>
      <AlertSound source="doctor-flag" items={ringingItems(alerts)} />
      {alerts.length > 0 && (
        <div className="mb-6 space-y-3">
          {alerts.map((a) => (
            <AlertFlag key={a.id} alert={a} reading={a.reading} timeZone={user.timezone} who={a.patient_name}>
              <Link to={`/doctor/patients/${a.patient_id}?onglet=alertes`}
                className="inline-flex min-h-11 items-center rounded-xl bg-surface px-4 text-sm font-semibold text-brand underline">
                Ouvrir le dossier pour examiner et clôturer
              </Link>
            </AlertFlag>
          ))}
        </div>
      )}
    </>
  );
}
