# PULSE model cards (30 Oct 2026)

| model | what | trained on | status |
|---|---|---|---|
| **`mbp-v1.1`** | tomorrow's morning BP, for the doctor | synthetic `pulse-sim-v2` (BP variation calibrated on a real home-BP series) | **served** |
| `ring-v1.1` | ring monitoring (advisory flags) | synthetic ring data built from published values | served (flags only) |
| `wcls-v1.1` | P(next week's home BP above target) | synthetic `pulse-sim-v2` | in the weekly report |
| `mbp-v2.1` | mbp-v1.1 + ring features | synthetic | experiment, not served |
| `wrisk-v1` | P(BP uncontrolled despite treatment) | **real** NHANES (2,309 people) | evaluated, **not shown** (too weak) |
| `live-v1` | live ring: warn the doctor BEFORE SpO2 / HR / temperature cross a limit; night going badly | synthetic minute-level nights (`live_sim`) | built; M9 in the cloud (kept by Ayoub, 31 Oct); engine inactive (freeze) |

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

## `live-v1`: live ring, warns BEFORE a limit is crossed (30 Oct 2026)
> **SIMULATOR-ONLY RESULTS.** Every live-v1 figure below (warning rates, lead times, false warnings per night, restless-night figures, forecast errors, speed) comes from 700 + 700 **simulated** nights. None of it is real-world or clinical validation.

- **Use:** in `monitor --follow` the engine checks every new minute; written as M9 `wearable_flags` rows; advisory, doctor only.
- **Data (simulated only):** `pulse_data.live_sim`, 700 simulated training nights (seed 11) and 700 **unseen simulated** test nights (seed 2027). There's no real minute-level ring data, so slopes, wake-up bouts and artefacts are assumptions.
- **Models:**
  - forecast of the value at +10 / +20 min: gradient boosting on past-only features
  - early warning: P(limit crossed within 20 min), gradient-boosting classifier. Thresholds were chosen on 140 held-out training nights (≤ 0.05 false warnings per night): HR 0.35, SpO2 0.45, temperature 0.85.
  - restless night: logistic regression at the 30-minute checkpoints
- **Why not a linear forecast:** a first ridge version learned "it comes back to normal" (most blips do) and never warned.

| test situation (unseen simulated nights) | nights | warned before the limit was crossed | warning came (median, IQR) | existing "limit crossed now" rule |
|---|---|---|---|---|
| oxygen falling | 93 | **93.5 %** | **17 min before** (13–21) | 7 min after |
| heart rate climbing | 103 | **97.1 %** | **20 min before** (16–24) | 9 min after |
| fever starting (temperature) | 73 | **94.5 %** | **17 min before** (13–22) | (no rule) |

**Early warnings on nights with nothing planted:**

| night | early warnings per night |
|---|---|
| normal | 0.04 |
| loose ring / bathroom spike | 0.03 |
| restless (heart-rate wake-ups) | 0.11 |
| sleep apnea | 0 |

The existing "now" rule flagged low oxygen on 98.3 % of sleep-apnea nights.

**Restless night:**
- Restless nights were warned in 94.9 % of cases, at a median of **01:00**; 1.5 % of other nights were warned.
- AUROC: 0.966 at 01:00, 0.979 at 02:00, 0.986 at 03:00.

| forecast error (mean absolute) | +10 min | +20 min | "same as now" (+20) | straight-line trend (+20) |
|---|---|---|---|---|
| heart rate (bpm) | 2.56 | 2.86 | 3.61 | 7.43 |
| SpO2 (%) | 0.38 | 0.39 | 0.52 | 1.05 |
| skin temperature (°C) | 0.058 | 0.064 | 0.078 | 0.171 |

**Speed:** about **44 ms per new minute** per patient (p95 81 ms). Replaying 20 nights one minute at a time gave exactly the same warnings as scoring each whole night at once.

**Reading:** on these simulated situations the engine warns about 17–20 minutes before the limit, where the existing rule reacts about 7–9 minutes after it, with few false warnings. The situations come from my simulator, so these numbers show the mechanism works. They don't measure real-world accuracy, which needs a real ring and doctor-reviewed flags.

### Clinician review
All of these were reviewed and accepted by the team's medical mentor on 30 Oct 2026, for prototype use. The review covers the settings, not the results: the results above stay simulator-only.

| parameter | value | where |
|---|---|---|
| SpO2 limit used as a forecast trigger | 94 %; COPD 88 % | `live.py` (from `reference.py`) |
| heart rate limit during sleep | 100 bpm (or the doctor's live band) | `live.py` (from `reference.py`) |
| skin temperature limit | personal night normal + 1.0 °C | `live.FEVER_RISE` |
| P(limit crossed within 20 min) threshold, per metric | heart rate 0.35; SpO2 0.45; skin temperature 0.85 | `artifacts/live-v1` (chosen on held-out simulated training nights, ≤ 0.05 false warnings per night) |
| forecast horizon | 20 min | `live.WARN_WITHIN` |
| persistence | candidate 2 minutes in a row | `live.py` |
| quiet period | 30 min per patient and metric | `live.QUIET_MINUTES` |
| freshness gate | no early warning if the newest sample is older than 2 min | `monitor.py` |
| restless night | P ≥ 0.7, from 01:00, every 30 min | `live.SLEEP_P`, `SLEEP_FROM`, `SLEEP_EVERY` |
| `ring-v1.1` night personal anomaly | robust z > 3.5 against the patient's last 28 days | `ring.Z_LIMIT` |
| R-RING-1 (backend safety rule) | SpO2 10-min median < 94 % with ≥ 2 samples → prompt a cuff reading, a symptom check and re-seating the ring | `reference.R_RING_1` |

## 30-day day-by-day test on patients no model has seen (30 Oct 2026)
`python -m pulse_ml.backtest` → `artifacts/backtest-30d/results.json`.
- **Data:** a new synthetic cohort (`pulse-sim-v2`, seed 2026, keys `H0001–H0100`; training used `S0001–S0200`). No patient, day or ring profile overlaps training.
- **Method:** frozen models, nothing retrained. Days 1–60 are history and the test days are 2–31 March. On each test day every model sees only earlier data (same feature code as serving) and is scored against what happened.

| next-morning BP, 2,271 patient-days | systolic MAE (95 % CI) | diastolic MAE (95 % CI) | within 10 mmHg (sys) |
|---|---|---|---|
| "same as yesterday" | 9.50 (9.21–9.80) | 5.48 (5.30–5.65) | 60.9 % |
| "7-day mean" | 8.41 (8.17–8.69) | 4.83 (4.66–5.01) | 65.9 % |
| **mbp-v1.1** | **7.88 (7.65–8.11)** | **4.56 (4.41–4.71)** | **68.6 %** |
| mbp-v2.1 | 7.88 (7.65–8.11) | 4.56 (4.41–4.71) | 68.9 % |

mbp-v1.1 had a lower error than "same as yesterday" on 30 / 30 days and than the 7-day mean on 28 / 30 days. Its interval covered the real value 90.7 % / 91.0 % of the time (target 90 %). mbp-v2.1 beat v1.1 on 15 / 30 days.

| ring, 2,703 nights, 14 planted events | events found | other flags / patient-week |
|---|---|---|
| medical limit only | 6 / 14 | 1.12 (433 of 443 flags are real low night SpO2 in the 31 sleep-apnea patients) |
| **personal baseline, z > 3.5** | **13 / 14** (HR 7/7, HRV 2/2, SpO2 4/5) | 0.22 |
| IsolationForest | 9 / 14 | 0.08 |

| weekly classifier, 400 predictions | AUROC (95 % CI) | Brier |
|---|---|---|
| **wcls-v1.1** | **0.963 (0.937–0.980)** | **0.072** |
| "status persists" | 0.881 (0.831–0.919) | 0.100 |
| 40 weeks where the status changed: wcls-v1.1 | 0.055 | 0.555 |

**REAL external test, wrisk-v1 on NHANES Aug 2021–Aug 2023** (a later survey it never saw; 1,851 treated adults, 31.1 % uncontrolled):
- wrisk-v1: AUROC 0.596 (0.568–0.624), weighted 0.592
- age + sex: 0.565 (0.534–0.597)

It's stable but weak, so it stays hidden. In the 2021–2023 survey the exam weight is `WTMEC2YR` and BP medicine is `BPQ150`, with the meaning checked against the CDC codebooks.

**Not testable on real data:** next-day BP and the weekly classifier need daily home BP of many patients, and no open dataset has it.

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
