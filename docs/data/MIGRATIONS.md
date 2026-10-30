# PULSE migration notes

One migration history, in `supabase/migrations/` on branch `AI`. Append-only: never edit or recreate an applied file; every change is a new file listed here.
Cloud project: `pulse` (ref `nfmfdhpxipdndggxtqho`).
**Rule:** schema changes reach the cloud only after backend review (`supabase db push`, run by the data/AI developer).

## Status
| # | File | What | Local | Cloud | Backend must update? |
|---|---|---|---|---|---|
| M1 | `20261029120000_core_schema.sql` | 17 tables, validation trigger `pulse-v1`, audit triggers, role checks, auth sign-up trigger | applied | applied 30 Oct | baseline |
| M2 | `20261029120100_access_policies.sql` | RLS on every table, `anon` gets nothing, per-role write policies, column grants | applied | applied 30 Oct | baseline |
| M3 | `20261030120000_backend_alignment.sql` | contract §3.1 items 1, 2, 4–7 (below) | applied | **applied 30 Oct** (approved by the data/AI owner before the backend review rule was agreed) | yes: alert episodes, rested_5_min, empty symptoms, doctor_notes read path |
| M4 | `20261030120100_ml_predictions.sql` | `ml_predictions` table, doctor/admin read only | applied | **applied 30 Oct** (same as M3) | endpoint 24 reads it |
| M5 | `20261030130000_patient_birth_year.sql` | `patient_profiles.birth_year` | applied | applied 30 Oct (with M6, on the data/AI owner's decision; see below) | profile schemas may expose `birth_year` |
| M6 | `20261030140000_algerian_factors_wearables.sql` | Algerian risk-factor fields, fasting logs, `body_measurements`, `wearable_samples` | applied | applied 30 Oct (same) | new optional fields and two read-only tables; nothing existing changes |

**Note for the backend:** the data/AI owner chose to apply M5 and M6 to the cloud before your review, so the demo data could include them. Every change is additive (new nullable columns, a widened category list, two new tables). No existing column, constraint meaning or policy changed for current API behaviour. If you want something reverted, it will be a new migration (M7), never an edit.

Check any environment with `npx supabase@2.122.0 migration list --linked` (cloud) or `--local`.

## M3 `backend_alignment`: details
| Item | Change | Behaviour |
|---|---|---|
| 1 | `alerts.alert_class` adds `above_target_trend` | trend alerts (R-TRD-1) have their own class |
| 2 | `alerts.persistent boolean not null default false` | an episode that stays open across readings (R-SEV-2, trend) |
| 4 | new table `alert_measurements (alert_id, measurement_id, patient_id, attached_at)`, PK (alert_id, measurement_id); same-patient composite FKs to `alerts (id, patient_id)` and `measurements (id, patient_id)`; new unique key `alerts (id, patient_id)` | the recheck readings of one episode (R-SEV-2 / R-SEV-3 "attach"); a reading of another patient is refused (23503) |
| 5 | `measurements.rested_5_min boolean` (null = not asked) | MeasurementIn field |
| 6 | `symptom_reports.symptoms` may be empty | "none of these" answers are stored |
| 7 | `doctor_notes_read` policy: assigned doctors and admin only | patients no longer read notes directly; the API returns `advice` and `follow_up_at` only |
| – | new tables: `REVOKE ALL FROM anon, authenticated`, then `GRANT SELECT TO authenticated` + RLS | the live project's default privileges would otherwise grant ALL |

Already present before M3: `alerts.resolution_note` (text, set with `resolved_at`/`resolved_by` when the doctor resolves). Contract item 3 needed no change.

### Repeat-reading and escalation behaviour (how the backend uses M3)
| Rule (backend) | Database write |
|---|---|
| R-SEV-1 severe reading | `insert alerts` (alert_class `severely_high`, `measurement_id`, rule_code `R-SEV-1`) |
| R-SEV-2 recheck still severe | `insert alert_measurements` (recheck reading) + `update alerts set persistent = true` |
| R-SEV-3 recheck below severe | `insert alert_measurements`; alert stays open for the doctor |
| R-EMG-1 red flag within 1 h of a severe alert ("raise") | `update alerts set alert_class = 'possible_emergency'` (+ `symptom_report_id` if empty) |
| R-TGT-1 / R-TRD-1 attach to the open notice / trend | `insert alert_measurements` |
| acknowledge / review / resolve | `update alerts set status, *_at, *_by, resolution_note` |

Every insert/update on `alerts` is copied to `audit_log` (old and new row, actor), which gives the escalation history; no separate events table is needed. "One active notice/trend per patient" is enforced by the backend, not by a DB constraint.
Expected class mapping: emergency → `possible_emergency`, severe → `severely_high`, notice → `above_target`, trend → `above_target_trend`. The same rule code fires at most once per measurement and once per symptom report (unique indexes).

## M4 `ml_predictions`
Contract §3.1 shape. Extra CHECKs: predicted values present **iff** `status = 'ok'`; interval low ≤ high. Index `(patient_id, target_date desc)`. Read: assigned doctor or admin; no patient read; no write grant (batch job uses the privileged connection). Output contract: [`ml/README.md`](../../ml/README.md).

## M5 `patient_birth_year`
`patient_profiles.birth_year smallint check (birth_year between 1900 and 2100)`, nullable. Year only (data minimisation). Patient fills it through the existing patient_profiles grant and policies; no new grant. Reason: age is the strongest hypertension factor in the Algerian STEPS 2016–2017 analysis (`PULSE_DATA_LOGIC.pdf` §6). Not used by the ML MVP.
Applied to the cloud on 30 Oct together with M6.

## M6 `algerian_factors_wearables`
Every factor in `PULSE_DATA_LOGIC.pdf` §6 and the wearable data in §5 now has a place in the database.

| Factor / data | Where | Filled by |
|---|---|---|
| Sex | `patient_profiles.sex` female / male | patient |
| Age | `patient_profiles.birth_year` (M5) | patient |
| Smoking | `patient_profiles.smoking_status` never / former / current | patient |
| Diabetes, cholesterol, kidney / heart disease, stroke, pregnancy | `patient_profiles.condition_codes` (controlled list; `relevant_conditions` stays free text for the emergency card) | patient (doctor confirms in the API) |
| Salt / bread | `patient_profiles.bread_portions_per_day` (0–20), `adds_salt_at_table`, `salty_processed_food` (never / rarely / sometimes / often / always, STEPS-style) | patient |
| Weight, height, waist (BMI, abdominal obesity) | new table `body_measurements` (`weight_kg`, `height_cm`, `waist_cm`, `source`) | patient (`patient_reported`) or assigned doctor (`clinician`) |
| Ramadan / fasting days | `lifestyle_logs.category = 'fasting'` (started_at = start of the fast, ended_at = iftar) | patient |
| Language | `profiles.preferred_language` fr / ar (column grant: the user may update it) | patient |
| Ring / bracelet / watch | new table `wearable_samples`: `metric` heart_rate (bpm) / hrv_rmssd (ms) / spo2 (percent) / skin_temperature (celsius), `value`, `measured_at`, `source`, `external_id`; same-patient device FK; unit and plausible range enforced per metric; dedup per (device_id, external_id) | device sync / import (backend only) |

Still outside the database (by design): the emergency number (backend config), physical activity / sleep / stress (already in `lifestyle_logs`), medication + adherence (already present), and a ring blood-pressure estimate (goes to `measurements` with provenance `estimated`, auto `needs_review`).

**Access:** `body_measurements`: read by self, assigned doctor or admin; insert by the patient (`patient_reported`) or an assigned doctor (`clinician`); no update or delete. `wearable_samples`: read the same way; no client writes. Both revoke `anon`.
BMI is computed when read (`weight_kg / (height_cm/100)^2`, using the latest height). Abdominal obesity uses the STEPS cut-offs: waist > 94 cm for men, > 80 cm for women.

## How to add a migration
1. New file `supabase/migrations/<UTC timestamp>_<name>.sql`. Never edit an applied one.
2. New tables: `revoke all ... from anon, authenticated`, enable RLS, grant only what is needed.
3. `npx supabase@2.122.0 db reset --local`, then `python -m pytest`.
4. Add a row above, update `DATA_SCHEMA.md` / `DATA_DICTIONARY.md` and the export (`docs/data/export/pulse_schema.sql`).
5. Push to the branch, backend review, then `db push --linked`.
