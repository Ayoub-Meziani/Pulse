# PULSE backend implementation plan

Status: **proposal, 2026-10-30**. Based on `PULSE_BACKEND_ARCHITECTURE.md` (decisions A1–A12) and the contracts in `PULSE_INTEGRATION_CONTRACTS.md` (endpoint numbers #1–#25, migrations M3/M4, checkpoints C1–C6).
Estimates are for one developer with Claude Code and are rough. Total backend ≈ **22 h**; see §12 for cuts if less time remains.

## 0. Starting point (VERIFIED, 2026-10-30)

- `main` = `02dc64a` (initial commit). PR open: `feat/api-measurement-slice` (82f7473): FastAPI + SQLite slice, 39 tests passing.
- `feat/web-scaffold` (acb3e04): local only, not pushed.
- `docs/backend-architecture`: this documentation, local only.
- Data/AI code: not in any repository yet (REPORTED: 0 commits, no remote).

**Recommendation on PR #1:** merge it as the baseline before Phase 1. It carries the CI, docs, rules, contract export and error handling that Phase 1 builds on; keeping it open means every later branch stacks on it. Ayoub decides.

## 1. Execution order

The phases are numbered as requested; build them in this order so the emergency path (product priority 1) lands early:

```
P1 Foundation → P2 Auth → P4 Measurements → P5 Alerts + emergency config/card → P3 Profiles/contacts/care plan
→ P8 Emergency events + notes → P6 History/summary → P7 ML read endpoint → P9 Frontend serving → P10 Tests/security/demo
```
Contract v1 (task 1.1) comes first and unblocks the frontend for the whole sequence.

---

## Phase 1 — Foundation and database integration  (MVP, ≈ 3 h)

**Goal:** the API runs on the Supabase Postgres schema, and tests run against the local stack.

| Task | Detail | Files |
|---|---|---|
| 1.1 Contract v1 | Write every schema in contracts §2.4 into `schemas.py`; add routers with stub handlers returning 501 for endpoints not built; export `openapi.json`. Branch `feat/api-contract-v1`. | `api/app/schemas.py`, `api/app/routers/*.py` (stubs), `contract/openapi.json`, `docs/API_CONTRACT.md` (point to contracts file) |
| 1.2 Bring in the data layer | Data/AI developer's PR (`feat/data-layer`): `supabase/` (config, 2 migrations), `pulse_data/` (ingest, simulate; `rules.py` removed), their tests, `docs/data/`. Ayoub reviews, runs `npx supabase@2.122.0 start`, their tests, and merges. | (data/AI) |
| 1.3 Postgres connection | Add `psycopg[binary]` to `api/pyproject.toml`; `PULSE_DATABASE_URL=postgresql+psycopg://...`; remove `create_all` from `create_app`; `db.py`: session per request, helper `set_request_claims(session, user_id, role)` running `select set_config('request.jwt.claims', :json, true)` at transaction start. Keep `UTCDateTime` only if needed (Postgres `timestamptz` keeps offsets; prefer `DateTime(timezone=True)`). | `api/app/db.py`, `api/app/main.py`, `api/app/config.py`, `api/pyproject.toml` |
| 1.4 Map the schema | Declarative models mapping existing tables (no DDL): profiles, patient_profiles, doctor_patient_assignments, care_plans, measurements, symptom_reports, alerts, trusted_contacts, emergency_events, journal_entries, doctor_notes (+ alert_measurements after M3, ml_predictions after M4). Map only used columns. | `api/app/models.py` (rewrite) |
| 1.5 Vocabulary module | Constants and mappings of architecture §7 (level ↔ alert_class, red-flag set, symptom codes). Rules import red flags from here. | `api/app/vocab.py`, `api/app/analysis/rules.py`, `api/app/analysis/texts.py` |
| 1.6 Test harness | `conftest.py`: connect to the local stack DB (`PULSE_TEST_DATABASE_URL`, default `postgresql+psycopg://postgres:postgres@127.0.0.1:55322/postgres`), each test inside a transaction rolled back at the end; factories that insert `auth.users` rows (trigger creates `profiles`) and set roles/assignments; tokens minted locally with the stack's signing key. | `api/tests/conftest.py`, `api/tests/factories.py` |
| 1.7 CI | Job `api`: set up Supabase CLI 2.122.0, `supabase start` (only db + auth needed), run API tests and data-layer tests, contract check. | `.github/workflows/ci.yml` |
| 1.8 Retire SQLite pieces | Delete `api/app/seed.py` (replaced by data/AI seed + replay job), PBKDF2/JWT minting in `auth.py`, SQLite branch in `db.py`. | `api/app/seed.py`, `api/app/auth.py`, `api/app/db.py` |

**Depends on:** data/AI PR (1.2); M-blockers B1–B3 in the blockers file.
**Acceptance:** `supabase start` + `pytest` green locally; CI green; `GET /health` works against the local stack; 29 analysis tests still pass (vocabulary updates only).

---

## Phase 2 — Authentication and authorization  (MVP, ≈ 2 h)

| Feature | Behaviour |
|---|---|
| `POST /auth/login` (#2) | Calls GoTrue `POST {SUPABASE_URL}/auth/v1/token?grant_type=password` with `apikey: SUPABASE_ANON_KEY`; maps 400 → 401 `invalid_credentials`; loads profile; returns `SessionOut`. |
| `POST /auth/refresh` (#3) | `grant_type=refresh_token`; same mapping. |
| Token check | `current_user`: verify with JWKS (cached) or HS256 secret per env; require `aud=authenticated`; load `profiles`; 401 `invalid_token` on any failure. |
| `GET /me` (#4) | `UserOut` incl. `timezone`; email from `auth.users`. |
| Permissions | `require_patient_access(db, user, patient_id: UUID, write)`: patient = own; doctor = active assignment; admin = 403. `require_role`. |

**Files:** `api/app/auth.py` (rewrite: token verification + GoTrue client using `httpx`), `api/app/routers/auth.py`, `api/app/permissions.py`, `api/app/config.py` (`SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_JWKS_URL` or `SUPABASE_JWT_SECRET`).
**Tables:** `auth.users`, `profiles`, `doctor_patient_assignments`.
**Depends on:** knowing the signing method (blocker B7).
**Tests:** valid/expired/forged token; wrong password; refresh; profile missing → 401; A8 matrix (patient other patient → 403, unassigned doctor → 403, ended assignment → 403, admin → 403); `httpx` GoTrue calls mocked in unit tests plus one live login test against the local stack.
**Acceptance:** seeded doctor and patient can log in through FastAPI; all A8 cases pass.

---

## Phase 3 — Patient and doctor data management  (MVP except care-plan PUT, ≈ 2 h)

| Endpoint | Behaviour |
|---|---|
| `GET /patients` (#6) | Active assignments; highest active alert (`open`/`acknowledged`), counts, latest reading, 7-day averages (valid only); sort unchanged. |
| `GET/PUT /patients/{id}/profile` (#7) | Reads/updates `profiles.display_name, timezone` and `patient_profiles`; patient only for PUT; `regular_doctor_id` read-only for patients. |
| Trusted contacts (#8) | CRUD on `trusted_contacts`; patient only for writes. |
| `GET /patients/{id}/care-plan` (#17) | Active plan or default 140/90 `is_default=true`. |
| `PUT /patients/{id}/care-plan` (#17) | Doctor: insert new active plan, mark old `superseded`, set `supersedes_id`, one transaction. **Deferrable** (seed has plans). |

**Files:** `api/app/routers/patients.py`, new `api/app/routers/profile.py`, `api/app/services/profile.py`, `api/app/services/care_plans.py`, `api/app/services/measurements.py` (`current_target` from `care_plans` with `status='active'`).
**Tables:** profiles, patient_profiles, trusted_contacts, care_plans, doctor_patient_assignments.
**Tests:** permissions per endpoint; one-active-plan constraint (23505 → 409); default target.
**Acceptance:** doctor list matches the seed scenarios; patient can edit profile and contacts; doctor can read them.

---

## Phase 4 — BP measurement and validation  (MVP, ≈ 2 h)

| Feature | Behaviour |
|---|---|
| `POST /patients/{id}/measurements` (#10) | Insert with `source=manual, provenance=measured, method=unknown`, `created_by` via claims; read back `validation_status`, `quality_flags`; `invalid` → stored, evaluation `DATA-INVALID` (upper-limit breach → `requires_symptom_check`); else rules (Phase 5). |
| `GET /patients/{id}/measurements` (#11) | Filters `from`/`to` (timezone required), `limit`, `include_invalid`. |
| DB error mapping | Catch `IntegrityError`/`ProgrammingError` → codes in architecture §10; no request body in logs. |

**Files:** `api/app/services/measurements.py`, `api/app/routers/patients.py`, `api/app/errors.py` (Postgres code mapping), remove `analysis/validation.py` from the path (delete module and its tests; keep request-shape validation in Pydantic).
**Tables:** measurements (trigger `pulse-v1`).
**Tests:** valid reading; `needs_review` (e.g. 255/100) still evaluated; invalid (120/130) stored, no alert, 201 with `DATA-INVALID`; 310/150 → `requires_symptom_check`; patient cannot post for another patient; doctor cannot post; future timestamp → `invalid` flag `measured_in_future`.
**Acceptance:** frontend Add-reading flow works against Postgres with only type regeneration.

---

## Phase 5 — Alert and emergency logic  (MVP, ≈ 3 h)

| Feature | Behaviour |
|---|---|
| Rules wiring | `services/alerts.py`: active alerts = `status in (open, acknowledged)`; create (`alert_class` via vocab), attach (`alert_measurements`), raise (`UPDATE alert_class`, set `symptom_report_id`, `persistent`), `reason`, `actions=[next_step]`, `rule_code`, `rule_version`. Unique `(measurement_id, rule_code)` respected. |
| `POST /patients/{id}/symptom-reports` (#12) | 13 codes accepted; red flags → R-EMG-1; `source=patient_reported`. |
| `GET /patients/{id}/alerts` (#13), `GET /alerts/{aid}` (#14) | Status filter; detail with attached measurements. |
| `POST /alerts/{aid}/transition` (#15) | State machine of contracts §2.4; actor columns set; note stored in `resolution_note`. |
| `GET /config/emergency` (#5) | From env: `PULSE_EMERGENCY_NUMBERS` (JSON), `PULSE_DEMO_MODE`, `PULSE_DEMO_NUMBER`; `verified` false unless set; `client_fallback` from `analysis.rules` constants and `vocab.RED_FLAGS`. No auth. |
| `GET /patients/{id}/emergency-card` (#9) | Composed from profiles, patient_profiles, first active trusted contact, latest non-invalid reading, regular doctor name. |

**Files:** `api/app/services/alerts.py`, `api/app/routers/alerts.py`, new `api/app/routers/emergency.py`, `api/app/services/emergency.py`, `api/app/config.py`, `api/app/analysis/rules.py` (red flags from vocab, thresholds unchanged), `api/app/analysis/texts.py` (French wording if D6 confirmed; `DATA-INVALID` texts).
**Tables:** alerts, alert_measurements (M3, live), symptom_reports, measurements, patient_profiles, trusted_contacts.
**Depends on:** nothing schema-side (M3 live). D3 for real numbers (not for code).
**Tests:** port the existing API tests (severe → symptom → same alert raised with audit; symptom with normal BP → emergency; repeat severe within 15 min → attached + persistent; trend after 3 readings); transitions allowed/forbidden incl. note required; config shape and `verified:false` default; card permissions and content; T1–T16 analysis vectors unchanged.
**Acceptance:** the conception's crisis demo (186/118 → symptom check → chest pain → emergency, single alert in doctor view) passes end to end on Postgres.

---

## Phase 6 — Historical measurements, trends and summaries  (MVP summary; daily deferrable, ≈ 1.5 h)

| Feature | Behaviour |
|---|---|
| `GET /patients/{id}/summary` (#16) | `compute_summary` on `valid` readings; counts of `needs_review`/`invalid`; patient timezone in response. |
| `GET /patients/{id}/daily` (#25) | Per local date: morning/evening means and counts. **Deferrable**: the frontend chart can plot the raw list from #11. |

**Files:** `api/app/analysis/summary.py`, `api/app/analysis/types.py`, `api/app/routers/patients.py`.
**Tests:** existing summary tests adapted; timezone boundary test (reading at 23:30 UTC = next local day in Algiers).
**Acceptance:** summary for the "rising" seed patient shows `trend=rising`.

---

## Phase 7 — ML integration and prediction endpoint  (MVP, ≈ 1 h backend)

| Feature | Behaviour |
|---|---|
| `GET /patients/{id}/predictions/latest` (#24) | Doctor only (patient → 403). Latest row by `target_date` then `created_at`; none → `model_unavailable`; `insufficient_history` passed through; fixed limitation text. |

**Files:** new `api/app/routers/predictions.py`, models mapping `ml_predictions`.
**Tables:** ml_predictions (M4, live).
**Depends on:** rows from the data/AI batch job `pulse_ml.predict` (model `mbp-v1`, exists on `AI`); tests use fixture rows.
**Tests:** doctor ok; patient 403; unassigned doctor 403; empty → `model_unavailable`; the endpoint never touches alerts.
**Acceptance:** after the batch job runs on the seed, a demo patient shows `status=ok` with model version and "synthetic" label.

---

## Phase 8 — Incident records and follow-up  (MVP except journal, ≈ 3 h)

| Feature | Behaviour |
|---|---|
| Emergency events (#18–#21) | Client-generated id → idempotent create; actions appended to `actions_attempted` with `client_action_id` dedupe and `confirmed:false`; PATCH location only with consent; report = event + alert + readings and symptoms ±24 h. Creating an event linked to an alert does **not** change alert status (doctor reviews later). |
| Doctor notes (#22) | Doctor writes; patient gets `advice`/`follow_up_at` only. |
| Journal (#23) | Patient writes; doctor sets reviewed. **Deferrable.** |

**Files:** `api/app/routers/emergency.py`, `api/app/services/emergency.py`, new `api/app/routers/followup.py`, `api/app/services/followup.py`.
**Tables:** emergency_events, alerts, measurements, symptom_reports, doctor_notes, journal_entries.
**Depends on:** nothing (columns verified live).
**Tests:** duplicate event id → 200 same event; duplicate action ignored; location without consent → 422; doctor reads report; patient cannot read another patient's event; patient never sees `note`.
**Acceptance:** demo flow "emergency screen opened → call tapped → share opened → outcome reported" appears in the doctor's incident report with correct wording.

---

## Phase 9 — Frontend integration and API contract  (MVP, ≈ 1.5 h)

| Task | Detail |
|---|---|
| Serve the SPA | FastAPI mounts `web/dist` at `/` with history fallback to `index.html`; API stays under `/api/v1`. |
| Contract hygiene | Every schema change → `python -m app.export_openapi` → frontend `npm run gen:api`; CI checks both are current (web job exists on `feat/web-scaffold`). |
| Integration pass | With the frontend developer: run the full flows against the local stack, then `pulse`. |

**Files:** `api/app/main.py`, `.github/workflows/ci.yml`, `README.md`.
**Acceptance:** `npm run build` + `uvicorn` serves the whole app from one origin; no CORS configuration exists.

---

## Phase 10 — Testing, security checks and demo readiness  (MVP, ≈ 3 h)

| Task | Detail |
|---|---|
| Alert replay job | `python -m app.jobs.replay_alerts [--patient]`: evaluates seeded readings and symptom reports in time order with `clock = measured_at`; idempotent (skips readings already attached). |
| Demo reset script | `scripts/demo_reset.ps1` / `.sh`: seed (data/AI tool) → replay alerts → ML batch → print accounts. Local stack and `pulse` only. |
| Security | Login rate limit; no bodies in logs; secrets only in env; `PULSE_ENV=prod` refuses missing config; sign-up disabled verified on `pulse`; anon key cannot read any table (REPORTED 0 grants; re-check on cloud). |
| Deploy | FastAPI host with HTTPS (D5) + `pulse`; health check; phone test (GPS needs HTTPS). |
| Demo | Script rehearsal from a fresh reset; backup screen recording. |

**Acceptance (A1–A10 of the conception):** reading persists; doctor sees it within 15 s; rules tested; red flag → emergency with normal BP; emergency call in ≤ 2 taps and offline from cache; three paths visibly separate; alerts/incidents/notes in history; no cross-patient reads; simulated data labelled; demo repeatable from reset.

---

## 11. Task allocation (no shared responsibilities)

| Developer | Owns and delivers | Inputs | Outputs / done when |
|---|---|---|---|
| **Ayoub** (backend + integration) | Phases 1–10 above (except 1.2 authoring), contract v1, vocab mapping, rules, replay job, deploy, CI, merges | Data layer PR, M3, M4, frontend feedback | C1, C3, C4, C6 |
| **Data/AI developer** | 1) PR `feat/data-layer` (supabase/, pulse_data/ without rules.py, tests, docs) — **first**. 2) M3. 3) Seed generator: password from env; scenarios incl. trusted contacts and profiles. 4) Create/configure `pulse` with Ayoub (sign-up off) and apply migrations. 5) M4. 6) ML pipeline + model card + `pulse_ml.predict`. 7) CSV import doc for the demo. | Contracts §3–§4, Ayoub's approval of the ML target | C2, C5; model card committed; `ml_predictions` filled on `pulse` |
| **Frontend developer** | `web/`: adapt scaffold to contract v1 (uuid, refresh, 13 symptoms, validation display); emergency screen (config + card cache, `tel:`, contact call/share, GPS with timeout, offline action queue, client fallback); history chart; alerts list + acknowledge; doctor list (15 s polling) + patient detail + alert review + incident report + notes + prediction panel; profile + contacts; FR UI, FR/AR emergency text | `contract/openapi.json` (C1), contracts §2.5 | Every screen uses generated types; builds and lints in CI |

Shared interfaces: `contract/openapi.json` (Ayoub), `supabase/migrations/` (data/AI), `ml_predictions` table (data/AI writes, Ayoub reads), `EmergencyConfigOut` client-fallback constants (Ayoub).

## 12. If time is short

Cut in this order (each is independent): #25 daily series → #23 journal → #17 care-plan PUT → alert transitions other than doctor `reviewed` → prediction interval. Never cut: Phases 1, 2, 4, 5, the emergency events in 8, 9 and the demo reset in 10. If fewer than ~20 h remain when Phase 1 starts, apply the fallback trigger in architecture §11.

## 13. First implementation tasks (in parallel, once approved)

1. **Ayoub — task 1.1 Contract v1** on `feat/api-contract-v1` from the merged base. Needs no database, unblocks the frontend immediately.
2. **Data/AI developer — task 1.2** `feat/data-layer` PR into `Ayoub-Meziani/pulse`.
3. **Frontend developer** — review the scaffold and answer the review questions; then adapt to contract v1 once C1 lands.
