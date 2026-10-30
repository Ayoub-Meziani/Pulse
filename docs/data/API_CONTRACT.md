# Data-layer contract (for backend + frontend)

PULSE uses Supabase: every table in `public` is available through the auto-generated REST API (`/rest/v1/<table>`) and `supabase-js`, protected by row-level security. Auth = Supabase Auth (email/password); the JWT's `sub` is the profile id.

Analytics, alert-rule and forecast endpoints are **not built yet** (next phases). This file covers storage and ingestion.

## Who can do what
| table | patient (own rows) | doctor (actively assigned patients) | admin | service role |
|---|---|---|---|---|
| profiles | read; update `display_name`, `timezone` | read assigned patients + self | read all | all |
| patient_profiles | read, insert, update | read | read | all |
| doctor_patient_assignments | read own | read own | read | **only writer** |
| devices | read, insert, update (not simulator) | read | read | all |
| measurements | read; insert **manual only** | read | read | all (imports, device sync, seed) |
| symptom_reports | read; insert (patient_reported/bystander) | read | read | all |
| lifestyle_logs | read, insert, update, delete (patient_reported) | read | read | all |
| medications | read; insert/update patient_reported | read; insert/update clinician (`prescribed_by` = self) | read | all |
| medication_adherence_events | read; insert | read | read | all |
| journal_entries | read; insert | read; update review columns | read | all |
| care_plans | read | read; insert (`clinician_id` = self), update | read | all |
| doctor_notes | read | read; insert/update own notes | read | all |
| alerts | read | read | read | **only writer** (rule engine, next phase) |
| trusted_contacts | read, insert, update, delete | read | read | all |
| emergency_events | read, insert, update | read | read | all |
| ingestion_batches | read | read | read | **only writer** |
| audit_log | – | – | read | written by triggers |
Anonymous (no login): nothing. Unassigned doctors: nothing. Enforced in the database; tested in `tests/test_db.py`.

## Record a manual measurement
`POST /rest/v1/measurements` (header `Prefer: return=representation`)
```json
{"patient_id": "<auth uid>", "source": "manual", "provenance": "measured", "method": "cuff_oscillometric",
 "systolic": 142, "diastolic": 91, "pulse": 74, "measured_at": "2026-10-29T07:45:00+01:00",
 "measured_tz": "Africa/Algiers", "body_position": "sitting", "arm": "left", "context": "before breakfast"}
```
Response includes `id`, `validation_status`, `quality_flags`, `validation_policy_version` computed by the database. Do not send `validation_status`; it is overwritten. Show `needs_review`/`invalid` flags to the user instead of hiding the reading.

## Read history
`GET /rest/v1/measurements?patient_id=eq.<id>&validation_status=neq.invalid&order=measured_at.desc&limit=100`
Always display `source`/`provenance` so simulated and estimated readings are visibly labelled.

## Other common writes
- Symptom: `POST /rest/v1/symptom_reports` `{"patient_id", "symptoms": ["chest_pain"], "onset_at"}`
- Lifestyle: `POST /rest/v1/lifestyle_logs` `{"patient_id", "category": "activity", "started_at", "ended_at", "activity_type": "walking", "intensity": "moderate"}` (sodium needs `sodium_basis`)
- Adherence: `POST /rest/v1/medication_adherence_events` `{"patient_id", "medication_id", "status": "taken", "taken_at"}`
- Care plan revision (doctor): `PATCH` old plan `status=superseded`, then `POST` new plan with `supersedes_id` (only one active plan per patient).

## Errors (PostgREST returns the Postgres code)
| code | meaning in PULSE |
|---|---|
| 42501 | not allowed (RLS / missing grant): wrong patient, forbidden source, append-only table |
| 23514 | check failed: bad enum value, unit ≠ mmHg, unlabelled simulated/estimated data, role mismatch (e.g. clinician is not a doctor), lifestyle field in wrong category |
| 23505 | duplicate: second active care plan, same device reading, same rule alert twice, file already imported |
| 23503 | reference to another patient's device/batch/measurement, or missing row |
| 22003 | number out of storage range |
Never echo request bodies (health data) into logs or error messages.

## Bulk import (server-side tool)
```
python -m pulse_data.ingest import-csv --patient <email|uuid> --file <csv> --provenance measured|estimated|simulated [--tz Africa/Algiers] [--method cuff_oscillometric] [--device <devices.id>]
```
Prints a JSON summary `{batch_id, rows_total, rows_inserted, rows_duplicate, rows_rejected, validation_status, rejections}`; exit code 1 if the file was already imported. Uses `DATABASE_URL` (default: local stack `127.0.0.1:55322`). It connects as a privileged role, so keep it server-side.
