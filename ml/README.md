# PULSE ML: next-day morning blood-pressure estimate

Doctor-only model estimate, trained on **synthetic data**. It is not a measurement, not clinically validated, never used for alerts, and never a basis for medication decisions. Results: [MODEL_CARD.md](MODEL_CARD.md).

## Layout
| path | what |
|---|---|
| `pulse_ml/features.py` | features + eligibility, shared by training and prediction |
| `pulse_ml/train.py` | offline training and evaluation → `artifacts/mbp-v1/` |
| `pulse_ml/predict.py` | batch job → `public.ml_predictions` |
| `artifacts/mbp-v1/model.joblib`, `metadata.json` | trained model (2.6 KB, needs the pinned scikit-learn) + metrics |
| `tests/test_ml.py` | split, leakage, eligibility, determinism, job writes only predictions |

## Commands (Windows, from `ml/`)
```
..\.venv\Scripts\python -m pip install -r requirements.txt
..\.venv\Scripts\python -m pulse_data.simulate csv        # run from the repo root: data/synthetic/ (git-ignored)
..\.venv\Scripts\python -m pulse_ml.train                 # ~70 s; rewrites artifacts/mbp-v1/
..\.venv\Scripts\python -m pulse_ml.predict --all --dry-run
..\.venv\Scripts\python -m pulse_ml.predict --all [--date YYYY-MM-DD]
```
`predict` uses `DATABASE_URL` (default: local stack `127.0.0.1:55322`). It prints only counts per status, never health values. Run it after seeding and before the demo (contract checkpoint C5); a daily schedule can come later.

## Inference output contract (for the backend)
**Input it reads:**
- `measurements` with `validation_status = 'valid'`, of patients with an **active** row in `doctor_patient_assignments`.
- Readings strictly before the start of the target day, in the reading's `measured_tz` (else the profile `timezone`).

**Output it writes:** one row per patient, target day and model version in `public.ml_predictions`. Re-runs upsert the same row.
| column | value |
|---|---|
| `target_date` | patient-local day being estimated (default: tomorrow in the patient's time zone) |
| `target` | `morning_mean_bp` = mean of that day's readings before 12:00 local |
| `status` | `ok`, or `insufficient_history` when the 7 days before the target day have < 6 valid readings, < 4 days with readings, or no morning reading |
| `predicted_systolic`, `predicted_diastolic` | mmHg, 1 decimal; **null unless `ok`** (DB CHECK) |
| `interval_*_low/high` | ± split-conformal half-width (90 % nominal on synthetic validation patients); null unless `ok` |
| `model_version` | `mbp-v1` |
| `trained_on` | `synthetic:pulse-sim-v1` |
| `features_until` | start of the target day (patient-local), the cutoff for every input |
| `n_readings_used` | valid readings in the 7-day window |

**Backend mapping** to `PredictionOut` (endpoint 24, doctor only):
- Read the latest row for `(patient_id, target_date)`, preferring the newest `model_version`.
- No row → `model_unavailable`.
- `interval = {systolic: [low, high], diastolic: [low, high]}`, `generated_at = created_at`.
- `limitations` = the fixed contract text.

**Never:** the job does not write alerts, measurements or anything outside `ml_predictions`, and it is never called from a patient request.

## Ring monitor (ML phase 2): advisory flags for the doctor
Built as required by the backend review (`PULSE_ML_phase2_review.pdf`). **Flags never create alerts and are not the safety path.** The proposed safety rule R-RING-1 (`pulse_ml/reference.py: R_RING_1`) is for the backend to evaluate directly on `wearable_samples`.

| Command (from `ml/`) | What |
|---|---|
| `..\.venv\Scripts\python -m pulse_ml.ring_train` | trains IsolationForest on synthetic personal z-scores, scores all methods on test patients → `artifacts/ring-v1/` |
| `..\.venv\Scripts\python -m pulse_ml.monitor --nights` | night windows (00:00–06:00 local) of assigned patients: reference, personal baseline or approved band, IsolationForest |
| `..\.venv\Scripts\python -m pulse_ml.monitor --follow --every 5` | live 10-minute windows; polls `wearable_samples` by `created_at` with a 5-minute overlap; never re-flags a window |
| `..\.venv\Scripts\python -m pulse_data.stream --scenario spo2_dip --minutes 1` (repo root) | **simulated** live ring samples for every demo patient (scenario on Nadia by default); refuses a cloud URL without `--i-confirmed-cloud` |

**Inputs:** `wearable_samples` of actively assigned patients, `patient_bands` (active), and doctor-confirmed flags (left out of the baseline).
**Output:** rows in `wearable_flags`. Nothing else is written.
| kind | window | rule |
|---|---|---|
| `outside_reference` | night or live_10min | deterministic: SpO2 below 94 % (BTS) or resting heart rate above 100 bpm; live windows need ≥ 2 samples |
| `personal_anomaly` | night | the doctor-approved band if one exists, else robust z > 3.5 against the patient's own 28 previous days (≥ 14 nights, confirmed anomalies excluded) |
| `personal_anomaly` | live_10min | outside an active `live_10min_median` band in 2 consecutive windows |
| `multivariate_anomaly` | night | IsolationForest (`ring-v1`) on the 4 personal z-scores |

Night statistic: the night **median** for every metric. For SpO2 (6 samples per night) the median avoids flagging the normal dips of healthy sleepers (mean lowest saturation 90.4 %, Gries & Brooks 1996).

**Backend to build:**
- doctor flag review (`review_status`, `reviewed_by` = the doctor, `reviewed_at`, `review_note`)
- band approval through `private.approve_band(band_id, doctor_id, low, high)`
- rule R-RING-1 on raw samples

**Chronic conditions** (`patient_profiles.condition_codes`) change the rules:
- **COPD:** the SpO2 limit is 88 % (BTS) and band proposals use the COPD range.
- **Atrial fibrillation:** HRV is never flagged and the multivariate score is skipped.
- **Sleep apnea:** it is not a rule change; low night SpO2 is flagged for the doctor.

**Local demo (verified 30 Oct 2026; every demo patient has a simulated ring, 28 days):**
1. **`monitor --nights`:** 34 flags.
   - Karim's seeded heart-rate rise is caught as `personal_anomaly` on its 2 nights.
   - Karim and Samir (sleep apnea) get low night SpO2 flags.
   - Fatima (COPD, night SpO2 about 92 %) gets **no** SpO2 flag: her limit is 88 %. Before the COPD rule she had 5 false flags.
   - Houria (atrial fibrillation) gets no HRV flag.
2. **`monitor --follow` + `stream --scenario spo2_dip --minutes 1`** (default patient Nadia): a live `outside_reference` SpO2 flag for Nadia within about 10 s.
3. **`weekly`:** 11 reports and 43 band proposals; Fatima's proposed SpO2 band is 89.8–92.8 %, waiting for the doctor.

## Training commands (all from `ml/`, synthetic data from `python -m pulse_data.simulate csv` at the repo root)
| Command | Model | Time |
|---|---|---|
| `..\.venv\Scripts\python -m pulse_ml.train` | `mbp-v1` next-day morning BP (**served**) | ~70 s |
| `..\.venv\Scripts\python -m pulse_ml.ring_train` | `ring-v1` ring monitor (IsolationForest + evaluation of all flag methods) | ~15 s |
| `..\.venv\Scripts\python -m pulse_ml.classify` | `wcls-v1` weekly P(next week above target) | ~40 s |
| `..\.venv\Scripts\python -m pulse_ml.mbp_v2` | `mbp-v2` experiment vs v1 (**not served**) | ~80 s |
Metrics and their honest reading: [MODEL_CARD.md](MODEL_CARD.md).

## Weekly doctor loop
| Command (from `ml/`) | What |
|---|---|
| `..\.venv\Scripts\python -m pulse_ml.weekly [--week YYYY-MM-DD]` | one report per patient actively assigned at job time; week = patient-local Monday–Sunday (default: last full week) |
| `..\.venv\Scripts\python -m pulse_ml.feedback` | exports doctor-reviewed flags as labels (git-ignored `data/feedback/`) and says whether there are enough (≥ 30) |
| `..\.venv\Scripts\python -m pulse_ml.feedback --gate <candidate metadata.json>` | regression gate: a retrained ring model must not lose injected-episode recall; deployment stays manual |

**`weekly_reports` row:**
- `home_bp_category`: ACC/AHA 2017 home column, from the week's valid readings.
- `control_status`: vs the active `care_plans` target, default 140/90; insufficient_data if fewer than 3 readings.
- `next_week_above_target_prob`: from `wcls-v1` when that week has ≥ 3 valid readings, built with the same `week_examples()` as in training.
- `model_versions`.
- `summary`, numbers only: BP means and target, ring night values, flag counts by kind and review status, latest mbp estimate.

A report the doctor already reviewed is never overwritten.

**`patient_bands` proposals:**
- Median of the last 28 nights ± max(3 × robust SD, floor).
- Never more permissive than the reference on the safety side.
- Status `proposed`, one open proposal per metric. Only `private.approve_band` (doctor) activates a band; from then on the monitor uses the band instead of the learned baseline.

**Feedback rules (review M5):**
- Labels retune only `personal_anomaly` thresholds, never the reference or safety values.
- At least 30 labels are needed.
- The injected-episode recall is the gate.
- No automatic deployment.

**Verified locally (30 Oct 2026):**
- 11 reports, 12 band proposals.
- A test runs the weekly job, has the doctor approve and edit Karim's heart-rate band through RLS, re-runs the monitor, and checks that the flags now cite `band:<id>`.

## Demo scenarios (local seed, 30 Oct 2026, target = next day)
| demo patient | seed scenario | job result | why it is useful in the demo |
|---|---|---|---|
| Amina | controlled | `ok`, about 127/79 (7-day mean 125/78) | stable patient: estimate stays near target |
| Karim | rising trend, gaps | `ok`, about 159/97 (7-day mean 153/94) | the estimate continues the upward trend, above the plain average |
| Nadia | severe event + chest pain | `ok`, about 153/96 | ML stays separate: the emergency came from the rules, not the model |
| Yacine | unassigned, sparse | **no row** | the job skips patients without an assigned doctor |
| 8 cohort patients (risk factors from STEPS shares) | assigned | `ok` for all 8 | fuller doctor list (11 assigned patients) |
| any patient, `--date` 20 days ahead | – | `insufficient_history` | shows the eligibility rule |
Values move slightly with each re-seed, because seed timestamps are relative to "now".
