# Incident: unapproved changes to the live Supabase project `pulse` (2026-10-30)

| | |
|---|---|
| Status | **Open. Freeze in effect** (see §1). Reviewed by Ayoub; ready for publication. The incident itself is not closed: approvals, actors and several timings are unresolved (§10). |
| Project | Supabase `pulse`, ref `nfmfdhpxipdndggxtqho` |
| Detected | 2026-10-30, during the session start-up Git check (`origin/AI` had moved from `6681979` to `ba556da`) |
| Investigated | 2026-10-30, about 17:00–18:00 UTC. Read-only. Approved by Ayoub. |
| Written by | Claude Code (session in the repository root, branch `feat/api-supabase`) |
| Classification | Approval-process breach and data-integrity incident. No production patient data is involved: every row on `pulse` is fictional demo data. |

Labels used in this report:

- **FACT**: checked during the investigation. The command or query is named.
- **CLAIM**: stated in a commit, a document or by a person. Not independently confirmed.
- **ASSUMPTION**: an inference. Stated as such.
- **OPEN**: unresolved.

No credentials, connection strings, patient identifiers, device identifiers or health values appear in this report. Counts and timestamps only.

---

## 1. Freeze (ordered by Ayoub, in effect until he lifts it)

- Do not run `scripts/cloud_update.ps1`, `scripts/run_cloud_jobs.ps1`, any migration, seed, replay, simulator or ML job (`pulse_ml.predict`, `monitor`, `weekly`, `feedback`, `pulse_data.ingest`, `stream`) against live `pulse`.
- No changes to live records or schema. No rollback.
- Do not reset passwords or rotate shared credentials.
- R-RING-1 stays disabled.
- No change to model versions, backend configuration (`PULSE_ML_MODEL_VERSION`) or the backend migration profile (`scripts/test_db.py` `LIVE_UNTIL`).
- Branch `AI` is kept as is. Do not delete it, rewrite it or merge it. Its model artifacts and scripts are kept for review.
- Do not display, copy, delete, modify or rotate the repository-root `.env` or the credentials it holds (§8a).
- This report is **internal**. It names the commit author's GitHub handle for accountability. Any wider or external copy must be anonymised separately.

### 1a. Approved exception: re-push of the wearable demo data (separate, narrow operation)

Ayoub has asked the data/AI developer to re-push the wearable demo data. This approval covers **only** simulated wearable demo data. It does **not** authorise:

- ML jobs (`run_cloud_jobs.ps1`, `pulse_ml.*`);
- migrations (`db push`);
- updates to `patient_profiles`;
- any other data change.

**FACT:** the existing tooling is broader than that scope:

- `scripts/cloud_update.ps1` without `-Local` first runs `db push --linked`, confirmed automatically.
- Part 1 of the generated SQL (`cloud_ring_demo_parts()`, and the same in `cloud_ring_demo_sql()`) also **UPDATEs `condition_codes` on every demo patient profile** and inserts `devices`, in addition to deleting and re-inserting `wearable_samples` (§4.1).

Running either one unchanged would go beyond the approved scope. The operation should be agreed beforehand, at the level of the exact SQL: which tables, which statements, and whether a `DELETE` is included. It should then be recorded with its time, its operator and before/after counts.

---

## 2. Summary

1. **FACT:** migration M8 `20261030160000_chronic_conditions` is applied on live `pulse`. Ayoub's approval, which `PULSE_DATABASE_SYNC_POLICY.md` §3 requires, is not on record. The previous verification (before step 8, at `AI` `6681979`) recorded M8 as "not applied, needs approval" (blocker B29).
2. **FACT:** a "ring demo refresh" ran against live `pulse` at about 14:57–14:59 UTC:
   - it **deleted** every earlier simulated wearable sample;
   - it **updated** `condition_codes` on all 12 patient profiles;
   - it **inserted** 20,832 simulated wearable samples and some simulated devices.

   The policy classes `DELETE` of data as a change that needs Ayoub's explicit approval first. That approval is not on record.
3. **FACT:** nothing in `public.audit_log` records the M8 apply, the deletion or the profile updates.
4. **FACT:** the ML jobs have **not** written to live. `ml_predictions`, `wearable_flags`, `weekly_reports` and `patient_bands` are all empty, last checked 17:57:47 UTC.
5. **FACT:** branch `AI` deleted the `mbp-v1` model artifact and replaced it with `mbp-v1.1`. The backend serves only `mbp-v1`.
6. **CLAIM:** commit `ba556da` and `docs/data/CLOUD_STEPS.md` say the changes were "team approved" and that "Claude ran it" on the data/AI developer's machine.

---

## 3. Migration M8

### 3.1 Live migration history

FACT (Supabase CLI 2.54.11 `migration list --linked`; CLI 2.122.0 `db query --linked` on `supabase_migrations.schema_migrations`):

| Version | Name | Statements recorded |
|---|---|---|
| 20261029120000 | core_schema | 49 |
| 20261029120100 | access_policies | 53 |
| 20261030120000 | backend_alignment | 15 |
| 20261030120100 | ml_predictions | 6 |
| 20261030130000 | patient_birth_year | 1 |
| 20261030140000 | algerian_factors_wearables | 20 |
| 20261030150000 | ml_monitoring (the data/AI "M7"; approved by Ayoub, B28) | 31 |
| **20261030160000** | **chronic_conditions (M8)** | **2** |

- **FACT:** `schema_migrations` has no `created_by` column, and it records no apply time. The live database cannot tell us **when** M8 was applied or **who** applied it.
- **FACT:** the two statements recorded live are the text of `supabase/migrations/20261030160000_chronic_conditions.sql`, comments included:
  1. `alter table public.patient_profiles drop constraint patient_profiles_condition_codes_check`
  2. `alter table public.patient_profiles add constraint patient_profiles_condition_codes_check check (condition_codes <@ array[...13 codes...]::text[])`
- **FACT:** the file's git blob is `5404d382a288e2f0fc7df883655e57f530c14459`, the same at `6681979` and at `origin/AI` `ba556da`. It was added in `6681979` ("feat(data,ml): literature-based ring demo data + chronic conditions (M8)", 2026-10-30 06:16 UTC) and never edited afterwards.

### 3.2 Live schema difference

FACT (`supabase db dump --linked -s public,private`, schema only, compared with `scripts/compare_schemas.py`):

- I read `compare_schemas.py` before using it. It only reads two local files and prints the difference. It makes no database connection and no writes.
- **Live now vs the previous verified live dump (M1–M7):** 382 statements each, 381 identical.
- **Live now vs the M1–M7 migrations dump** (built in a throwaway container in the earlier session): 382 statements each, 381 identical.
- The only differing statement is `CREATE TABLE public.patient_profiles`, because of its inline CHECK constraint:

| | `patient_profiles_condition_codes_check` allowed codes |
|---|---|
| M1–M7 (before) | hypertension, diabetes, dyslipidemia, chronic_kidney_disease, heart_disease, stroke_history, pregnancy (7) |
| Live now | the 7 above + copd, asthma, obstructive_sleep_apnea, atrial_fibrillation, heart_failure, thyroid_disease (13) |

- **FACT:** the live list is exactly the M8 file's list, in the same order.
- **FACT:** there are no other schema changes: no new or changed tables, columns, indexes, triggers, functions, policies or default privileges in `public` or `private`.
- **FACT:** M8 is additive. It widens a CHECK constraint, so no existing row can become invalid.

---

## 4. The ring-demo refresh (live data changes)

### 4.1 What the code does

FACT (read from `origin/AI`; nothing was executed):

- **`scripts/cloud_update.ps1`**, added in `2f4ee63`, runs these steps:
  1. **Migrations.** Without `-Local`: `npx -y supabase@2.122.0 db push --linked --dry-run`, then `"y" | npx -y supabase@2.122.0 db push --linked`. The `"y"` is piped in, so the push is confirmed automatically. With `-Local`: `migration up --local`.
  2. **Generate the SQL:** `.venv\Scripts\python -m pulse_data.simulate ring-demo-sql`, which writes `data/cloud_ring_demo*.sql`. `data/` is git-ignored.
  3. **Run the SQL:** each `data/cloud_ring_demo_part*.sql` file is executed with `npx -y supabase@2.122.0 db query --linked -f <file>`, or `--local` with `-Local`.
  4. **Check:** a count query.
- **`pulse_data/simulate.py` `cloud_ring_demo_parts()`**, added in `2f4ee63`. Each part is a `DO $ring_demo$ ... end` block. Part 1 starts with:
  - `delete from public.wearable_samples where source = 'simulated' and device_id in (<the 12 demo ring device ids>)`
  - `update public.patient_profiles set condition_codes = <generated list> where user_id = <id>`, once for each of the 12 demo patients (fictional accounts);
  - `insert into public.devices (...) values ... on conflict (id) do nothing`.

  Every part then runs `insert into public.wearable_samples (...) values ... on conflict (device_id, external_id) where external_id is not null do nothing`, with 5,000 rows per part.
- **`cloud_ring_demo_sql()`** is the earlier single-block version, present since `6681979`. It does the same delete, update and inserts in one block.

### 4.2 What the live data shows

FACT (read-only `SELECT` through CLI 2.122.0 `db query --linked`, first run earlier in the investigation, re-checked 17:57:47 UTC; counts unchanged between the two runs):

| Table | Rows now | `created_at` / `updated_at` (UTC, 2026-10-30) | Notes |
|---|---|---|---|
| `wearable_samples` | 20,832 | created 14:57:49.91 – 14:58:58.87 | all `source = 'simulated'`; 12 patients; heart_rate 18,144, spo2 2,016, hrv_rmssd 336, skin_temperature 336; `measured_at` 2026-10-01 23:00 – 2026-10-29 22:00 |
| `devices` | 24, all `device_type = 'simulator'` | created 04:30:51 – 14:57:49.91 | some rows created at 14:57:49 by the refresh |
| `patient_profiles` | 12 | created 04:30:51; **last `updated_at` 14:57:49.91** | codes now in use: hypertension 12, dyslipidemia 5, diabetes 3, obstructive_sleep_apnea 2, chronic_kidney_disease 1, copd 1, atrial_fibrillation 1 |
| `measurements` | 730, all `provenance = simulated`, `source = simulated` | created 04:30:51 | unchanged by the refresh |
| `profiles` | 14 (12 patient, 1 doctor, 1 admin) | created 04:30:51 | unchanged |
| `symptom_reports` | 2, `source = simulated` | created 04:30:51 | unchanged |
| `doctor_notes` | 1 | from the seed | unchanged |
| `emergency_events` | 0 | — | |
| `alerts` | 0 | — | |
| `ml_predictions` | 0 | — | ML jobs not run on live |
| `wearable_flags` | 0 | — | |
| `weekly_reports` | 0 | — | |
| `patient_bands` | 0 | — | |

From this:

- **FACT:** no wearable sample is older than 14:57:49 UTC. Every simulated sample that existed before the refresh has been deleted.
- **CLAIM:** that was about 315 samples (the earlier session's row estimate before step 8; `docs/CLAUDE_SESSION_HANDOFF.md` §4). The exact number deleted is unknown.
- **ASSUMPTION:** the 14:57–14:59 UTC writes are one run of `cloud_update.ps1`, or of the same generated SQL. This matches the expected check in the script (`ring_patients 12, ring_samples 20832, copd 1`). Nothing in the database ties the writes to a person or a tool.
- **FACT:** `measurements` and `profiles` are unchanged, which matches the script's stated scope.
- **ASSUMPTION:** the earlier `condition_codes` values were overwritten for all 12 patients. They cannot be recovered from the live database (see §5).

### 4.3 Classification under `PULSE_DATABASE_SYNC_POLICY.md` §3

| Operation | Policy class | Approval required | Approval on record |
|---|---|---|---|
| M8 `db push` | Migration | Ayoub approves every migration before it reaches `pulse` | **No.** B29 was open. |
| `DELETE` of simulated wearable samples | Destructive change | Stop, describe the risk, Ayoub's explicit approval first | **No** |
| `UPDATE patient_profiles.condition_codes` (12 rows) | Direct non-destructive change, which overwrites prior values | Record it in `PULSE_SUPABASE_CHANGELOG.md` and report it to Ayoub | **No** changelog entry on the backend side. The `AI` docs record it as done. |
| `INSERT` devices and samples | Direct non-destructive change, fictional data | Record and report | Recorded in the `AI` docs only |

---

## 5. Audit trail

FACT (read-only `SELECT table_name, action, count(*), min(changed_at), max(changed_at) from public.audit_log group by ...`; the `old_data` and `new_data` columns were **not** read):

| table_name | action | rows | changed_at |
|---|---|---|---|
| care_plans | INSERT | 11 | 04:30:51 |
| doctor_notes | INSERT | 1 | 04:30:51 |
| doctor_patient_assignments | INSERT | 11 | 04:30:51 |
| medications | INSERT | 11 | 04:30:51 |
| profiles | INSERT | 14 | 04:30:51 |
| profiles | UPDATE | 14 | 04:30:51 |

- **FACT:** every audit row comes from the seed run at 04:30:51 UTC. There is no audit row for the M8 apply, the `wearable_samples` delete or insert, the `patient_profiles` updates, or the `devices` inserts.
- **ASSUMPTION:** this is because those tables have no audit trigger, and DDL is never audited. It does not mean the writes happened elsewhere. I did not check the trigger list table by table for this report.
- **OPEN:** the Supabase platform logs (Postgres or API logs for 14:00–15:00 UTC) could show the session and role. They were not queried: the Supabase MCP connector has no access to this project (§9).

---

## 6. The five `AI` commits (`6681979..ba556da`)

FACT (`git log`, `git show --stat`, `git diff`). All five are by the data/AI developer (commit author: the AI data contributor; the author name and email are in the commit metadata). Times are converted to UTC from `+0100`.

| Commit | Time (UTC) | Subject | Relevant changes |
|---|---|---|---|
| `13cc3a1` | 07:21 | feat(ml): train and test on REAL public data (NHANES, Mendeley home BP, PhysioNet Apnea-ECG) | `ml/pulse_ml/real_data.py`: fetchers into a git-ignored `data/external/`. `real_bands.py` → `reference_nhanes.json` (aggregates only). New model `wrisk-v1` (artifact added; **CLAIM:** AUROC 0.60, not shown in reports). `reference.py` `pulse_vs_population()`. `weekly.py` adds `summary.pulse_vs_population`. `real_tests.py`. `ml/requirements.txt` +3 lines. Tests. |
| `21ec74f` | 07:21 | docs(ml): real datasets used, real-data results and limits | `docs/data/DATA_SOURCES.md`, `ml/MODEL_CARD.md`, `ml/README.md` |
| `deedf52` | 08:12 | feat(ml): pulse-sim-v2 calibrated on real home BP; retrain all models (*.1 versions) | `pulse_data/simulate.py` `NOISE_V2` (**CLAIM:** ML cohort only; the demo seed stays v1). **Artifacts deleted and replaced:** `mbp-v1` → `mbp-v1.1`, `mbp-v2` → `mbp-v2.1`, `ring-v1` → `ring-v1.1`, `wcls-v1` → `wcls-v1.1`. Model code (`train.py`, `classify.py`, `ring.py`, `ring_train.py`, `mbp_v2.py`). `ML_INVENTORY.md`, `MODEL_CARD.md` rewritten. |
| `2f4ee63` | 09:09 | chore(cloud): scripts + step-by-step guide to apply M8, refresh the ring demo and run the ML jobs on the cloud | **New** `scripts/cloud_update.ps1`, `scripts/run_cloud_jobs.ps1`, `docs/data/CLOUD_STEPS.md`; `simulate.py` `cloud_ring_demo_parts()`; test update |
| `ba556da` | 14:00 | docs(cloud): M8 applied and ring demo refreshed in the cloud (team approved); record the read-only check | `CLOUD_STEPS.md`: "step 1 is done (the team approved; Claude ran it, and the check matched)". `MIGRATIONS.md`: M8 row changed from "**NOT applied: needs approval**" to "**applied 30 Oct 2026** (team approved)", plus a line recording the cloud refresh and a read-only check. |

Things in these commits that bear on our rules:

- **FACT:** no new migration file. M8 already existed at `6681979`.
- **FACT:** `CLOUD_STEPS.md` tells the reader to:
  - grant Claude Code permission for `npx -y supabase@2.122.0 db push --linked` and `db query --linked` ("only if your team agrees");
  - reset the database password if it is forgotten. A reset would break every other holder of the connection string.
- **FACT:** `MIGRATIONS.md` line 5 still says: "schema changes reach the cloud only after backend review". The M8 row contradicts that rule.
- **FACT:** `CLOUD_STEPS.md` step 5 contains a message for the backend teammate listing the work to build next. That list includes **rule R-RING-1** (spec in `ml/pulse_ml/reference.py`, which still has `PENDING_CLINICIAN_REVIEW = True`). The backend has not implemented R-RING-1. It stays disabled (B26).
- **OPEN:** commit `ba556da` (14:00:06 UTC) reports the refresh as done, yet the live rows were written at 14:57–14:59 UTC. Possible explanations:
  - the refresh ran again after the commit;
  - the commit's author date does not reflect when it was actually made (author dates can be set or carried over);
  - the clock on the data/AI machine was wrong.

  Not determined.

---

## 7. Cloud scripts and how they choose their target

FACT (code read only; nothing executed):

| Script or job | How the target database is chosen | What it writes |
|---|---|---|
| `scripts/cloud_update.ps1` | `--linked` by default, i.e. whatever project `supabase link` last linked **in the folder it is run from**; `-Local` for the local stack. There is no project-ref check inside the script. | Pending migrations (`db push`, confirmed automatically); `DELETE`/`UPDATE`/`INSERT` as in §4.1 |
| `scripts/run_cloud_jobs.ps1` | Without `-Local`, it reads the first `DATABASE_URL=` line from `.env` **in the repo root** and exports it. With `-Local`, `127.0.0.1:55322`. | Runs `pulse_ml.predict --all`, `pulse_ml.monitor --nights`, `pulse_ml.weekly`. These write `ml_predictions`, `wearable_flags`, `weekly_reports` and proposed `patient_bands`. |
| `ml/pulse_ml/predict.py`, `monitor.py`, `weekly.py`, `feedback.py`; `pulse_data/ingest.py` | `os.environ.get("DATABASE_URL", LOCAL_DB)`: **any shell with `DATABASE_URL` set targets that database**, with no confirmation flag | As above. `monitor --follow` is a long-running poller (sleeps between polls). `ingest.py` writes imported readings. |
| `pulse_data/stream.py` | `DATABASE_URL` is refused unless `--i-confirmed-cloud` is passed | The only job with a cloud guard |

---

## 8. Read-only check for automation that could run the scripts

| Where | Finding | Basis |
|---|---|---|
| GitHub Actions | **FACT:** the repository has one workflow, `CI` (`.github/workflows/ci.yml`, active). It exists on `feat/api-supabase`, `docs/backend-architecture`, `feat/api-contract-v1` and `feat/api-measurement-slice`. Triggers are `push` and `pull_request` only: no `schedule`, no `workflow_dispatch`. It runs backend tests against throwaway local databases (`127.0.0.1:55432/55433`). It does not reference Supabase cloud, `cloud_update`, `run_cloud_jobs` or `pulse_ml`. **`AI`, `main` and `feature/frontend` have no workflow files.** | `git ls-tree` on every remote branch; `git show <branch>:.github/workflows/ci.yml`; public GitHub API `/actions/workflows` |
| GitHub repository secrets and environments | **OPEN:** not inspected. `gh` is not installed and the API needs an authenticated admin. The workflows do not reference any cloud secret. | — |
| Other CI or hosting configs | **FACT:** none on any branch (no Makefile, Procfile, Vercel, Netlify, Render, Fly, Husky or pre-commit config) | `git ls-tree` pattern search |
| Windows Task Scheduler (this machine) | **FACT:** no task whose name or actions mention `pulse`, `supabase`, `cloud_update`, `run_cloud_jobs` or `pulse_ml` | `Get-ScheduledTask` |
| Git hooks (this repo) | **FACT:** none installed (only `*.sample`) | `.git/hooks` |
| Project Claude settings | **FACT:** no `.claude/` folder in `pulse` or `pulse-frontend`. User-level settings exist but were not reviewed for allow-rules. | filesystem |
| Supabase link in this repo | **FACT:** `supabase/.temp/` has no `project-ref`, so this checkout is **not** linked. `cloud_update.ps1` run here would not reach `pulse` without a `supabase link` first. | filesystem |
| **`.env` in this repo** | **FACT:** `.env` in the repository root exists (git-ignored, 119 bytes, last modified **2026-10-30 17:19:27 UTC**, during this investigation). It contains one key, `DATABASE_URL`, whose host is the Supabase session pooler `aws-0-eu-west-3.pooler.supabase.com`. The value was not printed and is not reproduced here. **This investigation did not create or modify that file.** **ASSUMPTION:** it points at `pulse`. **Risk:** `scripts/run_cloud_jobs.ps1` run from a checkout of `AI` in this folder, or any ML job in a shell that loads this `.env`, would write to that database. | `stat`; key-name and host-only `grep`/`sed` |
| The data/AI developer's machine | **OPEN:** cannot be inspected from here. `CLOUD_STEPS.md` documents manual runs only. No scheduling is documented. | — |
| Documented workflows | **FACT:** `CLOUD_STEPS.md` steps 1–3 and `docs/data/PULSE_FULL_REPORT.html` describe **manual** runs of both scripts. The report marks `run_cloud_jobs.ps1` as "OPEN", meaning still to run. Neither documents a schedule or an automatic trigger. | `git grep` on `origin/AI` |

### 8a. The `.env` discovery

- **FACT:** `.env` exists in the repository root.
  - It is git-ignored (`.gitignore:167`) and has never been committed.
  - Size: 119 bytes. Last modified: 2026-10-30 17:19:27 UTC, while this investigation was running.
  - It contains exactly one key, `DATABASE_URL`, whose host is a Supabase session pooler (`aws-0-eu-west-3.pooler.supabase.com`).
- **FACT:** the investigation read only the key name and the host. The connection string, user and password were not displayed, copied or stored anywhere, including this report.
- **FACT:** the investigation did not create, modify or delete this file. Every write made by the investigation was to a scratch directory outside the repository.
- **OPEN:** who created the file, why, and which project the URL points at.
  - **ASSUMPTION:** `pulse`, because it is the only project in `eu-west-3` known to this team.
  - **ASSUMPTION:** it is the input expected by `CLOUD_STEPS.md` step 2.
- **Decision (Ayoub):** keep the file as it is. Do not delete it, change it or rotate the credential. ML cloud jobs stay frozen and `run_cloud_jobs.ps1` is not to be run.
- **Note:** the backend API does not load `.env` by itself (`docs/CLAUDE_SESSION_HANDOFF.md` §5, B8). The key name `DATABASE_URL` is the one the `AI` scripts and jobs use. The backend reads `PULSE_DATABASE_URL`.

**Conclusion:** I found no automation in the repository or on this machine that would run the cloud scripts by itself. The open risk is a manual run by someone following `CLOUD_STEPS.md` step 3 (`run_cloud_jobs.ps1`). `CLOUD_STEPS.md` still lists that step as pending, and the repo's `.env` now contains the cloud connection string it needs.

---

## 9. Impact

- **Backend ML serving.** FACT: the API serves only `ml_predictions` rows with `model_version = "mbp-v1"` (`api/app/config.py:33`, env `PULSE_ML_MODEL_VERSION`). FACT: `AI` no longer contains the `mbp-v1` artifact, and `CLOUD_STEPS.md` step 3 says the jobs will write `mbp-v1.1`. **ASSUMPTION:** if the jobs run as documented, `GET /patients/{id}/predictions/latest` will return `model_unavailable` for every patient. Nothing changes until someone decides.
- **Backend test databases.** FACT: `scripts/test_db.py` `LIVE_UNTIL = "20261030150000"`. The `live` test profile no longer matches live `pulse`, which now includes M8. The `latest` profile already applies M8. Not changed, per the freeze.
- **API contract.** FACT: `ConditionCode` values in `api/app/schemas.py` and `contract/openapi.json` were not reviewed against the 13 live codes in this investigation. **OPEN:** a profile read could return a code that the contract does not list.
- **Clinical safety.** FACT: no `alerts` and no ML outputs were written to live. Deterministic rules are unaffected. R-RING-1 is not implemented.
- **Data.** All data on `pulse` is fictional demo data (CLAIM: seed design; FACT: every `measurements` row is `provenance = simulated`). No real patient data is involved. The deleted rows were simulated wearable samples.

---

## 10. Open questions

1. Who approved M8 and the ring refresh ("team approved")? Was Ayoub's approval requested or given?
2. Who ran `cloud_update.ps1`, or the equivalent SQL? From which machine and Supabase account, and how many times?
3. When exactly was M8 applied? The live history has no timestamp. Was it in the same run as the 14:57 UTC data writes, or earlier?
4. Why is `ba556da` (14:00 UTC) dated before the data writes (14:57–14:59 UTC)?
5. How many simulated wearable samples were deleted, and what were the 12 profiles' `condition_codes` before the update? Restoring them would need a backup or point-in-time recovery; whether the project has them was not checked.
6. Who wrote the repository-root `.env` at 17:19 UTC, and for what purpose? Does it point at `pulse`?
7. Will the ML jobs be allowed to run, and with which served model version (`mbp-v1` vs `mbp-v1.1`)?
8. Do `api/app/schemas.py` and `contract/openapi.json` accept the six new condition codes?
9. Should the process change? Options: require a project-ref check in scripts that target the cloud; add a `--i-confirmed-cloud` guard like `stream.py`'s; do not grant agents `db push --linked` permission.
10. For the approved wearable re-push (§1a), what is the exact agreed SQL? Who runs it, and how is it recorded?
11. Should audit triggers cover `patient_profiles`, `wearable_samples` and `devices`? That would be a schema change and needs its own review.

---

## 10a. Addendum: ML jobs ran on live after the freeze (re-check at 18:12:58 UTC)

Trigger: a message from the data/AI developer saying they had run the 3 ML jobs on the cloud, and that the demo data "was never deleted".

**New commits on `AI`** (FACT: `git fetch`, `git log`, `git diff ba556da origin/AI`):

| Commit | Author date | Subject |
|---|---|---|
| `ee3853d` | 2026-10-30 17:09:04 +0100 | docs: full data/database/AI report (HTML + PDF) and the earlier logic guide; fix trained_on in ml/README |
| `4feff73` | 2026-10-30 18:07:01 +0100 | feat(cloud): run the ML jobs on the cloud without a stored password; jobs ran 30 Oct |

- **Author:** both commits are authored and committed by the same AI data contributor. **CLAIM** (the message): "I pushed to AI as you". That is not true of the git metadata.
- **No new migration file.**
- **`scripts/run_cloud_jobs.ps1` (FACT, code read only).** If `.env` has no `DATABASE_URL`, the script:
  1. runs `npx -y supabase@2.122.0 db dump --linked --dry-run`;
  2. parses the `PGUSER`, `PGPASSWORD`, `PGHOST`, `PGPORT` and `PGDATABASE` values it prints (the Supabase CLI's temporary login role);
  3. builds a `DATABASE_URL` from them;
  4. sets `PULSE_DB_ROLE=postgres`.
- **`ml/pulse_ml/predict.py` new `connect()` (FACT).** After login it runs `set role postgres` whenever `PULSE_DB_ROLE` is set. `monitor.py`, `weekly.py` and `feedback.py` now connect through it. **Effect:** the jobs write as the `postgres` superuser-equivalent role, using a credential taken from whoever's Supabase CLI is linked on the machine. No confirmation flag guards cloud use.
- **`docs/data/CLOUD_STEPS.md`:**
  - **CLAIM:** "steps 1–3 are done (team approved; Claude ran them and checked the cloud)".
  - The pooler host in the guide is changed from `aws-0-eu-west-3` to `aws-1-eu-west-3`.
  - **FACT:** the `.env` in this repository (§8a) uses the old `aws-0` host.

**Live data now** (FACT: read-only `SELECT`, `now()` = 2026-10-30 18:12:58 UTC):

| Table | Before (17:57:47 UTC) | Now | Written (UTC) | Detail |
|---|---|---|---|---|
| `ml_predictions` | 0 | **11** | 18:03:55.82 | all `model_version = mbp-v1.1`: 10 `ok`, 1 `insufficient_history` |
| `wearable_flags` | 0 | **33** | 18:04:17 – 18:04:22 | `ring-v1.1`, `review_status = open` |
| `weekly_reports` | 0 | **11** | 18:04:32 – 18:05:11 | `status = ready` |
| `patient_bands` | 0 | **43** | 18:04:32 – 18:05:11 | `status = proposed`, `ring-v1.1` |
| `audit_log` | seed rows only | + 33 `wearable_flags INSERT`, 11 `weekly_reports INSERT`, 43 `patient_bands INSERT` | same times | **no audit row for `ml_predictions`** |
| `alerts` | 0 | 0 | — | |
| `wearable_samples` | 20,832 | 20,832 | last 14:58:58 | unchanged |
| `measurements`, `profiles`, `patient_profiles`, `devices` | 730 / 14 / 12 / 24 | same | no new `created_at`/`updated_at` | unchanged |
| migrations | 8 | 8 | — | unchanged |

**Conclusions:**

- **FACT:** the ML jobs wrote 98 rows to live `pulse` between 18:03:55 and 18:05:12 UTC. That was after the freeze (§1), and after Ayoub's instruction to keep ML cloud jobs frozen and not run `run_cloud_jobs.ps1`. This approval breach is separate from the one in §2. It is also outside the scope of the approved wearable re-push (§1a).
- **FACT:** the served model mismatch is now real. Live has only `mbp-v1.1` rows, and the backend serves only `mbp-v1` (`api/app/config.py:33`). **ASSUMPTION:** `GET /patients/{id}/predictions/latest` returns `model_unavailable` for every patient until someone decides.
- **FACT:** the jobs left the demo data untouched (counts and timestamps unchanged), which matches the claim.
- **The "never deleted" claim, partly.** It is consistent with the cloud state **since** the 14:57 UTC refresh. It does not cover the simulated samples that existed before 14:57, which are gone (§4.2).
- **The local-database claims.** They refer to the data/AI developer's own machine. **FACT:** this machine has no database on `localhost:55323`. It runs only the backend test containers (`55432`, `55433`) and an unrelated container, and has no second checkout of the project under a `Desktop` folder.
- **Timestamp pattern (ASSUMPTION; probably answers §10 question 4):** each `AI` commit time stamped `+0100` lands about 1 hour **before** the live writes it reports:
  - `ba556da` 14:00 UTC vs writes at 14:57 UTC;
  - `4feff73` 17:07 UTC vs writes at 18:03 UTC.

  If the developer's machine records UTC wall-clock time with a `+0100` label, each commit was made 2–4 minutes after its writes. That fits the commit messages. Not verified.

**New open questions:**

- **12.** Whose Supabase CLI login, on which machine, supplied the temporary credential used at 18:03 UTC?
- **13.** Is `set role postgres` from the CLI login role acceptable for batch jobs, given that it bypasses RLS?
- **14.** Should the 98 ML rows stay, given that they are advisory, doctor-only and not exposed by any endpoint except `ml_predictions`? Removing them would be a destructive change: Ayoub's decision, not taken here.

---

## 10b. Addendum: second ML run after the freeze (re-check at 19:49:31 UTC)

**FACT** (`git fetch`). Two new `AI` commits:

- **`d84a7f6`** (author date 18:31 +0100), "record the medical mentor review and emergency number 14; cloud jobs on one connection". It:
  - adds `ml/pulse_ml/jobs.py`;
  - changes `predict.connect()` to retry up to 6 times;
  - passes the CLI login to `run_cloud_jobs.ps1` as `PG*` variables;
  - replaces `PENDING_CLINICIAN_REVIEW = True` with a `CLINICIAN_REVIEW` statement.

  Its message says "Cloud re-run: 10 BP estimates for 31 Oct, 33 flags, 11 reports (all cite the review)".
- **`d30296a`** (19:20 +0100): a model backtest and NHANES test.

Neither commit adds a migration.

**FACT** (read-only `SELECT`). Live changes since the 18:12:58 UTC check:

| Table | Change | Time (UTC) |
|---|---|---|
| `ml_predictions` | Still 11 rows (10 `ok`, 1 `insufficient_history`, `mbp-v1.1`, target 2026-10-31), but `created_at` is now 18:40:50–18:40:53. `predict.py` upserts on `(patient_id, target_date, model_version)` and sets `created_at = now()`. **The values written at 18:03 UTC were overwritten and cannot be recovered**; `ml_predictions` has no audit trigger. | 18:40:50–18:40:53 |
| `weekly_reports` | 22 `UPDATE` audit rows; `updated_at` up to 18:42:17 | 18:29–18:42 |
| `wearable_flags`, `patient_bands` | unchanged (33 / 43) | — |
| Everything else | unchanged: `alerts` 0, `measurements` 730, wearable samples 20,832, 8 migrations | — |

**CLAIMS that need Ayoub's confirmation:**

- the medical mentor reviewed the alert thresholds, the SpO2 94 % / COPD 88 % limits, the band rule and the wording on 30 Oct 2026;
- emergency number 14 has been "decided" (D3).

The backend has not changed `api/app/config.py` (`dz-14` stays `verified: False`), `api/app/analysis/` or R-RING-1 because of these claims.

---

## 10c. Addendum: `AI` commit `358ad4c` and migration `20261030170000_live_early_warning.sql`

Discovered during the publication-readiness check on 2026-10-30, after the evidence in §10b was gathered.

**FACT** (`git fetch`, `git show`, `git log`; read only):

- **Commit:** `358ad4c96b7a69a3219863f7c412f75ad8a19308`, author date 2026-10-30 20:21:46 +0100, by the AI data contributor. Parent `d30296a`. 19 files, 1,664 insertions, 34 deletions. Subject: "feat(ml): live ring engine live-v1 - checks every new minute and warns the doctor BEFORE a limit is crossed".
- **New migration file:** `supabase/migrations/20261030170000_live_early_warning.sql` (named "M9" on `AI`), added in `358ad4c`. Git blob `687c42fbbeb47ce531dad60dce30a09c0c21901d`, SHA-256 `c40d8c14ef06f2f169484da4682154936ed30128e5a94846c3bd10d217f0cf47`.
- **What it does:** one `ALTER TABLE public.wearable_flags` that drops and re-adds three CHECK constraints (`kind`, `window_kind`, `metric`) with wider lists, and adds two new checks. No row, grant, policy or index change.
- **Also in the commit:** a new model artifact `ml/artifacts/live-v1/`, `ml/pulse_ml/live.py` and `live_test.py`, a changed `monitor.py` (`--follow` can write early-warning flags), a changed `pulse_data/stream.py` (live-situation simulator), `pulse_data/live_sim.py`, and updated `docs/data/*`.
- **Not in the backend branch:** the file has not been copied, `LIVE_UNTIL` is unchanged (still M8) and the backend test databases do not include it.

**CLAIM** (commit message and `docs/data/MIGRATIONS.md` on `AI`): M9 was "applied LOCALLY only (no row changed); NOT applied to the cloud" and "waits for the user's OK".

**UNRESOLVED: whether M9 is applied on live `pulse` is unknown.**

- The last read-only check of the live migration history (2026-10-30 19:49:31 UTC) showed 8 migrations (M1–M8). It was made before `358ad4c` had been fetched, so it cannot show M9.
- I did not query the live history again: that needs a Supabase CLI login, which was not part of this step.
- The `AI` documents say it is not applied, but the same documents said M8 "needs approval" until commit `ba556da`. Treat the claim as unconfirmed until the history is re-read.

**INFERRED** (from the SQL and from the live rows counted earlier; not executed anywhere):

- No existing live row can violate the new constraints. The 33 flags counted at 18:04–19:49 UTC all have `window_kind = 'night'`, a `kind` other than `early_warning`, and a `metric` other than `sleep`, which satisfies both new checks.
- The constraint names the file drops exist in the live schema dump with exactly those names, so the `DROP CONSTRAINT` statements would find them.
- The backend does not map `wearable_flags`, so M9 needs no API model change today. If flag endpoints are built later, `kind`, `window_kind` and `metric` would need the new values.

**Process note (REPORTED, from code):** the `AI` test `test_m9_early_warnings_are_forecast_flags_for_the_doctor_only` runs `delete from public.wearable_flags`. It runs inside a rolled-back transaction against a local database by default. If someone sets `PULSE_TEST_DATABASE_URL` to the cloud database, it would delete the 33 live flags inside that transaction before rolling back; no write persists, but it is a hazard worth removing.

**Applicable rule:** M9 follows the same rule as every other migration: nobody applies it to `pulse` without Ayoub's approval and a read-only verification before and after (`PULSE_DATABASE_SYNC_POLICY.md`).

---

## 11. Evidence and its limits

**How the evidence was gathered (all read-only):**

- **Git:** `git fetch --all --prune`; `git log`, `show`, `diff`, `ls-tree` and `grep` on `6681979..origin/AI`.
- **Remote migration history:** Supabase CLI 2.54.11 `migration list --linked`.
- **Schema:** CLI 2.54.11 `db dump --linked -s public,private`, schema only. The first attempt failed (`FATAL: terminating connection due to administrator command`); the retry succeeded.
- **Row counts and timestamps:** CLI 2.122.0 `db query --linked`, `SELECT` statements only, aggregates only.
- **Link folder:** a copy of the earlier session's link folder (project-ref only), kept in a scratch directory outside the repository.

**Limitations:**

- The Supabase MCP connector cannot access project `pulse` ("You do not have permission to perform this action"), so the CLI was used instead.
- When the CLI connects, it prints "Initialising login role". It creates its own temporary login role through the Supabase Management API. That is platform role management, not a data or schema change.
- The schema comparison used the earlier session's verified M1–M7 dumps, plus a direct comparison of the constraint text with the M8 file. I did **not** rebuild M1–M8 from scratch in a throwaway container for this report.
- Grants and RLS were compared only through the dump diff (default privileges and policies were identical). There was no separate grants query.
- Platform logs, backups and point-in-time-recovery availability, GitHub secrets, and the data/AI developer's machine were not inspected.
- Pre-incident row counts come from the earlier session's estimates (`reltuples`), not exact counts.

**Files the investigation produced:** scratch files only, outside the repository: the CLI install, a link-folder copy, `live5.sql` (schema only), and two `SELECT` files. The only repository change is this report.
