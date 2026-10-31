# Your steps for the cloud (project `pulse`)

> **FROZEN by Ayoub (`docs/incidents/2026-10-30-unapproved-live-changes.md` §1 and §10e).** Do not run `cloud_update.ps1`, `run_cloud_jobs.ps1`, any migration, seed, simulator or ML job against the cloud project until Ayoub lifts the freeze. Steps 1–3 below are kept as a record only.

**Status, 31 Oct 2026:** Claude ran steps 1–3 on 30 Oct (evidence: `CLOUD_RUN_LOG_2026-10-30.md`). Ayoub's written record says they ran without his confirmed explicit approval. M9 is in the cloud; Ayoub decided on 31 Oct to keep it (not approved retroactively). Cloud: M1–M9; 10 BP estimates + 1 insufficient_history, 33 ring flags, 11 weekly reports, 43 proposed bands; demo data unchanged. Step 5 is done. Everything was tested on the local copy first. Open a terminal in VS Code (**Terminal → New Terminal**); it starts in `C:\Users\Lenovo\Desktop\pulse`.

## Step 1: chronic conditions (M8) + ring demo data (about 2 minutes)
```
powershell -ExecutionPolicy Bypass -File scripts\cloud_update.ps1
```
**What it does:**
1. Shows the pending migration (only `20261030160000_chronic_conditions.sql`).
2. Applies it.
3. Uploads the simulated ring data for all 12 demo patients in 5 parts.
4. Prints a check.

**At the end you should see:** `readings 730, ring_patients 12, ring_samples 20832, copd 1` and **Done.**

**If it stops:** it prints `STOPPED at: …`. Nothing is lost, so just run the same command again. It deletes only the *simulated* ring samples of the demo rings.

## Step 2 (optional): give the jobs a way to reach the cloud database
Not needed if the Supabase CLI is linked (`supabase link`): `run_cloud_jobs.ps1` then takes a short-lived login from the CLI, the same one `db push` uses, and never prints it. This access method is under review in the incident report (questions 12–13) and frozen. Use a `.env` line only on a machine without the CLI login.
1. Open https://supabase.com/dashboard/project/nfmfdhpxipdndggxtqho and click **Connect** (top of the page).
2. Choose **Session pooler**, then copy the URI. It looks like:
   `postgresql://postgres.nfmfdhpxipdndggxtqho:[YOUR-PASSWORD]@aws-1-eu-west-3.pooler.supabase.com:5432/postgres`
3. Replace `[YOUR-PASSWORD]` with your **database password**.
   - Forgot it? Go to **Project Settings → Database → Reset database password**.
   - If the password has special characters (`@ : / ? # %`), use only letters and numbers when you reset it, to avoid escaping problems.
4. Open the secrets file: `notepad .env`. Add **one line** at the end, then save:
   ```
   DATABASE_URL=postgresql://postgres.nfmfdhpxipdndggxtqho:THE-PASSWORD@aws-1-eu-west-3.pooler.supabase.com:5432/postgres
   ```
   `.env` is git-ignored, so it never goes to GitHub. **Never paste it in chat.**

## Step 3: run the AI jobs on the cloud (about 1 minute)
```
powershell -ExecutionPolicy Bypass -File scripts\run_cloud_jobs.ps1
```
It runs, in order:
- `predict --all`: tomorrow's BP estimate for each assigned patient (model `mbp-v1.1`)
- `monitor --nights`: ring flags (`ring-v1.1`)
- `weekly`: doctor reports with pulse placement, classifier and proposed bands

It prints counts only. **Expected:** about 11 patients, mostly `ok`; 11 reports.

## Step 4: verify the cloud (done 30 Oct 2026)
Read-only checks: counts, access rules, ML outputs; the docs were updated.

## Step 5: team (done 30 Oct 2026: password shared privately, message sent)
- **Demo password:** open `.env` and read the `PULSE_DEMO_PASSWORD=` line. Send it to your teammates **privately** (not in the GitHub repo, which is public).
- **Backend teammate:** send this message:
  > "On branch AI: M8 (chronic conditions) and the 12-patient simulated ring demo are in the cloud, and the ML jobs ran there (10 BP estimates, 33 ring flags, 11 weekly reports, 43 proposed bands). The served BP model is `mbp-v1.1`. Weekly reports have `summary.pulse_vs_population` (real NHANES bands). Decisions of 30 Oct: the medical mentor reviewed the thresholds (180/120, red flags, SpO2 94 % / COPD 88 %, band rule, wording), and the emergency number is **14** (D3 closed): in `api/app/config.py` set `dz-14` to `"verified": True` (it is already `primary_number_id`), or set `PULSE_EMERGENCY_NUMBERS`. To build on your side: alerts written to Supabase, weekly report endpoint, band approval via `private.approve_band`, flag review, rule R-RING-1 (spec in `ml/pulse_ml/reference.py`). Full report: `docs/data/PULSE_FULL_REPORT.pdf`."
- **Clinician review:** done 30 Oct 2026 by the team's medical mentor (alert thresholds 180/120, red-flag symptoms, SpO2 94 % / COPD 88 %, band rule, patient wording). Also reviewed and accepted the same day: every live-v1 threshold and parameter, the ring-v1.1 night robust z 3.5 and R-RING-1 (list in `ml/MODEL_CARD.md`).
- **Emergency number for Algeria:** decided 30 Oct 2026: **14** (Protection civile). Never dial it in tests or the demo; demo mode uses a teammate's phone.

## Live early warnings (M9, `live-v1`): M9 in the cloud, engine inactive
- **Local:** M9 is applied (no row changed). The live engine runs inside `monitor --follow` on the local stack only.
- **Cloud:** M9 was applied between 21:47 and 22:58 UTC on 30 Oct, outside this Claude session. Ayoub decided on 31 Oct to **keep** it (Q6; not approved retroactively). No `early_warning` row exists. It's additive: three wider checks on `wearable_flags` and two consistency checks.
- **Still inactive by Ayoub's decision:** the live-v1 engine, the ML jobs, the simulators and R-RING-1. Running `monitor --follow` against the cloud needs Ayoub to lift the freeze.
- **Local demo:** `monitor --follow` + `pulse_data.stream --patient-email patient.b@demo.pulse.test --scenario oxygen_falling --speed 5 --minutes 20`, both with `DATABASE_URL` set to the local dev stack (`DEMO_RUNBOOK.html` step 2.3). The stream adds simulated samples to the local database.

## Cloud steps by Claude: frozen
Only read-only checks (allowed by `PULSE_DATABASE_SYNC_POLICY.md`). No `db push --linked`, no writes through `db query --linked`, no `scripts\run_cloud_jobs.ps1` until Ayoub lifts the freeze. Evidence of every earlier run: `CLOUD_RUN_LOG_2026-10-30.md`.
