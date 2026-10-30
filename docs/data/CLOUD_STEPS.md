# Your steps for the cloud (project `pulse`)

**Status, 30 Oct 2026:** step 1 is done (the team approved; Claude ran it, and the check matched). Steps 2–5 remain. Step 2 needs the database password, so only the project owner can do it. Everything was tested on the local copy first. Open a terminal in VS Code (**Terminal → New Terminal**); it starts in `C:\Users\Lenovo\Desktop\pulse`.

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

## Step 2: give the jobs a way to reach the cloud database (once)
1. Open https://supabase.com/dashboard/project/nfmfdhpxipdndggxtqho and click **Connect** (top of the page).
2. Choose **Session pooler**, then copy the URI. It looks like:
   `postgresql://postgres.nfmfdhpxipdndggxtqho:[YOUR-PASSWORD]@aws-0-eu-west-3.pooler.supabase.com:5432/postgres`
3. Replace `[YOUR-PASSWORD]` with your **database password**.
   - Forgot it? Go to **Project Settings → Database → Reset database password**.
   - If the password has special characters (`@ : / ? # %`), use only letters and numbers when you reset it, to avoid escaping problems.
4. Open the secrets file: `notepad .env`. Add **one line** at the end, then save:
   ```
   DATABASE_URL=postgresql://postgres.nfmfdhpxipdndggxtqho:THE-PASSWORD@aws-0-eu-west-3.pooler.supabase.com:5432/postgres
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

## Step 4: tell Claude "verify cloud"
Claude runs read-only checks (counts, access rules, a real doctor login) and updates the docs.

## Step 5: team
- **Demo password:** open `.env` and read the `PULSE_DEMO_PASSWORD=` line. Send it to your teammates **privately** (not in the GitHub repo, which is public).
- **Backend teammate:** send this message:
  > "On branch AI: M8 (chronic conditions) and the 12-patient simulated ring demo are in the cloud; ML jobs ran. The served BP model is now `mbp-v1.1` (retrained on data calibrated with real home BP). Weekly reports have `summary.pulse_vs_population` (real NHANES bands). To build on your side: weekly report endpoint, band approval via `private.approve_band`, flag review, rule R-RING-1 (spec in `ml/pulse_ml/reference.py`). Details: `ml/MODEL_CARD.md`, `docs/data/MIGRATIONS.md`."
- **Doctor / medical mentor:** ask them to review:
  - the alert thresholds (180/120, red-flag symptoms)
  - the SpO2 94 % / COPD 88 % limits
  - the band rule
  - the patient wording
- **Emergency number for Algeria:** confirm 14 vs 1021 from an official source before the demo.

## Optional: let Claude do the cloud steps itself
In Claude Code, run `/permissions` and allow these commands:
- `npx -y supabase@2.122.0 db push --linked`
- `npx -y supabase@2.122.0 db query --linked`

Only do this if your team agrees that Claude may change the shared cloud database.
