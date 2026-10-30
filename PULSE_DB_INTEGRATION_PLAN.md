# Database integration plan (Workstream 2)

Status: 2026-10-30. Implements phases 1–2 and the persistence side of phases 4–8 of `PULSE_BACKEND_IMPLEMENTATION_PLAN.md`, against the schema that is **VERIFIED identical** on branch `AI` and on the live project `pulse` (`PULSE_BRANCH_RECONCILIATION.md` §3).
Branch: `feat/api-supabase`, from `feat/api-contract-v1`. Owner: Ayoub. No migration files are created on this branch.

## 1. Table mappings (API ↔ database)

| API object | Table(s) and columns | Mapping rules |
|---|---|---|
| `UserOut` | `auth.users.email`; `profiles.id, role, display_name, timezone` | `full_name = display_name`; role from `profiles` only |
| Assignment check | `doctor_patient_assignments (doctor_id, patient_id, status='active')` | ended assignments give no access |
| `CarePlanOut` / target | `care_plans` where `status='active'` (one per patient, unique index) | null targets or no plan → 140/90, `is_default=true` |
| `MeasurementIn/Out` | `measurements` | insert `source='manual'`, `provenance='measured'`, `method='unknown'`, `unit='mmHg'`, `created_by=<user id>`, `measured_tz` default `profiles.timezone`; read back `validation_status`, `quality_flags`, `validation_policy_version`; `rested_5_min` stored (M3 live) |
| `SymptomReportIn/Out` | `symptom_reports` (`source='patient_reported'`) | empty list = "none of these", stored (M3 live); `report` always returned |
| `AlertOut/AlertBrief` | `alerts` | `level ↔ alert_class` (notice=`above_target`, trend=`above_target_trend`, severe=`severely_high`, emergency=`possible_emergency`); `rule_id = rule_code`; `rule_version='pulse-rules-1'`; `trigger_source='rule_engine'`; `next_step = actions[0]`; `persistent=true` set by R-SEV-2 (M3 live) |
| Alert episode readings | `alert_measurements` (M3 live) | attach rows for R-SEV-2/3, R-TGT-1, R-TRD-1; `AlertDetail.measurements` = triggering reading + attached readings |
| Transitions | `alerts.status` + `acknowledged_at/by`, `reviewed_at/by`, `resolved_at/by`, `resolution_note` | DB CHECKs require the matching timestamp per status |
| `ProfileOut/In` | `profiles` + `patient_profiles` (`user_id`) | `birth_year` from M5 (pending review; null until applied); `regular_doctor_name` via `profiles` of `regular_doctor_id` |
| `TrustedContactIn/Out` | `trusted_contacts` | `consented_at = now()` when `contact_consented=true`; phone regex enforced by DB and Pydantic |
| `EmergencyCardOut` | profiles, patient_profiles, first active contact by `consented_at`, latest non-invalid measurement | `age` from `birth_year` (M5) |
| `EmergencyEvent*` | `emergency_events` | `trigger_reason` text; actions appended to `actions_attempted` jsonb as `{client_action_id, action, at, detail, confirmed:false}`; `location_lat/lon` only with `location_shared_with_consent=true` (DB CHECK) |
| `NoteOut/In` | `doctor_notes` | patient reader gets `note=null` |
| `JournalOut/In` | `journal_entries` | review sets `doctor_review_status`, `reviewed_by/at` |
| `PredictionOut` | `ml_predictions` (M4) | missing table/row → `model_unavailable` |

## 2. Authentication flow and JWT verification

1. `POST /auth/login`: `httpx.post(f"{SUPABASE_URL}/auth/v1/token?grant_type=password", headers={"apikey": SUPABASE_ANON_KEY}, json={email, password})`. 400/401 from GoTrue → 401 `invalid_credentials`. Response `access_token`, `refresh_token`, `expires_at`; then load the profile → `SessionOut`.
2. `POST /auth/refresh`: same endpoint, `grant_type=refresh_token`.
3. Each request: `PyJWKClient(f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json")` (cached) → `jwt.decode(token, key, algorithms=["ES256"], audience="authenticated", issuer=f"{SUPABASE_URL}/auth/v1")`. Cloud project: ES256 (VERIFIED LIVE). Tests: a locally generated ES256 key pair, injected through settings (`jwks` override), so no GoTrue is needed in unit/integration tests.
4. `sub` → `profiles` row; missing → 401 `invalid_token`. Role `admin` → 403 on patient data.
5. Dependency: `PyJWT[crypto]` (adds `cryptography`) and `httpx` move to runtime dependencies.

## 3. Database access and permissions

| Item | Decision |
|---|---|
| Driver | `psycopg[binary]` 3 via SQLAlchemy 2 (`postgresql+psycopg://`) |
| Cloud connection | Supavisor **session** pooler `aws-1-eu-west-3.pooler.supabase.com:5432`, user `postgres.nfmfdhpxipdndggxtqho` (the direct host has no IPv4 route from Ayoub's network: VERIFIED `Test-NetConnection` failed for `db.<ref>.supabase.co:5432`, pooler 5432/6543 reachable). Session mode avoids the prepared-statement problems of transaction mode (6543). |
| Role | `postgres` (bypasses RLS) for the MVP; authorization in `permissions.py`. A dedicated least-privilege role is a post-MVP change (needs a migration by the data/AI developer). |
| Per transaction | `select set_config('request.jwt.claims', :claims, true)` so `auth.uid()` in triggers (`audit`, `validate_measurement`) records the real user; `created_by` also set explicitly (`coalesce(auth.uid(), new.created_by)`, VERIFIED). |
| Secrets | `PULSE_DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_ANON_KEY` in local `.env` / host secrets only. No service-role key in the API. |

## 4. Local and CI database for tests

- Supabase CLI 2.54.11 `db start` fails on this Windows machine (container closes connections; VERIFIED). Their documented workaround is `npx supabase@2.122.0`.
- **Chosen for backend tests:** plain container `public.ecr.aws/supabase/postgres:17.11.0.003` (same build as the live project; includes `auth.users`, `auth.uid()` and the `anon/authenticated/service_role` roles) + apply `supabase/migrations/*.sql` with `psql -v ON_ERROR_STOP=1`. VERIFIED to work in about one minute (`PULSE_BRANCH_RECONCILIATION.md` §3).
- Script `scripts/test-db.sh` and `scripts/test-db.ps1` (Ayoub): start container on port 55432, apply migrations from the repo, print `PULSE_TEST_DATABASE_URL`. Requires the `AI` branch content in the working tree (merge `AI` first, or check out `supabase/migrations` from `origin/AI`).
- Fixtures: insert `auth.users (id, email)` (the trigger creates `profiles`, same technique as the data/AI tests), then set roles/assignments as `postgres`; each test in a transaction rolled back at teardown; tokens minted with the test ES256 key.
- CI: GitHub Actions service container with the same image; step applies migrations; then `pytest` for `api/tests`.

## 5. What is kept, replaced or removed from the SQLite slice

| Item | Fate |
|---|---|
| `analysis/rules.py`, `summary.py`, `texts.py`, `types.py` | **kept** (pure); already aligned to DB symptom codes on `feat/api-contract-v1` |
| `analysis/validation.py` | **removed** in this workstream; DB trigger `pulse-v1` is authoritative |
| Error format, `ApiError`, contract tests | kept |
| Alert episode logic (create / attach / raise) from PR #1 `services/alerts.py` | **ported** to the DB `alerts` table (+ `alert_measurements`) |
| Doctor-list sorting, permissions semantics (patient own; doctor assigned, read-only on readings) | ported |
| SQLAlchemy models, `create_all`, PBKDF2 passwords, own JWT, `seed.py` | replaced by mapped models of existing tables, Supabase Auth, data/AI seed + backend replay job |

## 6. Migrations and ownership (data/AI developer writes, Ayoub approves, data/AI applies)

**Status 2026-10-30 (VERIFIED, `PULSE_DATABASE_SYNC_POLICY.md` §5):** M3 and M4 are live; M5 `20261030130000_patient_birth_year` (nullable `patient_profiles.birth_year`) is on `AI`, pending review. `birth_year` moved from M3 to M5.

| Migration | Contents | Needed by |
|---|---|---|
| **M3 `backend_alignment`** | `alert_class` + `above_target_trend`; `alerts.persistent`; table `alert_measurements` (RLS read via `can_read_patient`, no client writes); `measurements.rested_5_min`; `symptom_reports` allow empty `symptoms`; `patient_profiles.birth_year smallint` (1900–2100, nullable; needed for age on the doctor list and the emergency card, requested by the frontend screens); `doctor_notes` patient visibility limited to `advice`, `follow_up_at`; explicit `REVOKE ALL ... FROM anon, authenticated` on new objects (live default privileges grant ALL) | Phases 4–5 (alerts, symptoms), profile age |
| **M4 `ml_predictions`** | as in `PULSE_INTEGRATION_CONTRACTS.md` §3.1 | Phase 7 |

Both as new files after `20261029120100`, never edits of applied files. Tests in their `tests/test_db.py`. Applied to `pulse` with `npx supabase@2.122.0 db push` by the data/AI developer after the PR is approved; each push recorded in `PULSE_SUPABASE_CHANGELOG.md`.

## 7. Order of work on `feat/api-supabase` (each step tested and committed)

1. **Done** (`feat/api-supabase` `93a4e0a`, `31fc5e7`): `scripts/test_db.py` (live image 17.11.0.003 + `scripts/test_db_auth_live.sql` + all migrations, ~11 s), rollback-per-test fixtures, ES256 test key. Finding: the plain image's `auth.uid()` ignores `request.jwt.claims`; the test DB now gets the live definitions.
2. **Done** (`93a4e0a`, `31fc5e7`): `db.py`, 14 mapped models checked column-by-column against the migrated DB, `vocab.py` checked against the DB CHECKs. Finding: `measurements.created_by` must be read back from the trigger (fixed).
3. **Done** (`31fc5e7`): JWKS ES256/RS256 verification, GoTrue proxy for login/refresh, `/me`, `permissions.py`; 178 tests pass with the test DB (M1–M5 applied there; M5 not yet on `pulse`).
4. **Done** (`feat/api-supabase` `28e8948`): measurements POST/GET, pulse-v1 validation read back, `DATA-INVALID`, SQLSTATE error mapping, permissions; 209 tests pass on the live (M1–M4) and latest (M1–M5) test DBs. Alerts are not persisted until step 5 (`alert`/`trend_alert` null; repeat severe readings re-evaluated as R-SEV-1).
5. **Done** (`feat/api-supabase` `52b4d02`): alert episodes (create / attach / raise), symptom reports with R-EMG-1, alerts list/detail, transitions; retries (`possible_duplicate`) never change alerts; 235 tests on M1–M6. `symptom_reports.measurement_id` does not exist: validated, not stored (M7 requested).
6. **Done** (`feat/api-supabase` `ab778d8`): doctor list, summary, profile, trusted contacts (consent enforced; phone change needs a new consented contact), care plan GET/PUT, emergency card (no notes, no M6 fields, no wearable data; last reading labelled with source/provenance); 282 tests on M1–M6. **Demo readiness:** the seeded `pulse` has readings but no alerts, so the doctor list shows no alert levels and no alert history until the step 9 replay job runs the rules over the seed; nothing is invented in the meantime.
7. Emergency events (idempotent create, actions, patch, report), notes.
8. **Done (plan step 7)** (`feat/api-supabase` `6eef991`): predictions endpoint, doctor only, configured model version (`PULSE_ML_MODEL_VERSION`, default `mbp-v1`), stale rows → `model_unavailable`; 297 tests on M1–M6. Live `pulse` has 0 prediction rows until the data/AI developer runs `pulse_ml.predict` against it.
9. Replay job for seeded history; demo reset script.
10. Run against `pulse` with the fictional seed (after sign-up is disabled).

Acceptance: every contract test that returns 501 today returns the specified status; A1–A10 scenarios from the conception pass on the test DB; contract export unchanged unless a reviewed contract change.
