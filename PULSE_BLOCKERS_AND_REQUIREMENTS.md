# PULSE blockers and requirements

Status: 2026-10-30. Lists only what is **not** already available in the repository or in the data/AI developer's documents.
Priority: **P0** = blocks starting the parallel work, **P1** = blocks a specific phase, **P2** = needed before the demo, **P3** = can wait.

## Are the materials sufficient to start?

**Yes. Nothing blocks the three developers from starting** (updated after branch reconciliation, `PULSE_BRANCH_RECONCILIATION.md`).
- Contract v1 is implemented on `feat/api-contract-v1` (local, awaiting push approval).
- The migrations on branch `AI` are VERIFIED identical to the live schema and apply on the same Postgres build in a throwaway container, so backend DB integration and its tests can start (`PULSE_DB_INTEGRATION_PLAN.md`).
- Still required before seeding or sharing the cloud URL: public sign-up off (B16).

Resolved since the previous version: B1 (code is on branch `AI`), B2 (both developers have pushed branches), B3 (schema verified by applying the migrations ourselves; their own 48 tests still not run here, now P3), B6 (project exists, migrations applied), B7 (ES256), B9 (generator already reads `PULSE_DEMO_PASSWORD`), B11 (frontend code inspected directly).

## Decisions needed from Ayoub (before work starts)

| # | Decision | Why | Options / recommendation | Priority |
|---|---|---|---|---|
| D-1 | Approve the architecture (A1–A12), in particular **A2: the frontend does not call Supabase/PostgREST directly** | It overrides the data/AI developer's published data-layer contract; if not settled, the frontend developer builds against two APIs | Approve as written | P0 |
| D-2 | Merge PR #1 (`feat/api-measurement-slice`) as the baseline | Every next branch stacks on it otherwise | Merge before Phase 1 | P0 |
| D-3 | Ownership change: `api/app/analysis/` moves to Ayoub; data/AI owns `supabase/`, `pulse_data/`, `ml/` | Avoids two owners for the rules | Approve; then update `CLAUDE.md` | P0 |
| D-4 | ML target and scope: next-day morning mean SBP/DBP, BP-history features only, doctor-only display | Data/AI developer cannot start ML without it | Approve contracts §4 | P0 (for data/AI) |
| D-5 | Readings with `needs_review` excluded from averages/trend/ML (still evaluated by safety rules) | Differs from the data/AI proposal | Approve architecture §8 | P1 |
| D-6 | Hosting for FastAPI (D5) | Needed for HTTPS (GPS) and the demo URL | Render or Railway free tier; backup: laptop + Cloudflare tunnel | P2 |
| D-7 | UI language for API wording (D6): keep English alert texts or translate `texts.py` to French now | Affects Phase 5 texts | French for patient-facing texts, Arabic only on the emergency screen (frontend) | P2 |

## Information or files still needed

| # | What is missing | Why it is needed | Who provides | Blocks? | Priority |
|---|---|---|---|---|---|
| B1 | ~~Data/AI code in the repo~~ **Resolved**: branch `AI` (`a004329`) | — | — | No | — |
| B2 | ~~Write access~~ **Resolved** for pushing branches. Remaining: branch protection reviewers (B15) | — | Ayoub | No | P3 |
| B3 | Their own test suite (`tests/test_db.py`, `test_ingest.py`) not yet run on Ayoub's machine; it needs a seeded local stack and GoTrue for one live test | Extra assurance only: the schema itself is VERIFIED | Data/AI developer runs it in CI once `AI` is merged | No | P3 |
| B18 | **Push approval for `feat/api-contract-v1`** (local `fb0acc9`) and PR to `main` after PR #1 | The frontend developer needs `contract/openapi.json` on GitHub | Ayoub | Frontend integration | **P0** |
| B19 | **Frontend app decision**: `frontend/` (frontend developer, JS) is the single app; `feat/web-scaffold` (TS) is not pushed as a second app; its API client / flow / proxy are offered for porting | Two competing apps otherwise | Ayoub + frontend developer | Frontend structure | **P0** |
| B20 | Merge order of PR #1, `AI`, contract v1 (reconciliation §5) | `feat/api-supabase` needs `supabase/migrations` in its tree for test scripts and CI | Ayoub | Backend CI only (local work can check out the folder from `origin/AI`) | P1 |
| B4 | ~~Migration M3~~ **Resolved**: M3 and M4 are live (VERIFIED, changelog row 3). **New: M5 `patient_birth_year` awaits Ayoub's review before `db push`** (verified to apply cleanly; adds nullable `patient_profiles.birth_year`, needed for `age` in the contract). Also note M3/M4 were pushed before the review rule existed (disclosed by the data/AI developer) | Age on profile, doctor list and emergency card | Ayoub approves; data/AI applies | No (fields stay null) | P1 |
| B5 | ~~alert_class update, created_by, emergency_events columns~~ **Resolved by live inspection** (contracts §3.1 item 8). Remaining: expected JSON shape inside `emergency_events.actions_attempted` | Phase 8 | Data/AI developer | No | P2 |
| B6 | ~~Create cloud project~~ **Exists**: `pulse` (org `lwiza`, ref `nfmfdhpxipdndggxtqho`, Paris), both migrations applied, tables empty. Remaining: fictional seed (after B9 and B16), and **who applied the migrations and how** (the data/AI inventory says no cloud project existed when it was written) | Shared environment; one migration owner | Ayoub to confirm with the data/AI developer | Seed needed for frontend integration on shared data | P1 |
| B7 | ~~Cloud signing method~~ **Resolved: ES256 via JWKS** (VERIFIED LIVE). Remaining: local stack method (seen from `supabase status` once B1 lands) | Phase 2 config for local tests | Ayoub | No | P2 |
| B16 | ~~Switch off public sign-up~~ **Resolved**: `disable_signup: true` observed live 2026-10-30 (changelog row 6) | — | — | No | — |
| B17 | Exact row counts and `auth.users` count on `pulse` | Estimates say empty; confirm before seeding | Ayoub (SQL editor: `select count(*) from auth.users;`) or next CLI session | No | P3 |
| B8 | Secrets distribution, out of band (never in git or chat logs): FastAPI gets `PULSE_DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, JWT config; data/AI gets `DATABASE_URL` and the service-role key for seeding; frontend gets **nothing** | Least privilege | Ayoub | Phase 10 | P2 |
| B9 | ~~Seed password from env~~ **Resolved** on branch `AI` (`build_seed_sql(password)` from `PULSE_DEMO_PASSWORD`; `seed.sql` not committed) | — | — | No | — |
| B10 | Hackathon clock: exact hours remaining and demo time | Decides cuts (plan §12) and the fallback trigger | Ayoub | Scope decision | P0 |
| B11 | ~~Scaffold feedback~~ Superseded: the frontend developer built `frontend/` (inspected directly; gaps listed in reconciliation §4). Remaining: their confirmation of B19 | — | Frontend developer | No | P1 |
| B12 | Verified emergency number (D3: 14 vs 1021) and the demo substitute number (a teammate's phone) | `GET /config/emergency`; never dial real numbers in tests | Ayoub + medical mentor | No (config value) | P2 |
| B13 | Clinician review: thresholds (≥180/≥120), the 7 red flags vs the 13 recorded symptoms (severe_headache and confusion are not red flags in the current rule), plausibility limits, patient wording | Honest pitch; possible rule changes | Medical mentor | No | P2 |
| B14 | Data/AI developer's ML artefacts once trained: `ml/MODEL_CARD.md`, `metadata.json`, test metrics with baselines | Doctor panel and pitch claims | Data/AI developer | Phase 7 demo content only | P2 |
| B15 | Branch protection on `main` (require PR + CI) | Prevents accidental pushes by three developers | Ayoub (GitHub settings) | No | P3 |

## Conflicts found between the two workstreams (resolved in the architecture, listed for visibility)

| Topic | Backend (VERIFIED) | Data layer (REPORTED) | Resolution |
|---|---|---|---|
| Severe threshold | ≥ 180 / ≥ 120 | `> 180` / `> 120` in starter `rules.py` | ≥ (AHA wording); their `rules.py` deleted |
| Red-flag symptoms | 7 AHA codes | 5 codes; 13 recordable codes, different names | 7 red flags in DB naming |
| Validation ranges | diastolic 30–200, pulse-pressure flag | DB `pulse-v1`: diastolic 25–200, no pulse-pressure rule; their `rules.py` 40–300 / 20–200 | DB trigger authoritative; Python validation removed |
| Invalid readings | rejected 422, not stored | stored, flagged | stored + flagged; API explains |
| Sources | manual/device/imported/simulated | manual/device_sync/csv_import/simulated | DB vocabulary |
| Alert model | episodes with events, 6 states | one row per measurement per rule, 4 states | DB states + M3 for episodes |
| Identity | own users, integer ids, PBKDF2 | Supabase Auth, uuid | Supabase Auth via FastAPI proxy |
| Frontend data access | FastAPI only | PostgREST + supabase-js | FastAPI only |
| Analytics on `needs_review` | excluded (as "questionable") | included | excluded from averages; included in safety rules |
| Doctor note privacy | private note + advice | patient reads whole row (RLS) | API filters; RLS to align (M3 item 6) |
| ML lifestyle features | — | proposed (missed dose, sodium, activity, sleep) | excluded for MVP: not collected by the app |

## Answers to the data/AI developer's access questions (inventory §7)

| Their question | Answer |
|---|---|
| Repo URL and default branch | `https://github.com/Ayoub-Meziani/pulse`, default `main` (protected by convention; only Ayoub merges) |
| Branch / workflow | Push `feat/data-layer`, open a PR to `main`; Ayoub reviews |
| Where the code lives | Same repo: `supabase/`, `pulse_data/` (renamed), `ml/`, `docs/data/` |
| Existing `supabase/` folder in main repo | None (VERIFIED); no merge conflict expected |
| Supabase project | Existing `pulse` in org `lwiza` (ref `nfmfdhpxipdndggxtqho`); your two migrations are already applied there. Future migrations: you write them, Ayoub approves the PR, you `db push` |
| Connection string, service-role key | Shared privately (B8); service-role key never to FastAPI or the frontend |
| Anon key for the frontend | Not needed: the frontend calls FastAPI only (A2); FastAPI uses the anon key server-side for login |
| `seed.sql` on the shared project | Fictional seed allowed on `pulse` only, password from env (B9) |
| Email confirmation | Sign-up disabled; accounts created by seed tooling, so confirmation is not needed |

## New (audit 2026-10-30, `AI` `0505993`)

| # | Item | Why | Who | Blocks? | Priority |
|---|---|---|---|---|---|
| B21 | M6 was applied to `pulse` without backend review | Breaks the sync policy's approval rule; this time the change is additive and verified | Ayoub to remind the data/AI developer: write migration → PR → Ayoub approves → `db push` | No | P1 |
| B22 | Contract decision for M6 data (sex, smoking, condition codes, salt habits, preferred language, body measurements, wearable samples) | Not in contract v1; frontend profile screens may want them; wearable data must never feed rules or alerts | Ayoub | No (additive) | P2 |
| B23 | Seeded `pulse` has readings but 0 alerts | Doctor views will be empty until the backend replay job (plan step 9) runs our rules over the seed | Ayoub (backend) | Demo only | P1, **deferred 2026-10-30** (Ayoub: frontend integration first) |
| B24 | **Symptom-to-reading link request** (status 2026-10-30, `AI` `6681979`: **no proposal received yet**. The name "M7" is now used on `AI` for `ml_monitoring`, so this migration needs a new number/timestamp): `symptom_reports.measurement_id uuid` with same-patient composite FK `(measurement_id, patient_id) → measurements (id, patient_id)` | Contract v1 links a symptom check to the reading that triggered it; the column does not exist (VERIFIED in M1–M6), so the API validates and drops it | Data/AI developer writes M7 → Ayoub reviews → `db push`; backend then stores and returns it | No | P2 |
| B25 | ~~CI failure~~ **Resolved**: run 41011435521 on `ab778d8` passed (both DBs built, suite and contract green). Was: CI run 41009335018 (`52b4d02`) failed after 2 s in the test-database step (tests never ran); passes locally. `a97d5e2` adds pull retries + Docker Hub fallback + public error annotations | Unverified CI on the step-5 commit | Next approved push re-runs CI | Merge readiness | P1 |
| B26 | Proposed backend rule **R-RING-1** (ring SpO2 median < 94 % over 10 min → prompt cuff reading + symptom check) in `ml/pulse_ml/reference.py` on `AI` `b988e1a` | Would make wearable data trigger patient guidance, which the current rule (wearables kept separate from the deterministic alert rules) forbids; reference values are pending clinician review | Ayoub decides; clinician review first | No (not implemented) | P2 |
| B27 | `ml_predictions` on `pulse` is empty | The doctor prediction panel shows `model_unavailable` until `pulse_ml.predict --all` runs against `pulse` (after the step 9 replay) | Data/AI developer, with Ayoub's go | Demo only | P2, **deferred 2026-10-30** (with step 9) |
| B28 | ~~Approval of live `20261030150000_ml_monitoring`~~ **Resolved 2026-10-30: Ayoub personally approved the migration.** It is already applied and verified (382/382); it is not reapplied or modified | None | Ayoub | No | Closed |
| B29 | `20261030160000_chronic_conditions` ("M8") on `AI`, not applied; widens `condition_codes` (drop + re-add of the CHECK, additive in effect) | Needs review and Ayoub's approval before `db push`; `ProfileIn` validation of codes would need the new list | Ayoub | No | P2 |
| B30 | Privacy of doctor notes at the database level: RLS `doctor_notes_read` lets **admin** read note rows, and `audit_log` (admin-readable) stores full note text in `old_data`/`new_data` | The API blocks admin (403) and never exposes `audit_log`, but a direct database client with an admin account could read notes | Ayoub decides; possible future migration: drop admin from `doctor_notes_read`, redact `note` in the audit copy | No | P2 |
| B31 | `AI` `docs/data/MIGRATIONS.md` states R-RING-1 "is evaluated by the backend directly on `wearable_samples`" | Not true: R-RING-1 is **not implemented** and stays disabled (B26, clinician review); no wearable data reaches the rules | Data/AI developer to correct the doc | No | P3 |

