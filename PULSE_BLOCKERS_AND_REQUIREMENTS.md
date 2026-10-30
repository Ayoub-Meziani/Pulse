# PULSE blockers and requirements

Status: 2026-10-30. Lists only what is **not** already available in the repository or in the data/AI developer's documents.
Priority: **P0** = blocks starting the parallel work, **P1** = blocks a specific phase, **P2** = needed before the demo, **P3** = can wait.

## Are the materials sufficient to start?

**Yes for contract work and planning; not yet for database integration.**
- Enough is known to start backend task 1.1 (contract v1) and the frontend adaptation immediately.
- Backend Phase 1.3+ (Postgres integration) cannot start reliably until the data layer code is in the repository and runs on Ayoub's machine. Everything about the Supabase schema is currently **REPORTED** from documents; no migration, SQL export or test was supplied or run here.

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
| B1 | **The data/AI developer's code in our repository**: PR `feat/data-layer` to `https://github.com/Ayoub-Meziani/pulse` with `supabase/config.toml`, `supabase/migrations/*.sql`, `pulse_analysis/` (renamed `pulse_data/`, without `rules.py`), `tests/`, `requirements.txt`, `samples/`, docs → `docs/data/`. Not `seed.sql` with a password, not `data/synthetic/`. | Their repo has 0 commits and no remote; every schema fact is unverified; Phase 1 maps their tables | Data/AI developer (Ayoub grants write access to the repo first) | **Yes**, Phase 1.3+ | P0 |
| B2 | GitHub write access for the data/AI and frontend developers (their usernames) | B1 and the frontend PR | Ayoub | Yes for B1 | P0 |
| B3 | A run of their tests on Ayoub's machine: `npx supabase@2.122.0 start`, `supabase db reset`, `pytest` (their 48 tests, last run 29 Oct) | Converts REPORTED to VERIFIED; triggers the fallback if it fails within 2 h | Ayoub (with data/AI developer available) | Yes, Phase 1 acceptance | P0 |
| B4 | **Migration M3** (`backend_alignment`, contracts §3.1): `above_target_trend` class, `alerts.persistent`, `alerts.resolution_note`, `alert_measurements` table, `measurements.rested_5_min`, `doctor_notes` patient visibility | Our alert episodes (R-SEV-2/3, R-EMG-1 raise) cannot be stored in the current `alerts` table | Data/AI developer | Yes, Phase 5 | P1 |
| B5 | Answers to contracts §3.1 item 7: can `alert_class` be updated; does the `created_by` trigger accept claims set on a privileged connection; exact `emergency_events` columns (location, outcome, `actions_attempted` shape) | Phases 4, 5, 8 write these columns | Data/AI developer (answer in `DATA_SCHEMA.md`) | Yes, Phases 4/5/8 | P1 |
| B6 | Cloud project `pulse-demo` (Supabase, region close to Algeria, e.g. eu-central), with **sign-up disabled**, migrations applied, fictional seed; project ref shared with the team | Shared environment for frontend integration and the demo; the two existing projects in the account are unrelated and must not be used | Ayoub creates (account owner); data/AI developer applies migrations and seed | Yes, frontend integration on shared data + Phase 10 | P1 |
| B7 | Which JWT signing method the local stack (CLI 2.122.0) and `pulse-demo` use (HS256 secret vs asymmetric/JWKS) | Phase 2 token verification config | Ayoub checks `supabase status` output / a decoded token header | Yes, Phase 2 (code supports both, config needed) | P1 |
| B8 | Secrets distribution, out of band (never in git or chat logs): FastAPI gets `PULSE_DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, JWT config; data/AI gets `DATABASE_URL` and the service-role key for seeding; frontend gets **nothing** | Least privilege | Ayoub | Phase 10 | P2 |
| B9 | Seed generator reads the demo password from `PULSE_DEMO_PASSWORD`; generated `seed.sql` git-ignored | Known password must not be committed or pushed to a public project | Data/AI developer | Before seeding `pulse-demo` | P2 |
| B10 | Hackathon clock: exact hours remaining and demo time | Decides cuts (plan §12) and the fallback trigger | Ayoub | Scope decision | P0 |
| B11 | Frontend developer's feedback on the scaffold (structure, routing, styling, data fetching, types, flow, token storage, next screens, tooling, Claude Code use) | Structural adjustments to `web/` before they build on it | Frontend developer via Ayoub | Frontend only | P1 |
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
| Supabase project | New `pulse-demo`, created by Ayoub (B6); data/AI developer applies migrations after approval |
| Connection string, service-role key | Shared privately (B8); service-role key never to FastAPI or the frontend |
| Anon key for the frontend | Not needed: the frontend calls FastAPI only (A2); FastAPI uses the anon key server-side for login |
| `seed.sql` on the shared project | Fictional seed allowed on `pulse-demo` only, password from env (B9) |
| Email confirmation | Sign-up disabled; accounts created by seed tooling, so confirmation is not needed |
