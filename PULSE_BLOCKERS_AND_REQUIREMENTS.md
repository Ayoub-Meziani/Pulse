# PULSE blockers and requirements

Status: 2026-10-30. Lists only what is **not** already available in the repository or in the data/AI developer's documents.
Priority: **P0** = blocks starting the parallel work, **P1** = blocks a specific phase, **P2** = needed before the demo, **P3** = can wait.

## Are the materials sufficient to start?

**Yes for the API contract and for database integration against the cloud schema; local tests still need the migration files.** (Updated after the live inspection of project `pulse`, architecture §12.)
- Backend task 1.1 (contract v1) and the frontend adaptation can start immediately.
- The schema is now **VERIFIED LIVE**, so model mapping (task 1.4) can start against it.
- Running the backend tests locally (task 1.6) and CI still need `supabase/migrations/*.sql` in the repo (B1). Do not reconstruct the migrations from the dump ourselves: that would create a second, conflicting history.
- Before any real account or data goes into the cloud project, public sign-up must be switched off (B16).

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
| B1 | **The data/AI developer's code in our repository**: PR `feat/data-layer` to `https://github.com/Ayoub-Meziani/pulse` with `supabase/config.toml`, `supabase/migrations/*.sql`, `pulse_analysis/` (renamed `pulse_data/`, without `rules.py`), `tests/`, `requirements.txt`, `samples/`, docs → `docs/data/`. Not `seed.sql` with a password, not `data/synthetic/`. | Schema is VERIFIED LIVE, but the migration files, importer, simulator and tests exist only on their machine; local stack, tests and CI need them; one migration history in git | Data/AI developer (Ayoub grants write access to the repo first) | **Yes**, Phase 1.3+ | P0 |
| B2 | GitHub write access for the data/AI and frontend developers (their usernames) | B1 and the frontend PR | Ayoub | Yes for B1 | P0 |
| B3 | A run of their tests on Ayoub's machine: `npx supabase@2.122.0 start`, `supabase db reset`, `pytest` (their 48 tests, last run 29 Oct) | Converts REPORTED to VERIFIED; triggers the fallback if it fails within 2 h | Ayoub (with data/AI developer available) | Yes, Phase 1 acceptance | P0 |
| B4 | **Migration M3** (`backend_alignment`, contracts §3.1): `above_target_trend` class, `alerts.persistent`, `alert_measurements` table, `measurements.rested_5_min`, allow empty `symptoms`, `doctor_notes` patient visibility, explicit REVOKEs (live default privileges grant ALL to `anon` on new tables). `alerts.resolution_note` already exists live. | Our alert episodes (R-SEV-2/3, R-EMG-1 raise) cannot be stored in the current `alerts` table | Data/AI developer | Yes, Phase 5 | P1 |
| B5 | ~~alert_class update, created_by, emergency_events columns~~ **Resolved by live inspection** (contracts §3.1 item 8). Remaining: expected JSON shape inside `emergency_events.actions_attempted` | Phase 8 | Data/AI developer | No | P2 |
| B6 | ~~Create cloud project~~ **Exists**: `pulse` (org `lwiza`, ref `nfmfdhpxipdndggxtqho`, Paris), both migrations applied, tables empty. Remaining: fictional seed (after B9 and B16), and **who applied the migrations and how** (the data/AI inventory says no cloud project existed when it was written) | Shared environment; one migration owner | Ayoub to confirm with the data/AI developer | Seed needed for frontend integration on shared data | P1 |
| B7 | ~~Cloud signing method~~ **Resolved: ES256 via JWKS** (VERIFIED LIVE). Remaining: local stack method (seen from `supabase status` once B1 lands) | Phase 2 config for local tests | Ayoub | No | P2 |
| B16 | **Switch off public sign-up on `pulse`**: Dashboard → Authentication → Sign In / Providers → "Allow new users to sign up" = off. Live today: `disable_signup: false` | With the publishable key (public by design) anyone can register and receive a `patient` profile. I could not change it safely: the dashboard session had expired (not signing in on your behalf) and `supabase config push` would overwrite the whole remote auth config from a local file we do not have | **Ayoub** (2 minutes) | Must be done before seeding or sharing the URL | **P0** |
| B17 | Exact row counts and `auth.users` count on `pulse` | Estimates say empty; confirm before seeding | Ayoub (SQL editor: `select count(*) from auth.users;`) or next CLI session | No | P3 |
| B8 | Secrets distribution, out of band (never in git or chat logs): FastAPI gets `PULSE_DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, JWT config; data/AI gets `DATABASE_URL` and the service-role key for seeding; frontend gets **nothing** | Least privilege | Ayoub | Phase 10 | P2 |
| B9 | Seed generator reads the demo password from `PULSE_DEMO_PASSWORD`; generated `seed.sql` git-ignored | Known password must not be committed or pushed to a public project | Data/AI developer | Before seeding `pulse` | P2 |
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
| Supabase project | Existing `pulse` in org `lwiza` (ref `nfmfdhpxipdndggxtqho`); your two migrations are already applied there. Future migrations: you write them, Ayoub approves the PR, you `db push` |
| Connection string, service-role key | Shared privately (B8); service-role key never to FastAPI or the frontend |
| Anon key for the frontend | Not needed: the frontend calls FastAPI only (A2); FastAPI uses the anon key server-side for login |
| `seed.sql` on the shared project | Fictional seed allowed on `pulse` only, password from env (B9) |
| Email confirmation | Sign-up disabled; accounts created by seed tooling, so confirmation is not needed |
