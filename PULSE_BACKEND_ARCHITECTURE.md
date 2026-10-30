# PULSE backend architecture (proposed, for approval)

Status: **proposal, 2026-10-30**. Nothing below is implemented unless marked so. Approval: Ayoub (integration lead).
Companion documents: `PULSE_BACKEND_IMPLEMENTATION_PLAN.md`, `PULSE_INTEGRATION_CONTRACTS.md`, `PULSE_BLOCKERS_AND_REQUIREMENTS.md`.

## 0. Evidence used

| Label | Meaning |
|---|---|
| **VERIFIED** | Checked in this repository by reading code or running commands on 2026-10-30, or **VERIFIED LIVE**: read from the cloud Supabase project `pulse` (org `lwiza`) on 2026-10-30 (schema dump, migration history, table stats, public auth settings, JWKS). See §12. |
| **REPORTED** | Stated in the data/AI developer's documents (`DATA_AI_INVENTORY.md`, `DATA_SCHEMA.md`, `DATA_DICTIONARY.md`, `API_CONTRACT.md` (data layer), `ML_INVENTORY.md`, `DATA_SOURCES.md`, `DEVICE_INTEGRATION.md`). Their code (importer, simulator, tests) was **not** supplied, so it could not be run here. |
| **UNRESOLVED** | Unknown or conflicting. |

What exists today:

| Asset | Status | Evidence |
|---|---|---|
| FastAPI backend, 10 operations, SQLAlchemy 2, SQLite, own JWT auth (integer ids) | Works | VERIFIED: 39 tests pass on Windows/Python 3.13.5; contract export current; smoke test via uvicorn; PR open from `feat/api-measurement-slice` (82f7473) |
| Deterministic rules `api/app/analysis/` (R-EMG-1, R-SEV-1/2/3, R-TGT-1, R-TRD-1, summary) | Works | VERIFIED: 29 pure-function tests |
| React + Vite + TS scaffold (login, Add reading flow, typed client) | Works locally | VERIFIED: `feat/web-scaffold` (acb3e04, local only): 6 tests, lint, build, proxy smoke test |
| Supabase data layer: 17 tables, 34 FKs, 87 CHECKs, 41 RLS policies, validation trigger `pulse-v1`, audit trigger, auth trigger | **Applied to the cloud project `pulse`** (both migrations `20261029120000`, `20261029120100`) | **VERIFIED LIVE** (counts and definitions match the documents; differences in §12). Their repo still has 0 commits; their 48 tests were not run here (REPORTED). |
| CSV importer `pulse_analysis.ingest`, simulator `pulse_analysis.simulate`, synthetic ML set (200 patients × 90 days) | Built | REPORTED |
| Their alert rules `pulse_analysis/rules.py` | Starter, not connected to DB, thresholds differ from ours | REPORTED |
| ML (notebooks, models, metrics, inference) | **Does not exist** | REPORTED (stated explicitly by the data/AI developer) |
| Cloud Supabase project for PULSE | **Exists**: `pulse`, ref `nfmfdhpxipdndggxtqho`, org `lwiza`, West EU (Paris), Postgres 17.11, created 2026-10-30 00:00 UTC; tables empty (estimated 0 rows); **public sign-up enabled** | VERIFIED LIVE (the data/AI inventory, written earlier, says no project existed) |
| Docker on Ayoub's machine | Docker 28.5.1, daemon running | VERIFIED |

## 1. Decisions

| # | Decision | Replaces / overrides |
|---|---|---|
| A1 | **Database: PostgreSQL via Supabase. The data/AI developer's migrations (`supabase/migrations/`) are the single schema.** SQLite and our `models.py` tables are retired. `Base.metadata.create_all` is removed; the API never creates tables. | D1 (SQLite part), D13 |
| A2 | **FastAPI is the only application API.** The frontend calls FastAPI only. It does **not** call PostgREST or `supabase-js` for data or auth. | Overrides the data layer `API_CONTRACT.md` sections that tell the frontend to `POST /rest/v1/...` |
| A3 | **Identity: Supabase Auth (GoTrue)**, uuid user ids = `profiles.id`. FastAPI proxies login/refresh to GoTrue and verifies the access token on every request. Role comes from `profiles.role` in the database, never from client input. **Public sign-up disabled** in every shared project. | D14 (own PBKDF2 + HS256 tokens) |
| A4 | **Authorization is enforced in FastAPI (`permissions.py`)**, which connects with one privileged database role. RLS stays enabled as a second line of defence for the PostgREST surface but is **not** the MVP enforcement path. Each transaction sets `request.jwt.claims` so database triggers that use `auth.uid()` (audit actor, `created_by`) record the real user. | — |
| A5 | **Data validation: the database trigger `pulse-v1` is authoritative** for `validation_status` / `quality_flags` on every path (API, CSV import, seed). The Python validation `analysis/validation.py` leaves the ingestion path. Request-shape errors stay Pydantic 422s. | V1–V4 in Python |
| A6 | **One rule engine: `api/app/analysis/rules.py`** (tested). `pulse_analysis/rules.py` is deleted. Thresholds ≥180 systolic **or** ≥120 diastolic (AHA "180/120 or higher"), red flags = the 7 AHA symptoms. Rules run synchronously inside the measurement / symptom request. | Their starter rules (strict `>`, 5 red flags) |
| A7 | **Alerts persist in the database's `alerts` table** with its status machine `open → acknowledged → reviewed → resolved`. Our episode behaviour (attach repeat readings within 15 min, raise severity on red-flag symptom) needs migration **M3** (see contracts). States `escalated`/`dismissed` are dropped; escalation is the link `emergency_events.alert_id`. | Our `alerts` / `alert_events` tables and 6-state machine |
| A8 | **Incidents = `emergency_events`** (existing table). Action log lives in its `actions_attempted` JSON with client-generated ids for idempotency; `confirmed` stays `false` for calls and shares (PULSE cannot verify them). No new incident tables. | Conception's `incidents` + `incident_actions` |
| A9 | **Emergency numbers live in FastAPI settings (env), not the database.** `verified:false` until D3 is confirmed. | — |
| A10 | **ML is an offline batch job owned by the data/AI developer** that writes `ml_predictions` (migration **M4**). FastAPI only reads it, doctor view only. The model never runs inside a patient request and never feeds the rules. | — |
| A11 | **Environments:** backend tests run on a throwaway container of the exact live Postgres build with the `AI` migrations applied (VERIFIED to work; Supabase CLI 2.54 `db start` fails on Ayoub's machine); the data/AI developer keeps their local Supabase stack (CLI 2.122.0); the existing **cloud Supabase project `pulse`** (org `lwiza`, ref `nfmfdhpxipdndggxtqho`; fictional data only) is shared for frontend integration and the demo. | D5 partly |
| A12 | **API vocabulary stays stable where the frontend already depends on it** (evaluation `level` none/notice/trend/severe/emergency, `full_name`, error format). Database vocabularies are adopted where they carry meaning the API did not have (sources, provenance, validation status, 13 symptom codes). Mapping lives in one backend module. | — |

## 2. Why this and not the alternatives

| Option | For | Against | Verdict |
|---|---|---|---|
| **A. Keep FastAPI + SQLite, ignore Supabase** | No Docker; fast tests; PR already reviewed | Throws away a stronger schema that already contains what our next slices need (profiles, trusted contacts, emergency events, journal, doctor notes, care-plan revisions, medications, ingestion batches). We would design ~8 tables again. The data/AI developer's CSV importer and simulator would need porting. A deployed SQLite file needs a persistent disk. | **Fallback only** (trigger in §11) |
| **B. FastAPI as the single API on Supabase Postgres (chosen)** | Reuses their schema, constraints, validation trigger, auth and seed tooling; keeps our tested rules, error format and OpenAPI contract; the frontend keeps one typed API; rules evaluate in the same request as the reading | Our 10 endpoints and their tests must be re-pointed at new tables (uuid, new columns); tests need the local Supabase stack (Docker); two-system auth (GoTrue + FastAPI) | **Chosen** |
| **C. Supabase as the whole backend** (frontend writes through PostgREST/RLS; FastAPI only for rules/ML) | Least backend code for CRUD | The safety-critical path breaks: after a direct insert, someone still has to evaluate rules and return emergency guidance. That needs a second call, an edge function or rules rewritten in PL/pgSQL. Two APIs for the frontend (PostgREST + FastAPI), two error formats, no single OpenAPI contract, rules duplicated or detached. | **Rejected** |

The deciding reason is the emergency path: **a reading or symptom report must return its evaluation and emergency instruction in the same response**. Option B does this with one request; option C cannot without extra moving parts.

## 3. Runtime topology

```
Phone browser ──HTTPS──> FastAPI (api/)  ── serves built web/ at /, API at /api/v1
                            │  login/refresh proxy ──> Supabase Auth (GoTrue)
                            │  privileged DB role, request.jwt.claims per transaction
                            ▼
                     Supabase Postgres (schema = supabase/migrations)
                            ▲
   data/ML tools (server-side only, DATABASE_URL):
   pulse_data.ingest (CSV import) · pulse_data.simulate (seed) · pulse_ml.predict (batch → ml_predictions)
```

- Development: `npx supabase@2.122.0 start` (local stack; ports 55321 API, 55322 DB per their config, REPORTED) + `uvicorn` + `npm run dev` (Vite proxy `/api`).
- Demo: FastAPI on a host with HTTPS (D5 open) + cloud project `pulse`.
- The frontend never receives the service-role key or the database URL. It does not need the anon key either (A2).

## 4. Database

- **Schema owner:** data/AI developer (`supabase/migrations/`). Migrations are append-only (REPORTED rule; adopted). Backend asks for schema changes through a PR on that folder; Ayoub approves.
- **Applying migrations:** locally by each developer (`supabase db reset` on the **local** stack only); to `pulse` by the data/AI developer after Ayoub approves the PR. No one else pushes migrations.
- **Seed:** the data/AI developer's generator (`simulate seed`) produces fictional users and data. The generated `seed.sql` is not committed when it contains a password; the demo password comes from an environment variable and is shared privately. Alerts for seeded history are created by a backend replay job (rules evaluated in time order), so seeded alerts come from the same rules as live ones.
- **Tables the MVP API uses:** `profiles`, `patient_profiles`, `doctor_patient_assignments`, `care_plans`, `measurements`, `symptom_reports`, `alerts` (+ `alert_measurements` from M3), `trusted_contacts`, `emergency_events`, `journal_entries`, `doctor_notes`, `ml_predictions` (M4). Read by tooling only: `devices`, `ingestion_batches`. Present but **not exposed by the MVP API**: `lifestyle_logs`, `medications`, `medication_adherence_events`, `audit_log` (admin only).
- **ORM:** SQLAlchemy 2 declarative models that *map* existing tables (no DDL), psycopg 3 driver (`postgresql+psycopg://`). Only the columns the API uses are mapped.

## 5. Authentication and authorization

1. `POST /api/v1/auth/login` → FastAPI calls GoTrue password grant with the anon key (server-side env) → returns GoTrue `access_token` + `refresh_token` + our `UserOut`.
2. Every request: FastAPI verifies the bearer token (signature, `exp`, `aud=authenticated`), takes `sub` as user id, loads `profiles` (role, display name, timezone). Unknown profile → 401.
3. Token verification key: JWKS from `<SUPABASE_URL>/auth/v1/.well-known/jwks.json` if the project uses asymmetric signing keys, otherwise the HS256 JWT secret. **Cloud project `pulse`: ES256 (EC P-256) via JWKS — VERIFIED LIVE.** Local stack (CLI 2.122.0): UNRESOLVED; the code supports both, chosen by env.
4. `permissions.require_patient_access(db, user, patient_id, write)` keeps its current contract (VERIFIED in `api/app/permissions.py`), adapted to uuid ids and **active** rows of `doctor_patient_assignments`. Patient: own id only. Doctor: actively assigned patients; writes only on doctor-owned resources (care plan, notes, journal review, alert review). `admin`: no access to patient data through the API in the MVP.
5. Sign-up: must be disabled. Accounts are created by the seed tooling (service role). The data/AI developer's question about email confirmation is therefore moot for the demo. **Live state today: sign-up is ENABLED** (`disable_signup: false`, email confirmation on; VERIFIED LIVE). Anyone holding the publishable key can register and get a `patient` profile. Ayoub must switch it off in the dashboard (blockers B16).
6. Tokens in the browser: `sessionStorage` (current scaffold). Access tokens are short-lived; the frontend refreshes via `/auth/refresh`.

## 6. Data ownership

| Data | Table | Written by | Read through API by |
|---|---|---|---|
| Account, role, display name, timezone | `auth.users`, `profiles` | seed tooling (service role); patient may edit display name/timezone | self; assigned doctor |
| Doctor–patient relationship | `doctor_patient_assignments` | seed tooling only | doctor (own), patient (own) |
| Emergency card fields, consent | `patient_profiles` | patient (API) | patient; assigned doctor |
| Trusted contacts | `trusted_contacts` | patient (API) | patient; assigned doctor |
| BP readings | `measurements` | patient via API (`source=manual`); CSV import and seed via tooling | patient; assigned doctor |
| Validation status/flags | `measurements` (trigger) | database only | same as readings |
| Symptom reports | `symptom_reports` | patient (API) | patient; assigned doctor |
| Alerts | `alerts`, `alert_measurements` | **backend rules only**; status changes via API transitions | patient; assigned doctor |
| Emergency events (incidents) | `emergency_events` | patient device via API | patient; assigned doctor |
| Care plan / targets | `care_plans` | assigned doctor via API; seed | patient; assigned doctor |
| Doctor notes / advice | `doctor_notes` | assigned doctor | doctor: all fields; **patient: `advice` and `follow_up_at` only** |
| Journal | `journal_entries` | patient; doctor sets review status | patient; assigned doctor |
| Predictions | `ml_predictions` | ML batch job only | **assigned doctor only** |

Note on `doctor_notes`: the data layer's RLS lets a patient read the whole row (VERIFIED LIVE: policy `doctor_notes_read` uses `private.can_read_patient(patient_id)`). The conception keeps the clinical note private. The API therefore returns only `advice` and `follow_up_at` to patients. Ask the data/AI developer to align the RLS policy too (blockers file).

## 7. Vocabulary reconciliation (one mapping module: `api/app/vocab.py`)

| Concept | API (contract) | Database | Rule |
|---|---|---|---|
| Measurement source | `manual`, `device_sync`, `csv_import`, `simulated` | same | DB vocabulary adopted (replaces our `device`/`imported`) |
| Provenance / method | `measured`/`estimated`/`simulated`; `cuff_oscillometric`/`cuff_auscultatory`/`wearable_estimate`/`unknown` | same | adopted; API default for manual entry: `measured` + `unknown` |
| Validation | `valid`, `needs_review`, `invalid` + `quality_flags[]` | same | replaces `valid`/`questionable` |
| Symptoms | 13 DB codes | same | red-flag subset = `chest_pain, shortness_of_breath, back_pain, numbness, weakness, vision_change, difficulty_speaking` |
| Evaluation level | `none`, `notice`, `trend`, `severe`, `emergency` | `alert_class`: `above_target`, `above_target_trend` (M3), `severely_high`, `possible_emergency` | mapped 1:1 |
| Alert status | `open`, `acknowledged`, `reviewed`, `resolved` | same | adopted |
| Ids | uuid strings | uuid | breaking change for the frontend (types regenerate) |
| User name | `full_name` | `profiles.display_name` | API name kept to avoid frontend churn |

## 8. Validation, rules and the emergency path

- **Order inside `POST /patients/{id}/measurements` (one transaction):** insert → trigger sets `validation_status` → if `invalid`: no rules, evaluation explains why and asks to re-measure → else load active alerts and target → `analysis.rules.evaluate_measurement` + `evaluate_trend` → write/attach alerts → commit → return `{measurement, evaluation, alert, trend_alert}`.
- **`needs_review` readings still go through the safety rules** (a 260/150 reading is "unusual" and also severe). They are excluded from averages, trend direction and ML features (`valid` only). This deliberately differs from the data/AI proposal to include `needs_review` in analytics: `needs_review` covers possible duplicates and wearable estimates, which would distort averages.
- **Invalid readings above the upper limits** (systolic > 300 or diastolic > 200): evaluation still sets `requires_symptom_check=true` and tells the patient to use the Urgence button if unwell. A typo must not hide a possible crisis.
- **Symptom report:** any red-flag code → `level=emergency`, `show_emergency=true`, raises the most recent open severe alert from the last hour or creates one (R-EMG-1, unchanged).
- **Latency guarantee:** the rules are pure in-process functions; nothing in this path calls ML, GoTrue (beyond token verification, local) or any external service.
- **Client fallback when the API is unreachable:** the frontend shows the emergency screen for a ticked red-flag symptom and shows the recheck/symptom guidance for ≥180/≥120, using constants from the cached `GET /config/emergency`. This is the only rule logic in the frontend, it is used only when the request fails, and its constants come from the backend so they cannot drift.
- **Never:** ML in this path; claims that a call/SMS/share succeeded; diagnosis or medication advice (unchanged from `CLAUDE.md`).

## 9. ML integration

- Batch job `python -m pulse_ml.predict` (data/AI) reads `measurements` (`valid` only) with a privileged connection, computes features with the same code used in training, writes one `ml_predictions` row per patient and target date, including `status = insufficient_history` rows when the eligibility rule fails.
- FastAPI exposes `GET /patients/{id}/predictions/latest` to the **assigned doctor only**: `status ok | insufficient_history | model_unavailable` (no row or job never ran), values, interval if any, `model_version`, `trained_on`, fixed limitation text.
- **Features restricted to BP history (+ day of week) for the MVP.** The synthetic set also has missed dose, sodium, activity and sleep, but the MVP app does not collect those from users, so a model using them would be fed missing values in production (train/serve skew). Lifestyle features are allowed only once the app collects them.
- Honesty requirements: every metric labelled "synthetic data"; the model rediscovers the simulator's invented formula, so its accuracy says nothing about real patients (REPORTED by the data/AI developer; agreed).

## 10. Errors, provenance, security

- Error body unchanged: `{"error": {"code", "message", "details"}}` (VERIFIED in `api/app/errors.py` usage and tests). Postgres errors map in one place: `23505` → 409 `conflict`/`duplicate_measurement`, `23514` → 422 `validation_failed`, `23503` → 422 `invalid_reference`, `42501` → 403 `forbidden`. Request bodies (health data) are never logged or echoed in errors.
- Provenance: every reading returned with `source`, `provenance`, `method`, `validation_status`, `quality_flags`. Simulated data stays labelled end to end.
- Secrets: FastAPI env holds `PULSE_DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, JWT verification config. **The service-role key is not given to FastAPI**; only the seed/import tooling uses it. Nothing secret reaches `web/`.
- Login rate limit (in-memory, per IP + email) before the cloud demo. HTTPS required for GPS. CORS stays off (single origin).

## 11. Risks and the fallback trigger

| Risk | Impact | Mitigation |
|---|---|---|
| Data layer code not in the repo (schema itself now VERIFIED LIVE) | Local stack and their tests cannot be run by others; schema history lives only on their machine and in the cloud | First task: data/AI developer pushes `supabase/` + code; Ayoub runs `supabase start` + their tests |
| Cloud schema changed without a migration file | Two schemas drift (cloud vs repo) | Every cloud change goes through a migration file in `supabase/migrations/`, applied with `db push`; no dashboard edits (§12) |
| Re-pointing 10 endpoints + tests at a new schema takes longer than expected | Late emergency features | Contract-first (frontend not blocked), emergency endpoints scheduled right after parity |
| Docker needed for tests and local DB | Slower CI, setup friction on Windows | Pin CLI `npx supabase@2.122.0` (their global CLI is broken, REPORTED); CI starts only needed services |
| JWT signing method: cloud ES256 (verified), local unknown | Auth config differs per environment | Support JWKS and HS256 from day one |
| Alert semantics differ from their schema | Wrong doctor view | Migration M3 before Phase 5 |
| Shared cloud project contains a demo account with a known password | Account misuse on a public URL | Sign-up off, password via env, fictional data only, project deleted after the hackathon |
| Synthetic-only ML | Misleading pitch | Doctor-only panel, "synthetic" label, baselines shown next to the model |

**Fallback trigger (option A):** if, within **2 hours** of the data layer being pushed, Ayoub cannot run `supabase start`, apply the migrations and get the data layer tests green on his machine, or if the remaining hackathon time is too short for Phases 1–5 (see plan estimates), keep SQLite and port only `trusted_contacts`, `patient_profiles` and `emergency_events` into our own models. Decide explicitly; do not drift into a half-migrated state. (Risk now lower: the schema is VERIFIED LIVE and the backend can also develop against the cloud project if the local stack fails.)

## 12. Live Supabase verification (2026-10-30)

Method: Supabase CLI 2.54.11 (already logged in on Ayoub's machine), `supabase link` from a scratch folder outside the repo, `supabase gen types --linked`, `supabase migration list --linked`, `supabase inspect db table-stats|vacuum-stats --linked`, `supabase db dump --linked -s public,private` and `-s auth` (schema only, no data), public `GET /auth/v1/settings` and JWKS with the publishable key. Dashboard not used (session expired; not signed in on Ayoub's behalf).

| Item | Live state | Matches docs? |
|---|---|---|
| Project | `pulse`, ref `nfmfdhpxipdndggxtqho`, org `lwiza`, eu-west-3 (Paris), Postgres 17.11 | New (docs said none) |
| Migration history | `20261029120000`, `20261029120100` applied | Yes (same file names as reported) |
| Objects | 17 tables, RLS enabled on 17, 41 policies, 87 CHECKs, 34 FKs, 10 `private` functions, 19 table triggers (incl. `measurements_validate`) + `on_auth_user_created` on `auth.users` | Yes |
| Data | All tables ≈ empty (estimated 0 live rows; exact counts need SQL access) | — |
| Validation trigger `pulse-v1` | invalid: sys ≤ dia, sys ∉ 50–300, dia ∉ 25–200, pulse ∉ 25–250, > now + 5 min; needs_review: sys ∉ 70–250 or dia ∉ 40–150, estimated, ±2 min duplicate | Yes |
| `created_by` | trigger sets `coalesce(auth.uid(), new.created_by)` → a privileged connection can set it explicitly or via `request.jwt.claims` | Answers B5 (partly) |
| `alerts` | columns incl. **`resolution_note`** (not in docs); `alert_class` CHECK has no trend class; status CHECK `open/acknowledged/reviewed/resolved` with timestamps required per status; unique `(measurement_id, rule_code)` and `(symptom_report_id, rule_code)`; no `persistent` | `resolution_note` undocumented |
| `symptom_reports` | **CHECK `cardinality(symptoms) > 0`**: an empty "none of these" answer cannot be stored | Conflicts with our contract |
| `emergency_events` | `location_lat`, `location_lon` only (no accuracy/time), consent CHECK, `actions_attempted` jsonb, `symptoms_snapshot` text[], `trigger_reason` free text | Contract adjusted |
| `trusted_contacts` | `consented_at` **NOT NULL**, `relationship` nullable, phone regex `^\+?[0-9 ()-]{6,20}$` | Contract adjusted |
| `care_plans` | targets nullable (90–200 / 50–130), one active plan per patient | Default target applies when null |
| `measurements` | no `rested_5_min` column | M3 still needed |
| Grants | `anon`: no table grants (only a sequence + schema usage). **Default privileges still grant ALL on future tables/functions in `public` to `anon` and `authenticated`** | Every new migration must REVOKE explicitly |
| Auth | email provider only; sign-up **enabled**; email confirmation required; JWT ES256 via JWKS | Sign-up must be disabled |

**Changes made to the project:** none to schema, data, policies or settings. Side effect of the CLI: `supabase link`/`inspect`/`dump` create or refresh the temporary login role `cli_login_postgres` (standard Supabase CLI behaviour). Logged in `PULSE_SUPABASE_CHANGELOG.md`.
