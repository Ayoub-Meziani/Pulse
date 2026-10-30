# PULSE database schema (actual)

**Scope:**
- Source of truth: the 6 files in `supabase/migrations/` (M1–M6). History, cloud status and per-migration notes: [MIGRATIONS.md](MIGRATIONS.md).
- Everything below was read from the local catalog (Postgres 17.11, port 55322) on 30 Oct 2026, with M1–M6 applied.
- **Cloud project `pulse`:** M1–M6 applied. Demo data loaded (30 Oct).
- Field meanings, units and the validation policy are in [DATA_DICTIONARY.md](DATA_DICTIONARY.md). The per-role permissions matrix is in [API_CONTRACT.md](API_CONTRACT.md). Note: the team decided that the frontend calls FastAPI only; the matrix describes what the database itself allows.

## 1. ER diagram
```mermaid
erDiagram
    AUTH_USERS ||--|| PROFILES : "id (cascade)"
    PROFILES ||--o| PATIENT_PROFILES : user_id
    PROFILES ||--o{ DOCTOR_PATIENT_ASSIGNMENTS : "doctor_id / patient_id"
    PROFILES ||--o{ DEVICES : patient_id
    PROFILES ||--o{ INGESTION_BATCHES : patient_id
    DEVICES ||--o{ INGESTION_BATCHES : "device_id+patient_id"
    PROFILES ||--o{ MEASUREMENTS : patient_id
    DEVICES ||--o{ MEASUREMENTS : "device_id+patient_id"
    INGESTION_BATCHES ||--o{ MEASUREMENTS : "batch_id+patient_id"
    PROFILES ||--o{ SYMPTOM_REPORTS : patient_id
    PROFILES ||--o{ LIFESTYLE_LOGS : patient_id
    PROFILES ||--o{ MEDICATIONS : "patient_id / prescribed_by"
    MEDICATIONS ||--o{ MEDICATION_ADHERENCE_EVENTS : "medication_id+patient_id"
    PROFILES ||--o{ JOURNAL_ENTRIES : "patient_id / reviewed_by"
    PROFILES ||--o{ CARE_PLANS : "patient_id / clinician_id"
    CARE_PLANS ||--o| CARE_PLANS : supersedes_id
    PROFILES ||--o{ DOCTOR_NOTES : "patient_id / doctor_id"
    PROFILES ||--o{ ALERTS : patient_id
    MEASUREMENTS ||--o{ ALERTS : "measurement_id+patient_id"
    SYMPTOM_REPORTS ||--o{ ALERTS : "symptom_report_id+patient_id"
    PROFILES ||--o{ TRUSTED_CONTACTS : patient_id
    PROFILES ||--o{ EMERGENCY_EVENTS : patient_id
    ALERTS ||--o{ EMERGENCY_EVENTS : alert_id
    ALERTS ||--o{ ALERT_MEASUREMENTS : "alert_id+patient_id"
    MEASUREMENTS ||--o{ ALERT_MEASUREMENTS : "measurement_id+patient_id"
    PROFILES ||--o{ ML_PREDICTIONS : patient_id
    PROFILES ||--o{ BODY_MEASUREMENTS : patient_id
    PROFILES ||--o{ WEARABLE_SAMPLES : patient_id
    DEVICES ||--o{ WEARABLE_SAMPLES : "device_id+patient_id"
```

`audit_log` has no foreign keys. It stores `table_name` + `row_id` + `actor`.

**Composite same-patient foreign keys.** Several links are on two columns, `(child_id, patient_id)` → `(id, patient_id)`. This makes it impossible to attach another patient's device, batch, measurement, symptom report or medication. These links are marked `+patient_id` in the diagram.

## 2. Tables, keys and indexes
| table | PK | foreign keys (on delete) | unique / partial indexes | other indexes |
|---|---|---|---|---|
| profiles | id | id → auth.users (cascade) | – | – |
| patient_profiles | user_id | user_id → profiles (cascade); regular_doctor_id → profiles (set null) | – | – |
| doctor_patient_assignments | id | doctor_id, patient_id → profiles (cascade) | `assignments_one_active` (doctor_id, patient_id) where active | (patient_id) where active |
| devices | id | patient_id → profiles (cascade) | (id, patient_id); `devices_external_id` (patient_id, external_device_id) where not null | – |
| ingestion_batches | id | patient_id (cascade); (device_id, patient_id) → devices; created_by (set null) | (id, patient_id); `batches_file_once` (patient_id, file_sha256) | – |
| measurements | id | patient_id (cascade); (device_id, patient_id) → devices; (ingestion_batch_id, patient_id) → batches; created_by (set null) | (id, patient_id); `measurements_device_reading` (device_id, external_id) where not null | (patient_id, measured_at desc) |
| symptom_reports | id | patient_id (cascade) | (id, patient_id) | (patient_id, reported_at desc) |
| lifestyle_logs | id | patient_id (cascade) | – | (patient_id, started_at desc) |
| medications | id | patient_id (cascade); prescribed_by → profiles (restrict) | (id, patient_id) | – |
| medication_adherence_events | id | (medication_id, patient_id) → medications (cascade) | – | (patient_id, reported_at desc) |
| journal_entries | id | patient_id (cascade); reviewed_by (set null) | – | (patient_id, created_at desc) |
| care_plans | id | patient_id (cascade); clinician_id (restrict); supersedes_id → care_plans (set null) | `care_plans_one_active` (patient_id) where active | – |
| doctor_notes | id | patient_id (cascade); doctor_id (restrict) | – | (patient_id, created_at desc) |
| alerts | id | patient_id (cascade); (measurement_id, patient_id) → measurements; (symptom_report_id, patient_id) → symptom_reports; acknowledged_by/reviewed_by/resolved_by (set null) | (id, patient_id) (M3); `alerts_once_per_measurement` (measurement_id, rule_code); `alerts_once_per_symptom_report` (symptom_report_id, rule_code) | (patient_id, status, created_at desc) |
| alert_measurements (M3) | (alert_id, measurement_id) | (alert_id, patient_id) → alerts (cascade); (measurement_id, patient_id) → measurements | – | (patient_id) |
| ml_predictions (M4) | id | patient_id → profiles (cascade) | (patient_id, target_date, model_version) | (patient_id, target_date desc) |
| body_measurements (M6) | id | patient_id → profiles (cascade); created_by (set null) | – | (patient_id, measured_at desc) |
| wearable_samples (M6) | id | patient_id → profiles (cascade); (device_id, patient_id) → devices | `wearable_samples_device_sample` (device_id, external_id) where not null | (patient_id, metric, measured_at desc) |
| trusted_contacts | id | patient_id (cascade) | – | – |
| emergency_events | id | patient_id (cascade); alert_id → alerts (set null) | – | (patient_id, started_at desc) |
| audit_log | id | – | – | (table_name, row_id) |

**Totals (M1–M6):** 21 tables, 41 foreign keys and 50 indexes, including primary keys.

**Columns added after M1** (full list per table in the export):
| table.column | type | migration | filled by |
|---|---|---|---|
| alerts.persistent | boolean not null default false | M3 | rule engine (backend) |
| measurements.rested_5_min | boolean, null = not asked | M3 | patient |
| patient_profiles.birth_year | smallint 1900–2100, nullable | M5 | patient |
| patient_profiles.sex, smoking_status, condition_codes, bread_portions_per_day, adds_salt_at_table, salty_processed_food | see DATA_DICTIONARY | M6 | patient |
| profiles.preferred_language | fr / ar | M6 | patient |
| lifestyle_logs.category adds `fasting` | – | M6 | patient |
| alerts.resolution_note | text (since M1) | M1 | doctor, when resolving (set with resolved_at / resolved_by) |

## 3. Check constraints (summary)
There are 108 `CHECK` constraints in total. The largest groups are measurements (18), lifestyle_logs (18), care_plans (7), and ingestion_batches and alerts (6 each). They enforce:
- **Controlled vocabularies:** role, source, provenance, method, status, alert class, symptom codes, lifestyle category, and so on.
- **Units:** `unit = 'mmHg'`.
- **Storage bounds:** systolic 1–400, diastolic 1–300.
- **Labelling rules:**
  - A row with `source = 'simulated'` must have `provenance = 'simulated'`.
  - A row with method `wearable_estimate` must have `provenance = 'estimated'`.
- **Category-specific lifestyle columns:** for example, `sodium_mg` requires `sodium_basis`.
- **Time ordering:** for example, `ended_at ≥ started_at`, and lifestyle entries last at most 24 h.
- **Consent rule:** location requires `location_shared_with_consent`.

Physiological plausibility is **not** a check constraint. It lives in the validation trigger, which stores flagged rows instead of refusing them.

## 4. Triggers and functions
All helper functions live in the `private` schema, which the API does not expose. They are `security definer` with `search_path=''`.

| trigger | table | timing | function / purpose |
|---|---|---|---|
| on_auth_user_created | auth.users | after insert | `private.handle_new_user`: creates the profile, always with role `patient` |
| measurements_validate | measurements | before insert/update | `private.validate_measurement`: policy `pulse-v1` sets `validation_status`, `quality_flags`, `validation_policy_version` and `created_by` |
| *_roles | assignments, patient_profiles, medications, care_plans, doctor_notes | before insert/update | `private.enforce_roles`: checks the referenced profile has the correct role (doctor/patient) |
| *_audit | profiles, assignments, medications, care_plans, doctor_notes, alerts | after insert/update/delete | `private.audit`: writes a row to `audit_log` |
| *_touch | profiles, patient_profiles, assignments, lifestyle_logs, medications, care_plans, doctor_notes | before update | `private.touch_updated_at`: refreshes `updated_at` |

**RLS helpers:** `current_app_role()`, `is_assigned_doctor(patient)`, `is_my_doctor(doctor)`, `can_read_patient(patient)`. Timezone validation: `is_valid_tz()`.

## 5. Access control (RLS + grants)
- RLS is enabled on all 21 tables, with 46 policies. Every policy targets the `authenticated` role.
- `anon` has **0** table grants (M3, M4 and M6 tables revoke explicitly, because the live project's default privileges would grant ALL).
- The service role and the privileged DB connection bypass RLS. They are used by FastAPI, the seed, the import CLI and the ML job.

| grant to `authenticated` | tables |
|---|---|
| SELECT only | profiles\*, doctor_patient_assignments, ingestion_batches, alerts, alert_measurements, wearable_samples, ml_predictions (doctor/admin policy), audit_log (admin policy) |
| SELECT, INSERT | measurements (policy: own row, `source='manual'`, not simulated, no batch), symptom_reports, journal_entries\*\*, medication_adherence_events, body_measurements (patient `patient_reported` / assigned doctor `clinician`) |
| SELECT, INSERT, UPDATE | patient_profiles, devices, medications, care_plans, doctor_notes, emergency_events |
| SELECT, INSERT, UPDATE, DELETE | lifestyle_logs, trusted_contacts |

\* On `profiles`, users can UPDATE only `display_name`, `timezone` and `preferred_language` (a column grant), so nobody can change their own role.
\*\* On `journal_entries`, UPDATE is limited to the review columns, and only an assigned doctor may use it.

There is no UPDATE or DELETE grant on measurements, symptom reports, adherence events, alerts or assignments. These tables are append-only for app users.

`doctor_notes` (M3): readable by assigned doctors and admin only; patients receive `advice` and `follow_up_at` through the API.

The full matrix of who can do what is in [API_CONTRACT.md](API_CONTRACT.md).

## 5b. Authentication structure
- **Sign-in:** Supabase Auth (GoTrue) with email and password. `auth.users` is managed by Supabase and PULSE does not alter it. Each user's id (`sub` in the access token) equals `profiles.id`.
- **Sign-up:** the trigger `on_auth_user_created` → `private.handle_new_user()` inserts the user's `profiles` row with role `patient`. Sign-up metadata cannot set the role.
- **Roles:** `profiles.role` is `patient`, `doctor` or `admin`. Only the service role or SQL run by the project owner can change it.
  - RLS reads the role through `private.current_app_role()`.
  - Doctors' access comes from active rows in `doctor_patient_assignments`.
- **Not configured:** email confirmation, OAuth providers, MFA and custom JWT claims. The team should decide on these.

## Schema-only export
[export/pulse_schema.sql](export/pulse_schema.sql) contains:
- 21 tables, all keys and indexes, check constraints, the 10 `private` functions, triggers, the 46 RLS policies and the grants (M1–M6)
- the auth trigger

It has **no data and no credentials**. Generated with `pg_dump --schema-only --no-owner --schema=public --schema=private`.

Use it for review. To create the schema, apply `supabase/migrations/` instead.

## 6. Connecting the backend safely
1. **FastAPI is the only application API** (team decision A2). It connects with a privileged role (`PULSE_DATABASE_URL`), which bypasses RLS, so every query must filter by the caller's patient id or active assignment. RLS stays as defence in depth.
2. **Keep the service role and DB credentials server-side** (FastAPI, seed, import CLI, ML job). Never in the frontend, the repo or logs.
3. **The ML job** (`ml/pulse_ml/predict.py`) reads `valid` measurements of assigned patients and writes `ml_predictions` only.
4. **Migrations are append-only.** Add a new file; never edit an applied one.
   - Apply with `npx supabase@2.122.0 link --project-ref <ref>` then `db push`, run by the agreed owner.
   - Every new table must enable RLS, revoke `anon`, and grant only what it needs. Supabase's default grants are wide open.
5. **Seed `pulse` only after public sign-up is off.** The demo password comes from `PULSE_DEMO_PASSWORD`, and `seed.sql` is git-ignored. Never run `db reset` against a linked or remote project; use `--local`.
6. **Keep health values out of logs.** Do not echo request bodies in logs or error messages. Map Postgres error codes (42501, 23514, 23505, 23503) to user messages as listed in API_CONTRACT.md.
7. **Treat the database status as authoritative.** Show `validation_status`/`quality_flags` from the database. Never compute them in the client, and never send them.
