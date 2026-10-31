# PULSE V1 — release audit (phase A), staging proposal (phase B), Q5 proposal (phase C)

Date: 2026-10-30 (23:39 UTC read-only checks; local time 31 Oct 00:39). Author: Claude Code for Ayoub. Base: `main` `e9c9c28`.
Scope of this document: read-only investigation, local analysis and plans. **Nothing was created, applied,
reverted, deployed or written to any cloud database.**

Labels: **FACT** (checked, method named) · **CLAIM** (stated by someone, not confirmed) · **INFERRED** ·
**DECISION NEEDED**.

> **Decisions recorded 2026-10-31 (Ayoub).** Q6: keep M9, no revert, not approved retroactively; `LIVE_UNTIL`
> moved to M9 (local only, `docs/engineering/PULSE_SUPABASE_CHANGELOG.md` rows 15–16). Q7: staging `pulse-staging` in `lwiza`,
> eu-west-3, M1–M9 mirrored, nothing created until Ayoub authorizes it (`docs/STAGING_SETUP.md`). Q5: plan only
> (`docs/proposals/M10_ALERT_DISMISSAL.md`). Q1–Q4 deferred. Sections below are the audit as written.

---

## 1. PR #4 audit (`AI` → `main`, merge `2c3d25b`)

FACT (`git diff 00ea3b2 2c3d25b`): 67 files, +9,662 / −226. **No file under `api/`, `frontend/`, `contract/`,
`.github/`, `CLAUDE.md` or the backend docs changed.** `00ea3b2` already contained the reviewed data layer up to
`0505993`; PR #4 added the `AI` commits after it (`b988e1a` … `74b55af`).

| Change in `main` | Files | Classification | Reason |
|---|---|---|---|
| Migration M9 `20261030170000_live_early_warning.sql` | `supabase/migrations/` | **Requires further review** (incident) | Applied to production without your approval. Additive, unused (0 rows). Applied by CI's `latest` test profile only; local dev stack and `live` test profile stop at M8 (`LIVE_UNTIL`) |
| Cloud scripts `scripts/cloud_update.ps1`, `scripts/run_cloud_jobs.ps1` | `scripts/` | **Not suitable for production** as they stand | `cloud_update.ps1` runs `db push --linked` with an automatic "y" and DELETEs/UPDATEs demo data; `run_cloud_jobs.ps1` writes ML tables with a CLI login and `set role postgres` (bypasses RLS). Manual only, no schedule. Keep in the repo, do not run (freeze) |
| ML jobs `ml/pulse_ml/{predict,monitor,weekly,feedback,jobs}.py` | `ml/` | **Integrated but inactive** | Run only when someone starts them; write `ml_predictions`, `wearable_flags`, `weekly_reports`, `patient_bands` to whatever `DATABASE_URL` the shell holds (no confirmation flag) |
| Live early-warning engine `live-v1` (`ml/pulse_ml/live.py`, `monitor --follow`) + artifact | `ml/` | **Integrated but inactive; requires clinical review** | Would write `early_warning` flags (M9). Simulator-only results. Never started in production (0 rows) |
| Retrained models `mbp-v1.1`, `ring-v1.1`, `wcls-v1.1`, `mbp-v2.1`, `wrisk-v1`; **`mbp-v1` artifact deleted** | `ml/artifacts/` | **Requires further review** | API serves `mbp-v1` (see §3); `mbp-v1.1` never reviewed for serving |
| Real-data tooling (`real_data.py`, NHANES bands, backtest) | `ml/` | **Integrated but inactive** | Offline analysis; downloads only when run manually |
| Simulators `pulse_data/live_sim.py`, `pulse_data/stream.py` (+ `simulate.py` changes) | `pulse_data/` | **Integrated but inactive** | `stream.py` refuses a non-local database without `--i-confirmed-cloud` (unlock removed on `feat/demo-complete`, D26: no unlock); `simulate.py ring-demo-sql` generates SQL (not executed by itself) |
| Data/ML docs (`docs/data/*`, reports, PDFs, `MODEL_CARD.md`) | `docs/data`, `ml/` | **Requires further review** | Contain claims of approvals and a mentor review that are not confirmed (incident report) |
| Tests `ml/tests/*`, `tests/*` | `ml/tests`, `tests/` | **Integrated and safe** | Not run by CI; default to local databases; one test deletes `wearable_flags` inside a rolled-back transaction (hazard if pointed at cloud) |

**Nothing from PR #4 is reachable through the API or the frontend.** No scheduled job exists: CI triggers only
on push / pull request; no GitHub schedule, no Windows scheduled task on this machine (earlier check).

## 2. M9 incident and database synchronization

| Check (2026-10-30 ≈23:39 UTC) | Result | Method |
|---|---|---|
| Live migration ledger | 9 versions: M1–M9 | `supabase migration list --linked` (read-only) |
| Live schema vs `main` migrations M1–M9 | **382 / 382 statements identical** | schema-only dump vs throwaway DB built from `main` (`scripts/compare_schemas.py`) |
| Live schema vs M1–M8 (`LIVE_UNTIL`) | 381 / 382: the only difference is the `wearable_flags` CHECKs added by M9 | same |
| Rows using M9 (`kind = 'early_warning'`) | 0 | read-only SELECT |
| Writes since 30 Oct 18:42 UTC | none (max timestamps unchanged in every checked table; no `audit_log` rows after 22:00 UTC) | read-only SELECT |
| Production data (fictional demo) | 14 accounts, 730 simulated readings, 20,832 simulated ring samples, 33 flags, 11 weekly reports, 43 proposed bands, 11 predictions (`mbp-v1.1`), 3 journal entries, 0 alerts, 0 emergency events | read-only SELECT |

**Histories compared**

| | M1–M8 | M9 |
|---|---|---|
| Production ledger and schema | ✓ | ✓ (unapproved) |
| `main` repository | ✓ | ✓ (via PR #4) |
| Backend test profile `live` / local dev stack | ✓ | ✗ (`LIVE_UNTIL` = M8) |
| Test profile `latest` / CI | ✓ | ✓ |
| Sync records (`docs/engineering/PULSE_SUPABASE_CHANGELOG.md`, sync policy §5) | ✓ | recorded only in the incident report (§10d) |

**Corrective synchronization plan (no production action needed for consistency):**

1. Repository and production already agree (M1–M9). No migration has to be applied or reverted to make them consistent.
2. Pending your decision on M9:
   - **Keep M9 (recommended while it stays unused):** move `LIVE_UNTIL` to `20261030170000` so the local stack
     and the `live` test profile match production; record the approval and the verification in
     `docs/engineering/PULSE_SUPABASE_CHANGELOG.md` and the sync policy. The feature it serves (`live-v1`) stays inactive.
   - **Remove M9:** a new forward migration (M10) restoring the M7/M8 CHECK lists, applied only after confirming
     0 `early_warning` rows. Never edit or delete the M9 file (append-only history).
3. Process: protect `main` (pull requests, review by you, CI required); restrict who can run `db push` on
   `pulse` (Owner/Admin roles in `lwiza`); require a changelog row before any production migration.
4. Hazard to remove: `C:\Users\CC USER\pulse\.env` (worktree on `feat/api-supabase`) holds a production
   `DATABASE_URL`; `run_cloud_jobs.ps1` reads `.env` from the folder it runs in. Keep it as instructed, but do not
   check out `main` in that folder, or move the file out of the repository folder (your decision).

## 3. API / model-version compatibility

| Item | State |
|---|---|
| API setting | `PULSE_ML_MODEL_VERSION`, default `mbp-v1` (`api/app/config.py`) |
| Production rows | 11 × `mbp-v1.1` (10 `ok`, 1 `insufficient_history`), target 2026-10-31 |
| Repository artifacts | `mbp-v1` deleted by PR #4; `mbp-v1.1` present |
| Result today | `GET /patients/{id}/predictions/latest` → `model_unavailable` for every patient (doctor sees "Aucune estimation disponible"). From 1 Nov (Algiers) the `mbp-v1.1` rows are stale anyway |
| Compatibility of `mbp-v1.1` rows with the API | Technically compatible (same table, target, 21 features, interval columns). Only the setting decides |
| Safety | Estimates are doctor-only, labelled experimental, never used by rules; `model_unavailable` is handled |

**Recommendation for V1:** leave `mbp-v1` (estimates unavailable) — V1 does not depend on ML. Serving `mbp-v1.1`
needs its own review and a recurring job, which is cloud ML activity (approval required).

## 4. Staging project under `lwiza` (proposal — nothing created)

| Setting | Proposal |
|---|---|
| Organization / name | `lwiza` / `pulse-staging` |
| Region | `eu-west-3` (Paris), same as production |
| Postgres | Supabase default for new projects (17.x); production runs 17.11.0.003 |
| Compute | Free: Nano. Pro: Micro (covered by the plan's $10 compute credit only if production is not already using it) |
| Auth | Sign-up **disabled**; email confirmations off for provisioned accounts; **ES256 JWT signing key** enabled (the API rejects HS256); site URL = staging frontend URL |
| Data | Fictional demo accounts and data only (same scenarios as `scripts/dev_seed.py`), created through Auth + the API |

**Cost and limits** (Supabase pricing and billing docs):
- Free plan: two active free projects per user, counted across all organizations where that user is Owner or
  Administrator; paused projects do not count; free projects pause after 1 week without activity; 500 MB
  database. **Your account already has two active projects (`qabas` in your personal organization, `pulse` in
  `lwiza`)**, so a free `pulse-staging` would require pausing one of them, or another Owner creating it — to check.
- Pro plan: $25/month per organization including one project's compute; each additional project ≈ $10/month
  (Micro, billed hourly); Pro projects do not pause; spend cap on by default.
- I could not read `lwiza`'s plan or the members' roles from the CLI: **check Billing and Team in the dashboard**.

**Access:** on Free/Pro, organization members' roles apply to every project of the organization; per-project
roles are a higher-tier feature (to confirm on the plan page). So everyone in `lwiza` would see both `pulse` and
`pulse-staging`. Isolation therefore rests on: separate credentials, separate keys, no shared `.env`, and limiting
Owner/Administrator roles to the people allowed to push migrations.

**Secrets and environment variables (never in the repository; password manager + host env; locally a
git-ignored `.dev/staging.env`):**

| Variable | Staging value source |
|---|---|
| `PULSE_ENV` | `staging` |
| `PULSE_DATABASE_URL` | session pooler URI of `pulse-staging` (password set at creation) |
| `SUPABASE_URL` | `https://<staging ref>.supabase.co` |
| `SUPABASE_ANON_KEY` | staging publishable key (login proxy only) |
| `PULSE_DEMO_MODE` / `PULSE_DEMO_NUMBER` | `true` / a team phone |
| `PULSE_ML_MODEL_VERSION` | unset (`mbp-v1`, estimates unavailable) |
| Never set | service-role key in the API, any production value |

**Migration initialization plan:**
1. Positive target check: ref ≠ `nfmfdhpxipdndggxtqho`, project name `pulse-staging`, organization `lwiza`.
2. From a scratch folder outside the repository with a copy of `supabase/config.toml` and the approved migration
   files only: `supabase link --project-ref <staging>`, `migration list --linked` (empty),
   `db push --linked --dry-run`, review, `db push --linked`.
3. Which history — **DECISION NEEDED:** M1–M8 (approved only) or M1–M9 (mirror of production). Recommended:
   mirror production (M1–M9) so staging tests what production runs; requires your approval of M9 for staging.
4. Verify: ledger, schema dump vs the throwaway database (0 differences), RLS on all tables, no `anon` grants.
5. Provision accounts (Auth admin API from your machine, passwords in a password manager), roles and assignments
   by SQL, data through the staging API. Then Phase D tests.

**Dependencies / risks:** where to run the staging API and frontend (no host chosen; for Phase D they can run
locally against the staging database and Auth); free-plan pause after inactivity; org-wide access; the CLI
links per folder, so a wrong folder could target production — mitigated by the ref check and a dedicated folder.

## 5. Q5 — alert dismissal and event timeline (proposal, not implemented)

**Current architecture (FACT, code + schema):**
- States `open → acknowledged → reviewed → resolved`; `acknowledged` by the patient or the assigned doctor,
  `reviewed` and `resolved` by the assigned doctor; resolving severe/emergency needs a note
  (`api/app/services/alerts.py`, CHECKs `alerts_status_check`, `alerts_check*`).
- Who/when: `acknowledged_by/at`, `reviewed_by/at`, `resolved_by/at`, `resolution_note` columns.
- History: trigger `alerts_audit` writes every INSERT/UPDATE/DELETE of `alerts` to `audit_log` with full
  old/new rows and the actor (`auth.uid()` from the per-request `request.jwt.claims` set by the API).
  Readings attached to an episode are in `alert_measurements` (`attached_at`). Severity raises are UPDATEs.
- Deletion: no API route and no RLS policy deletes alerts. Only a cascade from deleting the patient's profile
  would remove them (`alerts_patient_id_fkey … ON DELETE CASCADE`).

**Proposed behaviour (minimal):**

| Topic | Proposal |
|---|---|
| Dismissal | New status `dismissed`, allowed only from `open` or `acknowledged`, **only for `notice` alerts** (R-TGT-1). Severe, emergency and trend alerts can never be dismissed (409 `invalid_transition`) |
| Who | The patient (own alert) or the assigned doctor. Admin: no |
| Reason | Required, one of `remeasured_lower`, `measurement_error`, `other` + optional text (≤ 500) |
| Recording | New columns `dismissed_at`, `dismissed_by`, `dismissal_reason`, `dismissal_note`; CHECK `status <> 'dismissed' or dismissed_at is not null` |
| After dismissal | Not "active" (leaves the active lists and does not absorb the next above-target reading: a new reading creates a new notice), still listed under "all"; the doctor can still `review` it (`dismissed → reviewed`) |
| Preservation | Nothing is deleted; the original reason, level and readings stay; every change is in `audit_log` |
| Timeline | `GET /alerts/{id}/events` built from `audit_log` (this alert's rows) + `alert_measurements` + the linked symptom report: events `created`, `level_raised`, `measurement_attached`, `status_changed {from,to}`, with time, actor role (patient / assigned doctor / rule) and note. Ordered by time ascending, ties by audit id. Same access as `GET /alerts/{id}`; never returns raw `old_data/new_data` |
| Safety | Dismissal never changes rules, thresholds or emergency guidance; the patient sees "Your doctor will still see this alert" |

**Database impact:** one additive migration (M10): widen `alerts_status_check` with `dismissed`, add the four
columns and the CHECK. Optional in the same migration: make `audit_log` append-only for every role except
`service_role` (revoke UPDATE/DELETE, trigger that rejects them). The timeline needs no table. Rollback: forward
migration only (no dismissed rows may exist). It needs your approval, a staging run, then production approval.

**Tests:** transition matrix (who × level × state), 409 for severe/trend/emergency, reason required, dismissed
excluded from active + R-TGT-1 creates a new notice, timeline ordering and content, no raw audit payload leak,
other patient / unassigned doctor 403. Frontend: dismiss button on notice alerts (patient), timeline in alert
detail (doctor). Estimated effort: about one day including tests, after approval.

## 6. V1 release-readiness checklist

| Area | Item | Status |
|---|---|---|
| Functional | MVP of the conception (readings, rules, alerts, emergency workflow, journal, doctor record, care plan, profile) | Done, merged `e9c9c28`, local only |
| Functional | Q1–Q4 | Deferred (your decisions) |
| Functional | Q5 dismissal + timeline | Proposal (§5), not implemented |
| Database | Repository = production M1–M9 | Verified (382/382) |
| Database | M9 / `LIVE_UNTIL` | Kept by decision (not approved retroactively); `LIVE_UNTIL` = M9 |
| Database | Migration process (who can push, changelog first) | **Open** |
| Security | Assigned-doctor access, patient isolation, private notes | Tested (pytest + acceptance + browser) |
| Security | Login rate limiting, logout endpoint, token storage review | Open (step 10) |
| Security | `main` branch protection | Open |
| Security | Production `DATABASE_URL` in a repo-folder `.env` | Moved outside the repository folder 2026-10-31 (not read, not rotated); `.gitignore` also covers `*.env`, `*.pem`, `*.key` |
| Clinical | Thresholds, symptom list, wording, French alert texts reviewed by a clinician | Open (claims of a mentor review unconfirmed) |
| Clinical | Emergency number 14 verified | Open |
| Clinical | ML / live warnings inactive | Verified (0 early warnings; API serves no estimate) |
| Compatibility | API ↔ contract ↔ frontend | CI green on `e9c9c28` |
| Compatibility | API ↔ ML model version | `model_unavailable` by design (§3) |
| Tests | Backend 429 × 2 profiles, frontend 35, CI | Green |
| Tests | Staging end-to-end (phase D) | Blocked on staging approval |
| Release | Staging project | Proposal (§4), waiting for approval |
| Release | Hosting + HTTPS for API and frontend | Not chosen |
| Release | Production deployment | Not authorized |
