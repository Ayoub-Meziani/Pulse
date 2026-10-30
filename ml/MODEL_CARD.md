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

---

# Model card: `ring-v1` (ring monitoring, advisory)
**Status:** prototype; **synthetic ring data with invented coupling and injected, labelled episodes.** Its flags are advisory, for the doctor only. They never create alerts and are not the safety path.

- **Inputs:** night windows (00:00–06:00 local) built from raw `wearable_samples` by the same code in training and serving (`ring.py`): night **medians** of heart rate, HRV, SpO2 and skin temperature. SpO2 uses the median because healthy sleepers dip (mean lowest saturation 90.4 %, Gries & Brooks 1996).
- **Chronic conditions** (`condition_codes`, M8):
  - COPD moves the SpO2 reference to 88 % (BTS).
  - With atrial fibrillation, HRV and the multivariate score are skipped.
- **Personal baseline:** median and MAD of the 28 days strictly before the night, at least 14 nights, doctor-confirmed anomaly windows excluded. A doctor-approved band overrides it.
- **IsolationForest:** 100 trees, `contamination = 0.01` (a synthetic setting, tuned to the simulator's invented episode rate), fitted on all nights of the training patients' personal z-scores.
- **Data:** `wearable_samples.csv`, 200 patients × 90 days (about 10 % of days not worn).
  - Ring values are drawn from published figures (`docs/data/DATA_SOURCES.md`).
  - Chronic conditions: diabetes 17.5 %, COPD 3.6 %, sleep apnea 30 % (assumption), atrial fibrillation 2 % (assumption).
  - 67 injected episodes (`hr_rise` +15 bpm, `spo2_dip` −5 %, `hrv_drop` −40 %, 1–3 nights).
  - Patient-level split 140 / 30 / 30 (seed 7).

**Results on the 30 test patients (7 episodes), synthetic:**
| method | episodes detected | night precision | false flags / patient-week |
|---|---|---|---|
| reference only (SpO2 < 94 or COPD < 88, resting HR > 100) | 2 / 7 (0.29) | 0.03 | 0.39 |
| **personal baseline (robust z > 3.5)** | **6 / 7 (0.86)** | 0.11 | 0.26 |
| IsolationForest | 3 / 7 (0.43) | 0.20 | 0.05 |
| personal or IsolationForest | 6 / 7 (0.86) | 0.11 | 0.27 |

**Reading:**
- The personal baseline finds what population ranges miss.
- Reference-only flags now come mostly from sleep-apnea patients, whose night SpO2 is genuinely low. That's useful for the doctor, but it counts as "false" against the injected episodes.
- IsolationForest is the most precise and the least sensitive.
- 7 episodes is a small test set.
- **The episode recall on injected episodes is the regression gate** for any retraining with doctor feedback: recall must not drop (review M5).

**Limits:**
- The episodes and the ring↔BP coupling are invented.
- Consumer ring SpO2 is less accurate than a clinical oximeter, and can be overestimated in people with darker skin (FDA 2021).
- No real ring data has been used.

---

# Model card: `wcls-v1` (weekly classifier, doctor report)
- **Question:** will next week's mean of valid home readings be at or above the patient's target? The rule is **systolic OR diastolic**.
- **Targets:** per-patient synthetic targets (135/85 or 130/80, `patients.csv`); in production, the care-plan target.
- **Output:** `weekly_reports.next_week_above_target_prob`. Shown to the doctor as a probability, never an alert or a treatment suggestion.
- **Features:** that week only, built by the same `week_examples()` in training and serving: means, morning / evening, within-week slope and spread, last 3 days, gap to target, current status. The ring variant was tried as well.
- **Selection** on validation AUROC:

  | variant | validation AUROC |
  |---|---|
  | logistic regression, BP only (**chosen**) | 0.9921 |
  | logistic regression, BP + ring | 0.9909 |
  | gradient boosting, BP only | 0.9898 |
  | gradient boosting, BP + ring | 0.9873 |

  **Ring features add nothing here.**
- **Split:** patients 70 / 15 / 15 (seed 7); weeks 1,795 / 387 / 385.

| test set (synthetic) | model AUROC | baseline "status persists" AUROC | model balanced acc. | baseline balanced acc. | model Brier | baseline Brier |
|---|---|---|---|---|---|---|
| all 385 weeks | **0.985** (0.962–0.997) | 0.927 (0.872–0.969) | 0.924 | 0.927 | **0.049** | 0.070 |
| 27 weeks where the status changes | 0.022 | 0.000 | 0.071 | 0.000 | 0.542 | 1.000 |

(Retrained 30 Oct after the ring data and synthetic targets were regenerated; same conclusions as the first run.)

**Honest reading (review M7):**
- The model is better ranked and better calibrated than "status persists" overall.
- Its yes / no accuracy is the same as the baseline.
- On the weeks that actually change status it is **worse than chance**: it mostly follows the current status, because synthetic week-to-week changes are near-target noise.
- Use it as a calibrated "how close to the line" probability for the doctor, **not** as a predictor of change.

---

# Experiment: `mbp-v2` (mbp-v1 features + ring night features), NOT served
Same examples and same split as mbp-v1. Ring features: last night and 7-night means (heart rate, HRV, SpO2, skin temperature), from nights strictly before the target day.

| test (synthetic), MAE mmHg | systolic | diastolic |
|---|---|---|
| v1 features (ridge) | 5.23 (5.00–5.48) | 3.31 (3.16–3.44) |
| v2 features (ridge) | 5.19 (4.96–5.43) | 3.28 (3.13–3.41) |

- **Comparison:**
  - v2 is ahead on validation by 0.03 mmHg, and the confidence intervals overlap completely.
  - The simulator's ring↔BP coupling is invented, so any gain is by construction.
- **Decision:** mbp-v1 stays served (contract §4); switching needs a real win and the backend's agreement.

---

# Real-data results (30 Oct 2026; sources and terms in `docs/data/DATA_SOURCES.md`)

## `wrisk-v1`: trained on REAL people (NHANES), NOT used in reports
- **Question:** is a treated adult's BP uncontrolled (mean exam BP ≥ 140/90, systolic OR diastolic)?
- **Features:** only ones PULSE stores (age, sex, BMI, waist, smoking, diabetes, high cholesterol, kidney disease, COPD, heart failure, stroke).
- **Data:** 2,309 US adults taking BP medicine; person split 1,616 / 346 / 347; survey weights used. 31 % uncontrolled (weighted, test set).
- **Selection:** logistic regression chosen on validation (weighted AUROC 0.568 vs 0.511 for gradient boosting).

| test (347 real people) | AUROC | weighted AUROC | balanced accuracy | Brier |
|---|---|---|---|---|
| wrisk-v1 | 0.601 (0.540–0.664) | 0.623 | 0.528 | 0.225 |
| baseline: age + sex only | 0.622 | 0.611 | – | 0.227 |

**Reading:**
- On real data these risk factors **cannot** tell whose BP will be controlled under treatment; the model is no better than age and sex.
- Sensitivity analysis with 130/80: weighted AUROC 0.624.
- Because an almost random score would mislead a doctor, it is **not** shown in weekly reports.
- Its value is the finding itself: control has to be **measured** (PULSE's readings), not guessed from a profile.

## `mbp-v1` on real home readings (Mendeley, 1 patient)
- **Not applicable:** mbp-v1 needs ≥ 6 readings on ≥ 4 days in 7, and this series has 1 measurement every 3 days and no clock times.
- **Realism check:** systolic change between measurements 3 days apart is 10.0 mmHg in the real patient against 6.5 in synthetic treated patients sampled the same way (SD 11.7 vs 6.7; lag-1 correlation 0.40 vs 0.24).
- **Conclusion:** the simulator is too smooth, and real errors will likely exceed the synthetic 5.2 mmHg.
- **Next step (proposed, not done):** a `pulse-sim-v2` with real-sized noise, then retrain mbp-v1 (needs a deliberate fingerprint update).

## `ring-v1` SpO2 rules on real overnight recordings (PhysioNet Apnea-ECG)
| group | recordings | night median SpO2 | ODI-4 / hour | time < 90 % | ring rule flagged (median of 6 samples < 94 %) |
|---|---|---|---|---|---|
| apnea | 4 | 86–92 % | 61 | 48 % | **4 / 4** |
| borderline | 1 | 96 % | 1.5 | 0.5 % | 0 / 1 |
| control | 3 | 95–96 % | 0.9 | 0.2 % | **0 / 3** |

**Reading:**
- The ring-cadence night-median rule separated apnea from non-apnea nights perfectly.
- The night **minimum** would not: controls reach 57–69 % from sensor artefacts.
- The simulator's sleep apnea is milder than these real severe cases.
- It's a sleep-lab oximeter, not a ring, and only 8 nights: a sanity check, not a validation.

## Before any real use
- Real, consented home readings: no open multi-patient home-BP dataset was found (`docs/data/DATA_SOURCES.md`).
- Retraining and evaluation on real data, by patient and over time.
- Clinician review of the use, wording and display.
- Monitoring for drift.
