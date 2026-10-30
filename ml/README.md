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
