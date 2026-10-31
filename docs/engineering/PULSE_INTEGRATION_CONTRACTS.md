# PULSE integration contracts (v1, proposed)

Status: **encoded** in `api/app/schemas.py` → `contract/openapi.json` on branch `feat/api-contract-v1` (`fb0acc9`, 34 operations, 49 schemas; most handlers return 501 until the database integration). OpenAPI is the machine-readable source of truth; this file is its summary. Database columns referenced here are **VERIFIED** identical on branch `AI` (`supabase/migrations/`) and the live project `pulse` (`PULSE_BRANCH_RECONCILIATION.md` §3).
Additions while encoding: `UserOut.timezone`; `PatientListItem.age`, `ProfileOut.birth_year/email/regular_doctor_name`, `EmergencyCardOut.age` (age needs `patient_profiles.birth_year`, M5 pending review); `NoteOut.doctor_name`; `TrustedContactPatch`; `SymptomResult.report` nullable; `GET /patients/{id}/emergency-events`.

---

## 1. Ownership (one owner per path)

| Path | Owner | Others |
|---|---|---|
| `api/**` (routers, services, models, `analysis/` rules and summary, `vocab.py`, jobs), `contract/`, `.github/`, root `PULSE_*.md`, `CLAUDE.md`, `IMPLEMENTATION_PLAN.md` | **Ayoub** (backend + integration, only merger) | PRs from others need Ayoub's review |
| `supabase/**` (config, migrations, seed generation), `pulse_data/**` (CSV import, simulator; renamed from `pulse_analysis/`, `rules.py` removed), `ml/**` (`pulse_ml` package, training, model card, batch predictions), `docs/data/**` | **Data/AI developer** | Backend requests schema changes by issue/PR; Ayoub approves |
| `frontend/**` (branch `feature/frontend`) | **Frontend developer** | A generated `schema.d.ts` (if adopted) is regenerated from `contract/openapi.json`, never hand-edited. `web/` (Claude's scaffold) is not a second app; see `PULSE_BRANCH_RECONCILIATION.md` §4 |

Change of ownership vs current `CLAUDE.md`: `api/app/analysis/` moves to Ayoub. Reason: the rules are the safety core of the measurement endpoint and already exist; the data/AI developer's time goes to the data layer and ML. To be reflected in `CLAUDE.md` after approval.

---

## 2. Backend ↔ Frontend (HTTP API `/api/v1`)

### 2.1 Conventions
- JSON, ids are **uuid strings**, timestamps ISO 8601 with offset (server returns UTC). Display in the patient's `timezone` (default `Africa/Algiers`).
- Auth header `Authorization: Bearer <access_token>`. On 401 `invalid_token`, call `/auth/refresh` once, then send the user to login.
- Errors always `{"error": {"code": str, "message": str, "details": any}}`. Codes: `not_authenticated` 401, `invalid_token` 401, `invalid_credentials` 401, `forbidden` 403, `not_found` 404, `conflict` 409, `duplicate_measurement` 409, `invalid_transition` 409, `validation_failed` 422 (`details: [{field, code, message}]`), `invalid_request` 422, `consent_required` 422, `invalid_reference` 422, `not_implemented` 501, `http_<status>`.
- Endpoints in this contract that are not built yet return **501 `not_implemented`** with the final response schema already in OpenAPI, so the frontend can build against types.
- Doctor list polling: every 15 s. No push notifications (non-promise kept).
- The frontend shows `measurement.source`/`provenance` and `validation_status` on every reading.

### 2.2 Shared enums
```
Role            = patient | doctor | admin
Source          = manual | device_sync | csv_import | simulated
Provenance      = measured | estimated | simulated
Method          = cuff_oscillometric | cuff_auscultatory | wearable_estimate | unknown
ValidationStatus= valid | needs_review | invalid
Level           = none | notice | trend | severe | emergency
AlertStatus     = open | acknowledged | reviewed | resolved
Symptom         = chest_pain | shortness_of_breath | back_pain | weakness | numbness | vision_change |
                  difficulty_speaking | severe_headache | confusion | dizziness | nausea | palpitations | other
RedFlag (subset)= chest_pain, shortness_of_breath, back_pain, numbness, weakness, vision_change, difficulty_speaking
```

### 2.3 Endpoints

`P` = patient (own data), `D` = assigned doctor, `—` = no auth. Phase = backend phase in the implementation plan.

| # | Method + path | Who | Phase | MVP |
|---|---|---|---|---|
| 1 | `GET /health` | — | 1 | yes (exists) |
| 2 | `POST /auth/login` | — | 2 | yes (exists, changes) |
| 3 | `POST /auth/refresh` | — | 2 | yes (new) |
| 4 | `GET /me` | any | 2 | yes (exists, changes) |
| 5 | `GET /config/emergency` | — | 5 | yes (new) |
| 6 | `GET /patients` | doctor | 3 | yes (exists) |
| 7 | `GET /patients/{id}/profile`, `PUT` | P read/write, D read | 3 | yes (new) |
| 8 | `GET/POST /patients/{id}/trusted-contacts`, `PATCH/DELETE /trusted-contacts/{cid}` | P write, D read | 3 | yes (new) |
| 9 | `GET /patients/{id}/emergency-card` | P, D | 5 | yes (new) |
| 10 | `POST /patients/{id}/measurements` | P | 4 | yes (exists, changes) |
| 11 | `GET /patients/{id}/measurements?from&to&limit&include_invalid` | P, D | 6 | yes (exists, changes) |
| 12 | `POST /patients/{id}/symptom-reports` | P | 5 | yes (exists, changes) |
| 13 | `GET /patients/{id}/alerts?status=active\|all` | P, D | 5 | yes (exists, changes) |
| 14 | `GET /alerts/{aid}` | P, D | 5 | yes (exists, changes) |
| 15 | `POST /alerts/{aid}/transition` | P (acknowledge), D (review, resolve) | 5 | yes (new) |
| 16 | `GET /patients/{id}/summary` | P, D | 6 | yes (exists, changes) |
| 17 | `GET /patients/{id}/care-plan`, `PUT` | P read, D write | 3 | read yes; PUT deferrable |
| 18 | `POST /patients/{id}/emergency-events` | P | 8 | yes (new) |
| 19 | `POST /emergency-events/{eid}/actions` | P | 8 | yes (new) |
| 20 | `PATCH /emergency-events/{eid}` | P | 8 | yes (new) |
| 21 | `GET /patients/{id}/emergency-events`, `GET /emergency-events/{eid}/report` | P, D | 8 | yes (new) |
| 22 | `GET/POST /patients/{id}/notes` | D write; P reads advice only | 8 | yes (new) |
| 23 | `GET/POST /patients/{id}/journal`, `POST /journal/{jid}/review` | P write, D review | 8 | deferrable |
| 24 | `GET /patients/{id}/predictions/latest` | D only | 7 | yes (new, ML) |
| 25 | `GET /patients/{id}/daily?days=30` | P, D | 6 | deferrable |

### 2.4 Schemas (request → response)

**Auth**
```
LoginIn      {email: str, password: str}
SessionOut   {access_token: str, refresh_token: str, expires_at: datetime, token_type: "bearer", user: UserOut}
RefreshIn    {refresh_token: str}                                   → SessionOut
UserOut      {id: uuid, role: Role, full_name: str, email: str, timezone: str}
```

**Measurements**
```
MeasurementIn {
  systolic: int, diastolic: int, pulse?: int,
  measured_at?: datetime (with offset; default server time), measured_tz?: str (IANA; default profile timezone),
  body_position?: sitting|standing|lying, arm?: left|right, rested_5_min?: bool, context?: str (≤500)
}
# source is always "manual", provenance "measured", method "unknown" for this endpoint (patients cannot post other sources)

MeasurementOut {
  id: uuid, patient_id: uuid, systolic: int, diastolic: int, pulse: int|null,
  measured_at: datetime, measured_tz: str|null, created_at: datetime,
  source: Source, provenance: Provenance, method: Method,
  body_position: str|null, arm: str|null, rested_5_min: bool|null, context: str|null,
  validation_status: ValidationStatus, quality_flags: [str], validation_policy_version: str
}
EvaluationOut {level: Level, rule_id: str|null, reason: str, next_step: str,
               requires_symptom_check: bool, recheck_after_seconds: int|null, show_emergency: bool}
AlertBrief    {id: uuid, level: Level, rule_id: str, status: AlertStatus, persistent: bool}
MeasurementResult {measurement: MeasurementOut, evaluation: EvaluationOut, alert: AlertBrief|null, trend_alert: AlertBrief|null}   # 201
```
Rules for `invalid` readings: stored (append-only), `evaluation.level = none`, `rule_id = "DATA-INVALID"`, reason lists the flags in plain words, next step "measure again". If the flags include an upper-limit breach, `requires_symptom_check = true`.

`GET .../measurements`: newest first; `limit` 1–1000 (default 200); `invalid` rows excluded unless `include_invalid=true`.

**Symptoms**
```
SymptomReportIn  {symptoms: [Symptom] (empty = none of these), measurement_id?: uuid, onset_at?: datetime, notes?: str ≤1000}
# An empty list ("none of these") is stored like any report (M3, live), so the doctor sees the answer.
SymptomReportOut {id, patient_id, symptoms, measurement_id|null, onset_at|null, reported_at, source}
SymptomResult    {report: SymptomReportOut, evaluation: EvaluationOut, alert: AlertBrief|null}   # 201
```

**Alerts**
```
AlertOut {id, patient_id, level: Level, rule_id, status: AlertStatus, persistent: bool,
          reason: str, next_step: str, measurement_id|null, symptom_report_id|null,
          created_at, updated_at, acknowledged_at|null, reviewed_at|null, resolved_at|null, resolution_note|null}
AlertDetail = AlertOut + {measurements: [MeasurementOut]}          # readings attached to this alert episode
TransitionIn {to: acknowledged|reviewed|resolved, note?: str}       → AlertOut
```
Allowed transitions: `open→acknowledged` (P or D); `open|acknowledged→reviewed` (D); `reviewed→resolved` (D; `note` required when level is severe or emergency). Anything else → 409 `invalid_transition`. "Active" = `open` or `acknowledged`.

**Summary**
```
SummaryOut {window_days: 30, timezone: str,
            count_7d, count_needs_review_7d, count_invalid_7d,
            avg_systolic_7d|null, avg_diastolic_7d|null, avg_systolic_30d|null, avg_diastolic_30d|null,
            max_systolic_7d|null, max_diastolic_7d|null, pct_above_target_7d|null, days_with_reading_7d,
            trend: rising|stable|falling|insufficient_data, last_measured_at|null,
            target: {systolic, diastolic, is_default}}
```
Averages/trend use `valid` readings only. Default target 140/90 when no active care plan.

**Doctor list** (`GET /patients`)
```
PatientListItem {id, full_name, highest_active_alert: Level|null, active_alert_count,
                 latest_measurement: MeasurementOut|null, last_measured_at|null, avg_systolic_7d|null, avg_diastolic_7d|null}
```
Sorted: emergency > severe > trend > notice > none, then oldest last reading first (unchanged).

**Profile, contacts, care plan**
```
ProfileOut/ProfileIn {full_name, timezone, relevant_conditions: [str], allergies: str|null, medication_context: str|null,
                      regular_doctor_id: uuid|null (read-only for patient), regular_clinic: str|null, consent_location: bool}
TrustedContactIn  {name, relationship?: str, phone: str (^\+?[0-9 ()-]{6,20}$), contact_consented: true, active?: bool}
TrustedContactOut {id, name, relationship|null, phone, consented_at, active}
# consented_at is NOT NULL in the live DB: the patient confirms the contact agreed; the API sets consented_at = now().
# The table has no created_at (VERIFIED LIVE): "primary" = first active contact by id order is not meaningful,
# so the API uses the earliest consented_at.
CarePlanOut {id|null, target_systolic, target_diastolic, is_default: bool, effective_from|null, review_date|null,
             monitoring_readings_per_day|null, clinician_guidance|null}
CarePlanIn  {target_systolic, target_diastolic, review_date?, monitoring_readings_per_day?, clinician_guidance?}
```
Primary contact = active contact with the earliest `consented_at`. `PUT care-plan` creates a new active plan and supersedes the old one in one transaction.

**Emergency**
```
EmergencyConfigOut {
  version: str, country: "DZ", demo_mode: bool,
  numbers: [{id: str, label_fr: str, label_ar: str, number: str, verified: bool, source: str}],
  primary_number_id: str, disclaimer_fr: str, disclaimer_ar: str,
  client_fallback: {severe_systolic: 180, severe_diastolic: 120, red_flag_symptoms: [Symptom]}
}
EmergencyCardOut {
  full_name, relevant_conditions: [str], allergies|null, medication_context|null,
  primary_contact: {name, relationship, phone}|null, regular_doctor_name|null, regular_clinic|null,
  last_reading: {systolic, diastolic, measured_at, validation_status}|null, generated_at
}
```
No age on the card: the schema stores no date of birth (data minimisation, REPORTED). In demo mode the primary number is a teammate's phone and the UI shows a "DEMO" banner. Real emergency numbers are never dialled in tests.

The frontend caches `EmergencyConfigOut` and `EmergencyCardOut` (localStorage/Cache) after login and renders the emergency screen from the cache when offline.

**Emergency events (incidents)**
```
EmergencyEventIn  {id: uuid (generated by the client, makes retries idempotent), trigger_reason: symptom|severe_reading|manual,
                   alert_id?: uuid, symptoms_snapshot?: [Symptom], started_at: datetime}
EmergencyActionsIn {actions: [{client_action_id: uuid, action: ActionType, at: datetime, detail?: str}]}
ActionType = screen_opened | emergency_call_tapped | contact_call_tapped | share_opened | share_failed |
             location_granted | location_denied | location_timeout | outcome_reported
EmergencyEventPatch {location?: {lat, lon}, location_shared_with_consent?: bool,   # live columns: location_lat, location_lon only
                     reported_outcome?: str, ended_at?: datetime}
EmergencyEventOut {id, patient_id, trigger_reason, alert_id|null, symptoms_snapshot, started_at, ended_at|null,
                   actions: [{client_action_id, action, at, detail|null, confirmed: false}], reported_outcome|null,
                   location: {...}|null}
EmergencyReportOut {event: EmergencyEventOut, alert: AlertOut|null,
                    readings: [MeasurementOut] (started_at ± 24 h), symptom_reports: [SymptomReportOut] (same window)}
```
`POST emergency-events` with an existing id returns 200 with the stored event. Actions with a known `client_action_id` are ignored. `location` without `location_shared_with_consent=true` → 422 `consent_required`. The client queues events/actions offline and retries.

**Doctor notes, journal**
```
NoteIn  {note: str, advice?: str, follow_up_at?: datetime}
NoteOut {id, doctor_id, created_at, note|null (null for patients), advice|null, follow_up_at|null}
JournalIn {category: str, entry_text: str}     JournalOut {id, category, entry_text, created_at, doctor_review_status, reviewed_at|null}
```

**Prediction (doctor only)**
```
PredictionOut {status: ok|insufficient_history|model_unavailable, target_date: date|null, target: "morning_mean_bp",
               predicted_systolic|null, predicted_diastolic|null,
               interval: {systolic: [lo, hi], diastolic: [lo, hi]}|null,
               model_version|null, trained_on|null, generated_at|null,
               limitations: "Model estimate trained on synthetic data only. Not a measurement, not clinically validated, not used for alerts."}
```

### 2.5 Frontend flow rules (binding)
1. Reading → show evaluation; `requires_symptom_check` → symptom checklist; any `show_emergency` → emergency screen immediately; `recheck_after_seconds` and no symptoms → timer → recheck (as built in `web/src/flow.ts`).
2. **Offline/API failure fallback:** red-flag ticked → emergency screen; reading ≥ `client_fallback` thresholds → symptom check + "call if unwell" text. Nothing else is computed client-side.
3. Emergency screen order: emergency services call button first (`tel:` to primary number), then trusted contact, then the card. Logged actions use the wording "tapped"/"opened", never "called"/"sent".
4. ML prediction panel appears only in doctor views, labelled "Model estimate (synthetic training data)".

---

## 3. Backend ↔ Data layer (database contract)

### 3.1 Schema changes requested by the backend

**Status (VERIFIED 2026-10-30):** M3 = `20261030120000_backend_alignment` and M4 = `20261030120100_ml_predictions` are **live** and identical to branch `AI`. `birth_year` (item 5) was split into **M5** `20261030130000_patient_birth_year`, pending review. Items below are kept as the record of what was requested.

**M3 `backend_alignment`** (one migration, append-only, RLS on). The live project's **default privileges grant ALL on new `public` tables and functions to `anon` and `authenticated`** (VERIFIED LIVE), so the migration must `REVOKE ALL ... FROM anon, authenticated` on every new object and then grant only what is listed.
1. `alerts.alert_class` CHECK: add value `above_target_trend`.
2. `alerts.persistent boolean not null default false`.
3. ~~`alerts.resolution_note`~~ — already exists in the live DB (VERIFIED LIVE; missing from `DATA_SCHEMA.md`). No change.
4. New table `alert_measurements(alert_id uuid, measurement_id uuid, patient_id uuid, attached_at timestamptz default now(), primary key (alert_id, measurement_id))` with same-patient composite FKs to `alerts (id, patient_id)` and `measurements (id, patient_id)`; RLS select via `private.can_read_patient(patient_id)`; no write grants to `authenticated`.
5. `measurements.rested_5_min boolean null`; `patient_profiles.birth_year smallint null check (birth_year between 1900 and 2100)` (age on the doctor list, profile and emergency card).
6. `symptom_reports` CHECK: allow an empty `symptoms` array (replace `cardinality(symptoms) > 0` with the subset check only), so "none of these" answers are recorded.
7. `doctor_notes`: patients may read only `advice`, `follow_up_at` (today policy `doctor_notes_read` gives them the whole row, VERIFIED LIVE). Either a column-level grant split or a view; the API filters regardless.
8. Already answered by the live schema (VERIFIED LIVE): `alert_class` has no trigger preventing UPDATE (only the CHECK list); `created_by = coalesce(auth.uid(), new.created_by)`, so a privileged connection can set it explicitly; `emergency_events` columns are `location_lat`, `location_lon`, `location_shared_with_consent`, `reported_outcome` (text), `actions_attempted` (jsonb), `symptoms_snapshot` (text[]), `trigger_reason` (text, no CHECK). Remaining question for the data/AI developer: the expected JSON shape inside `actions_attempted` (docs say `[{action, at, confirmed}]`); the API adds `client_action_id` and `detail`.

**M4 `ml_predictions`** (before backend Phase 7):
```
ml_predictions(
  id uuid pk default gen_random_uuid(),
  patient_id uuid not null references profiles(id) on delete cascade,
  target_date date not null,                -- patient-local date being predicted
  target text not null check (target = 'morning_mean_bp'),
  status text not null check (status in ('ok','insufficient_history')),
  predicted_systolic numeric(5,1), predicted_diastolic numeric(5,1),   -- null unless status = 'ok'
  interval_systolic_low numeric(5,1), interval_systolic_high numeric(5,1),
  interval_diastolic_low numeric(5,1), interval_diastolic_high numeric(5,1),
  model_version text not null, trained_on text not null,              -- e.g. 'synthetic:pulse-sim-v1'
  features_until timestamptz not null, n_readings_used int not null,
  created_at timestamptz not null default now(),
  unique (patient_id, target_date, model_version)
)
RLS: select for actively assigned doctors (and admin); no patient read; writes by service role only.
Explicit REVOKE ALL FROM anon, authenticated first (default privileges would otherwise grant ALL).
```

### 3.2 Seed contract
- `python -m pulse_data.simulate seed` produces: 1 doctor, 4 patients (scenarios controlled / rising / severe event / sparse+dirty, REPORTED), assignments, care plans, trusted contacts, patient profiles, 30 days of `simulated` readings, a few symptom reports. Password read from `PULSE_DEMO_PASSWORD`; never hard-coded in a committed file.
- Backend then runs `python -m app.jobs.replay_alerts` (Ayoub) to create alerts from the seeded history through the real rules.
- The seed must be re-runnable on the **local** stack and on `pulse` only. Never on any other project.

### 3.3 Tooling access
| Tool | Connection | Owner |
|---|---|---|
| FastAPI | `PULSE_DATABASE_URL` (privileged role), `SUPABASE_URL` + `SUPABASE_ANON_KEY` (login proxy), JWT verification config | Ayoub |
| CSV import, seed | `DATABASE_URL` / service-role key | data/AI |
| ML batch job | `DATABASE_URL` (read measurements, write `ml_predictions` only) | data/AI |

---

## 4. Backend ↔ ML

| Item | Contract |
|---|---|
| Target | Next patient-local day's **morning** mean systolic and diastolic (`morning` = readings before 12:00 local time in `measured_tz`, else the profile timezone). |
| Inputs | `measurements` with `validation_status = 'valid'`, measured strictly before the start of the target day. BP-history features + day of week only (no lifestyle/adherence features in the MVP). |
| Eligibility (proposal; final value in the model card) | ≥ 6 valid readings on ≥ 4 distinct local days in the 7 days before the target day, and ≥ 1 morning reading. Otherwise write `status = insufficient_history`. |
| Training data | Synthetic set `pulse-sim-v1`, seed 7, 200 patients × 90 days (REPORTED). Optional single-patient temporal sanity check on Mendeley pjcv33hpp7 (CC BY-NC 3.0; file not committed). |
| Split | Patient-level 70/15/15 with a fixed seed; time order inside each patient; features only from earlier days; preprocessing fitted on train only; drop rows with systolic ≤ diastolic. |
| Baselines | Persistence (previous morning) and 7-day mean. Candidate: regularised linear regression and `HistGradientBoostingRegressor`; keep the best on validation, report on test once. |
| Metrics | MAE and RMSE (mmHg) for systolic and diastolic on test patients, for baselines and model, with bootstrap 95 % CI over patients. Labelled "synthetic". |
| Artefacts | `ml/artifacts/<model_version>/model.joblib` + `metadata.json` {model_version, trained_at, data (name, generator_version, seed, n_patients, split sizes), features, target, eligibility rule, metrics, limitations}. `ml/MODEL_CARD.md`. Retrain command reproducible from a clean checkout. Large artefacts and downloaded datasets git-ignored. |
| Inference | `python -m pulse_ml.predict --all [--date YYYY-MM-DD]` writes `ml_predictions`. Run after seeding and before the demo; optional daily schedule later. |
| Dependencies | `ml/requirements.txt` (numpy, pandas, scikit-learn, joblib, psycopg; pinned). Not added to `api/pyproject.toml`. |
| Tests | No patient overlap between splits; deterministic training on a tiny fixture; eligibility → `insufficient_history`; job writes nothing for unassigned/unknown patients; no write outside `ml_predictions`. |
| Forbidden | Writing to `alerts`/`measurements`; being called from a patient request; medication or treatment wording. |

---

## 5. Integration checkpoints

| ID | Checkpoint | Done when |
|---|---|---|
| C1 | Contract v1 frozen | `schemas.py` contains all §2 schemas, `openapi.json` exported, unbuilt endpoints return 501; frontend regenerated types |
| C2 | Data layer in repo | Data/AI PR merged: `supabase/`, `pulse_data/`, their tests green on Ayoub's machine and in CI |
| C3 | Backend parity on Postgres | Endpoints 1–4, 6, 10–14, 16 pass tests against the local stack |
| C4 | Emergency path | Endpoints 5, 7–9, 15, 18–21 working; frontend emergency screen works offline from cache |
| C5 | ML visible | `ml_predictions` filled by the batch job; endpoint 24 returns `ok` for a demo patient; model card committed |
| C6 | Demo from reset | Fresh seed → replay alerts → predictions → full demo script on the deployed URL |

## 6. Contract changes after v1 push

| Date | Change | Kind | Why |
|---|---|---|---|
| 2026-10-30 | `SymptomReportIn/Out.measurement_id` descriptions: validated, not stored until M7 | description | column does not exist (B24) |
| 2026-10-30 | `LastReading.source`, `LastReading.provenance` (required) | additive response fields | simulated readings must stay labelled on the emergency card |
| 2026-10-30 | `TrustedContactPatch` + PATCH summary: phone change refused (422 `consent_required`) | description / behaviour | a new number may be a person who never consented |
| 2026-10-30 | `PredictionOut.limitations` default starts with "Experimental" and adds "never used for alerts or emergency guidance"; description documents stale → `model_unavailable` | wording | label estimates as experimental (step 7) |
| 2026-10-30 | `EmergencyActionOut.confirmed` description: an action is a tap (attempt); PULSE never knows a call connected, a message was sent or delivered, or help was dispatched. `EmergencyEventOut` description: an incident record, not a notification | wording | keep "recorded / attempted / sent / delivered" distinct (step 8) |
| 2026-10-30 | Emergency events behaviour fixed by step 8: client id owned by another patient → 409 `conflict` (event never returned); `started_at`/action `at`/`ended_at` more than 5 min in the future → 422 `in_future`; `ended_at` before `started_at` → 422 `before_start`; `alert_id` not the patient's own → 422 `invalid_reference`; more than 500 actions per event → 422 `too_many_actions`; `location_shared_with_consent=false` removes a stored location; explicit `location: null` removes it | behaviour (error cases) | ownership, timestamps, consent |
| 2026-10-30 | `NoteOut` description: the patient sees only notes with advice or a follow-up date (note=null); others are not listed for the patient | description / behaviour | a note with nothing for the patient reveals nothing |
