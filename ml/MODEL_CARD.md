# PULSE model cards (30 Oct 2026)

| model | what | trained on | status |
|---|---|---|---|
| **`mbp-v1.1`** | tomorrow's morning BP, for the doctor | synthetic `pulse-sim-v2` (BP variation calibrated on a real home-BP series) | **served** |
| `ring-v1.1` | ring monitoring (advisory flags) | synthetic ring data built from published values | served (flags only) |
| `wcls-v1.1` | P(next week's home BP above target) | synthetic `pulse-sim-v2` | in the weekly report |
| `mbp-v2.1` | mbp-v1.1 + ring features | synthetic | experiment, not served |
| `wrisk-v1` | P(BP uncontrolled despite treatment) | **real** NHANES (2,309 people) | evaluated, **not shown** (too weak) |

All models are Python (pandas, numpy, scikit-learn). None of them creates alerts, decides an emergency or touches medication. Sources and data terms: `docs/data/DATA_SOURCES.md`.

---

## `mbp-v1.1`: next-day morning blood pressure (served)
- **Use:** an informational estimate in the **doctor's** view, labelled "Model estimate (synthetic training data)". Not for diagnosis, alerts or medication changes; never shown to patients.
- **Target:** the next patient-local day's morning mean systolic and diastolic (readings before 12:00).
- **Inputs:** valid readings from the 7 days before only. 21 features: last morning, 7-day and 3-day means, morning mean, slopes, spread, morning−evening gap, counts, day of week.
- **Eligibility:** ≥ 6 readings on ≥ 4 days, including ≥ 1 morning reading.

**Data and method:**
- **Data:** synthetic `pulse-sim-v2`, 200 patients × 90 days.
  - Day-to-day BP variation is **calibrated on a real home-BP series** (Mendeley pjcv33hpp7). Measured every 3 days, systolic SD / change / correlation is 11.8 / 10.0 / 0.41 in the simulation vs 11.7 / 10.0 / 0.40 in the real series.
  - The first generator (v1) was too smooth (6.7 / 6.5 / 0.24).
- **Split:** by patient 70 / 15 / 15 (seed 7): 140 / 30 / 30 patients, 8,730 / 1,918 / 1,929 examples. No patient in two sets; features only from earlier days.
- **Model:** ridge regression, chosen on validation (MAE 6.18 vs 6.30 for gradient boosting).

**Results on the 30 test patients** (MAE / RMSE in mmHg, 95 % bootstrap CI over patients):
| method | systolic MAE | systolic RMSE | diastolic MAE | diastolic RMSE |
|---|---|---|---|---|
| "same as yesterday's morning" | 9.56 (9.24–9.89) | 12.04 | 5.77 (5.58–5.97) | 7.31 |
| "7-day mean" | 8.29 (7.98–8.59) | 10.42 | 4.85 (4.70–4.99) | 6.11 |
| **mbp-v1.1** | **7.75 (7.49–8.00)** | **9.80** | **4.67 (4.55–4.80)** | **5.87** |

- **Interval:** split-conformal, ±16.2 / ±9.6 mmHg; it covered the real value 90.1 % / 89.5 % of the time (target 90 %).
- **Reading:**
  - The error is larger than v1's 5.2 mmHg because the data is now as variable as real home BP. This is the more honest number.
  - The model still beats both simple methods, with confidence intervals that don't overlap.
- **Real-data check:** the only open real home series (1 patient) is measured every 3 days, so mbp-v1.1 cannot run on it directly. It was used to calibrate the simulator instead.

---

## `ring-v1.1`: ring monitoring (advisory)
- **Inputs:** night medians (00:00–06:00 local) of heart rate, HRV, SpO2 and skin temperature, built from raw `wearable_samples` by the same code in training and serving.
- **Chronic conditions:** COPD moves the SpO2 limit to 88 % (BTS). With atrial fibrillation, HRV and the multivariate score are skipped.
- **Flags:**
  - outside the medical reference (SpO2 < 94 %, resting HR > 100)
  - outside the patient's own 28-day normal (robust z > 3.5), or outside the doctor-approved band
  - IsolationForest (contamination 0.01, a synthetic setting)
- **Data:** synthetic ring samples for the same 200 × 90 cohort; 67 injected episodes (`hr_rise` +15 bpm, `spo2_dip` −5 %, `hrv_drop` −40 %).

| method (synthetic) | test: episodes found | test: false flags / patient-week | validation: episodes found |
|---|---|---|---|
| reference only | 2 / 7 | 0.39 | – |
| **personal baseline, z > 3.5** | **3 / 7** | 0.27 | **7 / 10** (0.22 false / patient-week) |
| IsolationForest | 1 / 7 | 0.06 | – |

**Threshold choice (validation patients only):**
| z | episodes found | false flags / patient-week |
|---|---|---|
| 2.5 | 9 / 10 | 0.91 (about one false flag per patient every week) |
| 3.0 | 7 / 10 | 0.44 |
| **3.5 (kept)** | **7 / 10** | **0.22** |

- **Reading:**
  - With realistic day-to-day variation, a personal normal is wider, so moderate changes are harder to see.
  - The doctor-approved band (weekly loop) is how the threshold becomes patient-specific.
  - 7 and 10 episodes are small samples.
- **Regression gate:** episode recall is the gate for any retraining with doctor feedback (review M5).

**Real data, PhysioNet Apnea-ECG (8 real overnight SpO2 recordings):**
| group | recordings | night median | ODI-4 / hour | flagged by the ring rule (median of 6 samples < 94 %) |
|---|---|---|---|---|
| apnea | 4 | 86–92 % | 61 | **4 / 4** |
| borderline | 1 | 96 % | 1.5 | 0 / 1 |
| control | 3 | 95–96 % | 0.9 | **0 / 3** |

- The night **minimum** would fail: controls reach 57–69 % from sensor artefacts.
- A sleep-lab oximeter, not a ring, and only 8 nights: a sanity check, not a validation.

---

## `wcls-v1.1`: weekly "next week above target" (in the weekly report)
- **Label:** next week's home mean ≥ target (systolic OR diastolic).
- **Selection:** logistic regression on BP features, chosen on validation (AUROC 0.959). The ring features did not help (0.956).

| test (387 weeks, synthetic) | AUROC | balanced accuracy | Brier |
|---|---|---|---|
| **wcls-v1.1** | **0.954** (0.922–0.978) | 0.892 | **0.080** |
| "status persists" | 0.871 (0.821–0.915) | 0.871 | 0.124 |
| 48 weeks where the status changes: wcls-v1.1 | 0.126 | 0.210 | 0.508 |

**Reading:** better ranked and calibrated than "nothing changes", but no skill on weeks that actually change. Show it as "how close to the target line", not as a predictor of change.

---

## `mbp-v2.1` (experiment, not served)
| test MAE (synthetic) | systolic | diastolic |
|---|---|---|
| v1.1 features | 7.75 (7.49–8.00) | 4.67 (4.55–4.80) |
| + ring night features | 7.71 (7.45–7.97) | 4.64 (4.51–4.77) |

The 0.04 mmHg gain is within the noise, and the ring↔BP coupling is invented, so mbp-v1.1 stays served.

---

## `wrisk-v1`: trained on REAL people (NHANES), NOT shown in reports
- **Question:** is a treated adult's exam BP ≥ 140/90?
- **Features:** only PULSE fields.
- **Data:** 2,309 US adults taking BP medicine; survey-weighted.
- **Test (347 people):** AUROC 0.601 (0.540–0.664), weighted 0.623; age + sex alone 0.622; balanced accuracy 0.528.
- **Reading:** on real data, these risk factors can't tell whose BP is controlled under treatment. Control has to be **measured**, which is what PULSE does. An almost random score would mislead a doctor, so it isn't displayed.

**Real population bands (NHANES):** survey-weighted seated pulse and BP percentiles by sex × age in `pulse_ml/reference_nhanes.json`. The weekly report places the patient's seated **cuff** pulse in its band; it's context, not a threshold.

---

## History
| version | change |
|---|---|
| `mbp-v1`, `ring-v1`, `wcls-v1`, `mbp-v2` | trained on `pulse-sim-v1`: mbp systolic MAE 5.23 (too optimistic: v1 BP was about half as variable as real home BP); ring 6 / 7 episodes |
| `*.1` (30 Oct 2026) | retrained on `pulse-sim-v2` (calibrated on real home BP). The demo seed stays on v1 so the demo accounts and cloud data are unchanged |

## Before any real use
- Real, consented daily home readings (no open multi-patient set exists).
- Retraining and evaluation on real data, by patient and over time.
- Clinician review of the use, wording and display.
- Monitoring for drift.
