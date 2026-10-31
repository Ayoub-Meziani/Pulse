# PULSE — V1 and staging handoff

Date: 2026-10-31. Author: Claude Code for Ayoub. Applies to `main` after the merge of `feat/v1-completion`.
Read with `docs/PULSE_SCOPE_AUDIT.md` (what was specified versus built) and `docs/LOCAL_DEVELOPMENT.md` (run it).

## 1. Scope and audit conclusion

PULSE V1, as specified in `docs/conception.pdf` v0.9, is a hypertension follow-up and emergency-support web app:
manual readings checked by deterministic rules, a short emergency flow, and doctor follow-up. Sport and food
were specified only as journal entries (MVP) and optional, clinician-reviewed general guidance cards; structured
activity/meal tracking exists in the database (`lifestyle_logs`, from the data/AI work) but was never agreed for
the product. Details and sources: `docs/PULSE_SCOPE_AUDIT.md`.

**Conclusion:** every MVP item of the conception that has an agreed API is now built. What is left is either
"if time" in the conception, a V2 item, or blocked on a decision (Q1–Q7 in the audit).

## 2. Implemented features (end to end, real API data)

| Area | Features |
|---|---|
| Readings | Manual entry with context; repeat-safe submission; database validation (valid / to check / invalid); provenance on every reading; history, chart with target, 7/30-day summary with provenance counts |
| Safety rules | R-TGT-1, R-TRD-1 (simulated readings excluded), R-SEV-1/2/3 with symptom check and 60-s recheck, R-EMG-1; alerts with acknowledge (patient) and review / close with note (doctor) |
| Emergency | Urgence button everywhere; call button (demo number in demo mode; real numbers shown as text); FR + AR text; medical card; trusted-contact call; position shared only on tap, stored only with consent; share sheet / SMS composer / clipboard; outcome; incident record of taps (never "call made"); offline cache of config and card |
| Journal | Patient entries: food, physical activity, symptoms, medication, question for the doctor; doctor marks read and answers through note advice |
| Doctor | Assigned patients by urgency (refresh every 15 s), patient record: overview, readings incl. invalid, symptoms, alerts, emergency episodes with report, journal, wearable data, experimental estimate (doctor only), private notes + advice, care-plan editing |
| Patient profile | View and edit (full replace), trusted contacts add (with consent) / deactivate / delete, care plan view, doctor advice on the dashboard |
| Wearables | Optional; devices and samples labelled, separate from blood pressure, never an alert input |
| Admin | Account and published emergency configuration only (the API gives admins no medical records) |

## 3. Missing and why

| Item | Why |
|---|---|
| Structured activity / meal / sodium / sleep tracking | Never agreed (B22, D-11). Decision Q1 |
| General guidance cards (activity, salt, sleep) | "If time" in the conception; needs sourced content and clinical sign-off. Q3 |
| Medications and adherence, body measurements, M6 diet-habit profile fields | Database only; display decisions Q2, Q4 |
| Alert dismiss / escalated states, alert event timeline | Not in the built contract; Q5 |
| Symptom ↔ reading link | Needs a migration (B24) |
| Daily morning/evening means | Contract stub, deferrable |
| Lock-screen card, Medical ID guide, attention sound, ED map link, reminder banner, AI weekly summary | "If time" in the conception → V2 |
| Weekly reports, ring flags, band approval, live early warnings (M9, live-v1) | ML work on branch `AI`; no endpoints; clinical review; M9 approval Q6 |

## 4. Sport and nutrition status

- **Built:** food and physical-activity notes in the journal (patient writes, doctor reads and marks read).
  PULSE does not analyse them and gives no diet or exercise advice; they never trigger an alert.
- **Not built, decision needed:** structured activity and meal logs, sodium tracking, diet-habit profile fields,
  general guidance cards (Q1–Q3).
- **Out of scope:** personalised diet or exercise prescriptions, nutrition analysis or AI nutrition advice.

## 5. Environments

| Environment | State |
|---|---|
| Local | Working. `scripts/dev_stack.py` (Supabase Postgres 17.11.0.003, GoTrue v2.197.0 signing ES256, Kong 2.8.1) on 127.0.0.1, migrations up to `LIVE_UNTIL` (M9 since 2026-10-31). Fictional accounts via `scripts/dev_seed.py` |
| Staging | **Not created — blocked on Q7.** No staging project exists. The Supabase CLI login of this machine sees two organisations: `lwiza` (holds production `pulse`) and Ayoub's personal organisation. Creating a project is a billable/organisational decision; a staging project inside `lwiza` would also be reachable by the accounts that applied unapproved changes to production |
| Production | Supabase `pulse` (ref `nfmfdhpxipdndggxtqho`). Not touched by this work except read-only checks. **Now M1–M9** (M9 applied by someone else, see incident §10d). No API or frontend is deployed |

### Staging runbook (to execute once Q7 is answered)

1. Ayoub creates (or authorises the creation of) a Supabase project `pulse-staging` in the chosen organisation,
   region eu-west-3, with a database password kept in his password manager. Keep the ref and
   any credential out of the repository (for example in `.dev/staging-ref`; `.dev/` is git-ignored).
2. Positive target check before any write: the ref must differ from `nfmfdhpxipdndggxtqho`, and
   `supabase projects list` must show it in the expected organisation with name `pulse-staging`.
3. Migrations: from a scratch folder outside the repository containing a copy of `supabase/config.toml` and
   **only** the migration files up to `LIVE_UNTIL` (as `dev_stack.py` does), run `supabase link --project-ref
   <staging ref>`, `supabase migration list --linked` (empty), `supabase db push --linked --dry-run`, review,
   then `supabase db push --linked`. Verify: history = M1–M9, schema dump vs the M1–M9 test database with
   `scripts/compare_schemas.py` = 0 differences, RLS on every table, no grants to `anon`.
   Staging mirrors production M1–M9 (Ayoub, Q7, 2026-10-31). Full procedure: `docs/STAGING_SETUP.md`.
4. Auth: enable ES256 signing keys in the staging project (Authentication → JWT signing keys), disable public
   sign-up, keep email confirmation off for the provisioned accounts.
5. Accounts: create Patient A, Patient B and the doctor with the Auth admin API or the dashboard (passwords
   generated and stored in a password manager), set roles and assignments in SQL, then load the same fictional
   data as `dev_seed.py` through the staging API (a staging variant of the seed script, guarded by the ref
   check, is the next tooling task).
6. Staging API: any container host with HTTPS; environment = `PULSE_ENV=staging`, `PULSE_DATABASE_URL`
   (session pooler of the staging project, `aws-1-eu-west-3`), `SUPABASE_URL`, `SUPABASE_ANON_KEY` (staging
   publishable key), `PULSE_DEMO_MODE=true`, `PULSE_DEMO_NUMBER` (a team phone). No service-role key in the API.
7. Staging frontend: `npm run build` with the API behind the same origin (reverse proxy `/api` → API), HTTPS
   (required for location on phones).
8. Acceptance on staging: the API acceptance script and the browser scenarios of section 9, then record the
   results here.

## 6. Database migrations

| Version | Name | Local dev stack | Test profile `live` | Test profile `latest`, CI | Production `pulse` |
|---|---|---|---|---|---|
| M1–M7 | core … ml_monitoring | ✓ | ✓ | ✓ | ✓ |
| M8 `20261030160000` | chronic_conditions | ✓ | ✓ | ✓ | ✓ (applied before review, incident) |
| M9 `20261030170000` | live_early_warning | ✓ (since 2026-10-31) | ✓ (`LIVE_UNTIL`) | ✓ (since PR #4) | ✓ (applied between 21:47 and 22:58 UTC on 30 Oct without Ayoub's confirmed approval; kept by decision, not approved retroactively) |

The backend does not use M9. `LIVE_UNTIL` = M9 since 2026-10-31 (Q6: keep). Nothing writes `early_warning` flags (live-v1 inactive).

## 7. Demo accounts (local)

`patient.a@demo.pulse.test`, `patient.b@demo.pulse.test`, `medecin@demo.pulse.test`: fictional, created by
`python scripts/dev_seed.py` on the local stack. Passwords are random, written only to
`.dev/demo-credentials.txt` (git-ignored) in the folder where the seed ran; open that file to read them. They are
never printed, committed or reused. Staging accounts will be provisioned separately (section 5, step 5).

## 8. Architecture

Browser (React + Vite, French UI, AR on the emergency screen) → FastAPI (`/api/v1`, the only authority for
authentication and authorization; verifies Supabase Auth ES256 tokens via JWKS) → Supabase Postgres (RLS as a
second defence). The browser never talks to Supabase. No ML runs in the API; stored estimates are read for
doctors only. Deterministic rules live in `api/app/analysis` and never read wearable, journal or ML data.

## 9. Test evidence

| Check | Result |
|---|---|
| Backend, test DB `live` (M1–M8) | 429 passed |
| Backend, test DB `latest` (M1–M9, as CI) | 429 passed |
| Backend without a database | 129 passed, 300 skipped |
| OpenAPI freshness | re-export identical |
| Frontend lint / unit tests / build | clean / 35 passed / built |
| API acceptance on the local stack (earlier run, before this branch) | 34/34: isolation, reading, repeat-safe (also concurrent), invalid, severe → emergency, doctor scope, unassigned 403, no-wearable, simulated wearable, provenance counts, private notes |
| Browser, local stack (this branch, QA accounts later removed) | Patient: journal (activity entry saved and listed), profile edit (allergy), trusted contact added with consent, emergency screen (demo number + consented contact only, card with the edited allergy, outcome recorded; incident stored once with `screen_opened` and `outcome_reported`), sign-out clears the cached emergency data. Doctor: journal entry marked read, emergency episode report with honest timeline, care plan set to 135/85, all record tabs and the list at 390 px without horizontal overflow |
| Not verified in a browser | Tapping `tel:` links and the location share (they open system dialogs; the logging code is covered by the incident-queue tests); offline mode on a phone; admin screen (no admin account); staging (does not exist) |

## 10. Security and clinical limitations

- Not a medical device; thresholds, symptom list and texts are not clinically validated (B13, S2); alert texts are English.
- Emergency number 14 is unverified; demo mode is on by default and dials only the configured demo number.
- PULSE never calls, texts or alerts anyone; the doctor is not notified in real time.
- Location is requested only when the patient taps "Partager ma position" and stored only with consent.
- The emergency card and unsent incident steps are cached on the device until sign-out (shared-device risk).
- Tokens are kept in `sessionStorage`; no logout endpoint (refresh token valid until expiry); no login rate limiting.
- Admin can read doctor notes through direct database access (RLS), not through the API (B30).
- Production holds changes applied without approval (incident report).

## 11. Git

| Branch / commit | Content |
|---|---|
| `ef4ec39` | Scope audit + incident addendum 10d |
| `9b541a0` | Journal API + tests |
| `95272f2` | Frontend V1 gaps (emergency workflow, journal, profile, care plan, doctor tabs) |
| merge of `origin/main` (`2c3d25b`, PR #4) into `feat/v1-completion` | integration test with the AI merge |
| this document | handoff |
| merge `feat/v1-completion` → `main` | see `git log --first-parent main` |

No force-push, no history rewrite, no branch deletion. PR #4 was not reverted (Q6).

## 12. CI

GitHub Actions `CI`: backend (both test profiles + contract freshness) and frontend (lint, tests, build). Status of
the final `main` commit is reported in the delivery message.

## 13. Commands

Local: see `docs/LOCAL_DEVELOPMENT.md` (`dev_stack.py up` → `dev_seed.py` → `dev_api.py` → `npm run dev`,
http://localhost:5173). Staging: section 5 (not yet available).

## 14. Rollback

- Code: `git revert -m 1 <merge commit>` on `main` (new commit, no history rewrite); redeploy nothing (no deployment exists).
- Local data: `python scripts/dev_stack.py down` then `up` + `dev_seed.py`.
- Database: no migration was added by this work. M9 rollback, if Ayoub decides it, needs a new migration that
  restores the M7/M8 constraint lists (only after checking that no `early_warning` row exists).

## 15. Blockers before production

1. Q6: M9 / PR #4 decision; restore the approval process for migrations and `main` (branch protection, reviews).
2. Q7: staging project, hosting, HTTPS.
3. Clinical review of thresholds, symptom list, wording, French translation of alert texts; emergency number.
4. Login rate limiting, logout endpoint, token storage review.
5. Decisions Q1–Q5 for the remaining modules.
