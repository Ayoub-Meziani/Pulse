# Model card: `mbp-v1` (next-day morning blood pressure)

**Status:** prototype for a hackathon demo. **Trained and tested on synthetic data only.** No real patient has been used; the numbers below say nothing about real-world accuracy.

## Use
- **For:** an informational estimate in the **doctor's** view, labelled "Model estimate (synthetic training data)".
- **Not for:** diagnosis, emergency decisions, alerts, or any medication change. It is never shown to patients. The deterministic safety rules work without it.

## Target and inputs
- **Target:** the next patient-local day's morning mean systolic and diastolic (readings before 12:00).
- **Inputs:** valid readings from the 7 days before the target day only. 21 features: last morning value, 7-day and 3-day means, 7-day morning mean, 7-day slopes, day-to-day spread, morning−evening gap, counts, and day of week. No lifestyle, adherence or demographic inputs.
- **Eligibility:** ≥ 6 valid readings on ≥ 4 days in those 7 days, including ≥ 1 morning reading. Otherwise `insufficient_history`.

## Data
- **Source:** `data/synthetic/readings.csv`, generator `pulse-sim-v1`, seed 7: 200 fictional patients × 90 days, morning and evening sessions.
- **Cleaning:** readings the DB policy `pulse-v1` would not mark valid are dropped (e.g. the about 0.3 % of simulated swapped entries).
- **Known limitation:** the generator's effects (trend, AR(1) day-to-day noise, morning surge, missed-dose and lifestyle effects) are **invented**. The model learns the generator, not human physiology.

## Method
- **Split:** by patient, 70 / 15 / 15 (seed 7): 140 / 30 / 30 patients; 8,781 / 1,955 / 1,806 examples. No patient appears in two sets.
- **No leakage:** every feature comes from days strictly before the target day. Scaling is fitted on training patients only.
- **Candidates:** ridge regression (standardised, alpha 1.0) and histogram gradient boosting (200 iterations). Selected on validation mean MAE: ridge 4.155 vs gradient boosting 4.239 → **ridge**.
- **Interval:** split-conformal on the validation patients. Half-width = 90th percentile of the absolute error: ±10.3 mmHg systolic, ±6.9 mmHg diastolic.

## Results on the 30 held-out test patients (synthetic), scored once
MAE and RMSE in mmHg, 95 % bootstrap CI over patients (1,000 resamples).
| method | systolic MAE | systolic RMSE | diastolic MAE | diastolic RMSE |
|---|---|---|---|---|
| baseline: yesterday's morning value | 6.30 (5.97–6.62) | 7.95 (7.59–8.31) | 4.16 (3.96–4.34) | 5.26 (5.03–5.47) |
| baseline: 7-day mean | 5.68 (5.45–5.91) | 7.21 (6.94–7.49) | 3.44 (3.30–3.58) | 4.34 (4.18–4.48) |
| **mbp-v1 (ridge)** | **5.23 (5.00–5.48)** | **6.65 (6.36–6.93)** | **3.31 (3.16–3.44)** | **4.13 (3.98–4.28)** |

- **Interval coverage on test:** 87.9 % systolic, 90.9 % diastolic (nominal 90 %).
- **Reading the result:**
  - The model beats both baselines on systolic, and the confidence intervals do not overlap with the 7-day mean.
  - On diastolic the gain over the 7-day mean is small and the intervals overlap.

## Reproduce
From a clean checkout:
1. `python -m pulse_data.simulate csv` (repo root)
2. `python -m pulse_ml.train` (in `ml/`)

This writes `artifacts/mbp-v1/metadata.json` with the same split and metrics. The pins are in `ml/requirements.txt`.

## Before any real use
- Real, consented home readings: no open multi-patient home-BP dataset was found (`docs/data/DATA_SOURCES.md`).
- Retraining and evaluation on real data, by patient and over time.
- Clinician review of the use, wording and display.
- Monitoring for drift.
