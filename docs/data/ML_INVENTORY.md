# PULSE ML inventory

**Update, 30 Oct 2026 (later the same day): the ML workstream is built.** See [`ml/README.md`](../../ml/README.md) (commands, inference output contract, demo scenarios) and [`ml/MODEL_CARD.md`](../../ml/MODEL_CARD.md) (method and test metrics, synthetic only).

## 1. What exists
| item | status |
|---|---|
| Notebooks | none (scripts only) |
| Training / feature / evaluation code | `ml/pulse_ml/train.py`, `features.py` |
| Trained model | `ml/artifacts/mbp-v1/model.joblib` (ridge, 2.6 KB) + `metadata.json` |
| Metrics, model card | `ml/MODEL_CARD.md`: test systolic MAE 5.23 mmHg vs 5.68 (7-day mean) and 6.30 (yesterday), synthetic |
| `ml_predictions` table | migration M4, live in the cloud |
| Batch job | `python -m pulse_ml.predict --all`; no HTTP endpoint (the backend reads the table) |
| ML libraries | numpy, pandas, scikit-learn, joblib (pinned in `ml/requirements.txt`) |

Sections 2–5 below are the original plan; the implementation follows it. Differences: lifestyle features are left out of the MVP (team contract §4), and the interval is split-conformal.

## 2. Data available for ML
The only training-ready dataset is the **synthetic** set described in [DATA_AI_INVENTORY.md §1.2](DATA_AI_INVENTORY.md#12-ml-training-set-synthetic-verified):
- `data/synthetic/readings.csv`: 37,250 rows from 200 patients over 90 days, morning/evening sessions.
- `data/synthetic/daily_context.csv`: 18,000 patient-day rows of medication, missed dose, activity, estimated sodium and sleep.
- Regenerate with `python -m pulse_data.simulate csv`. Generation is deterministic: seed 7, generator `pulse-sim-v1`.
- **Caveat:** the generator has invented effects (missed dose +6 next day, sodium, activity, sleep). Any model will rediscover that formula. Its results demonstrate the pipeline only, not clinical performance.

Real data:
- none
- No open multi-patient longitudinal home blood-pressure dataset was found ([DATA_SOURCES.md](DATA_SOURCES.md)).
- The local DB has 259 synthetic readings for 4 demo patients: too few for training, but usable for an end-to-end inference demo.

## 3. Proposed approach (not implemented; to agree before coding)
**Target:** next-day **morning** mean systolic and diastolic per patient (regression), on days that have a morning reading.

**Features** (only from days ≤ D−1):
- last-reading and 3-day / 7-day means
- 7-day slope
- morning − evening gap
- coverage (readings in the last 7 days)
- previous day's missed dose, activity, estimated sodium and sleep
- day of week

**Preprocessing:**
- Drop rows with systolic ≤ diastolic (same rule as DB policy `pulse-v1`).
- No imputation; a day without a target is not a training row.

**Split and leakage prevention:**
- **Patient-level split** by `patient_key`, e.g. 70/15/15 for train/validation/test, so no patient appears in two sets.
- Time order kept inside each patient.
- Features computed only from strictly earlier days, and repeat readings of the same morning averaged into the target.
- No scaling or statistics fitted on test patients.

**Baselines to beat:**
1. Persistence (yesterday's morning value).
2. 7-day mean.

**Models:**
- regularised linear regression
- gradient boosting (scikit-learn `HistGradientBoostingRegressor`)

**Metrics:**
- MAE and RMSE in mmHg on test patients, against the baselines.
- Calibration of an interval if one is added.
- Always reported as "**synthetic data**".

**Sanity check:** run the trained pipeline on the single-patient Mendeley series, temporal split only. Respect CC BY-NC and keep the file uncommitted.

## 4. How the model would be called from the backend (proposal)
1. A server-side batch job (Python, service role or `DATABASE_URL`) runs daily or on demand:
   - Read valid and needs-review measurements and context for each patient.
   - Compute features with the same code used in training.
   - Write rows to a new `ml_predictions` table: patient_id, target_date, predicted SBP/DBP, interval, model_version, trained_on = `synthetic`, created_at.
   - The table would get RLS (read by the patient and assigned doctor; written by the service role only).
2. Backend and frontend read `ml_predictions` through Supabase like any other table. No model is served to the client.
3. **Optional:** a small HTTP endpoint (FastAPI or edge function) for on-demand prediction. Add it only if the frontend needs it.

**Safety rules (from the spec):**
- Predictions are informational and labelled with the model version and training data.
- They never recommend or change medication.
- They never create emergency alerts. Alerts stay with the deterministic rules.
- They are never stored as measurements.

## 5. What is needed to start
- Agreement on the target and approach in §3.
- Adding `numpy`, `pandas` and `scikit-learn` (pinned) to `requirements.txt`.
- A new migration for `ml_predictions`.
- For anything beyond a demo: real, consented PULSE data or a data-sharing agreement.
