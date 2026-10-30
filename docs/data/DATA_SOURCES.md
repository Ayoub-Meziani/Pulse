# Data sources: what PULSE needs and where it comes from

## Data PULSE needs
| need | used for | source now | real source later |
|---|---|---|---|
| BP readings (sys/dia, pulse, time, method) | history, trends, alerts, ML target/features | simulator seed, manual entry, CSV import | validated cuff (manual/CSV/Bluetooth) |
| Patient time zone | morning/evening, daily windows | profile default `Africa/Algiers` | patient profile |
| Symptoms | emergency rules (independent of BP) | seed, patient entry | patient/bystander entry |
| Care plan targets | above-target rules, coverage vs plan | seed (135/85, 2/day) | doctor entry |
| Medication + adherence events | context, possible ML feature | seed | doctor + patient entry |
| Activity, meals (sodium only if known), sleep | context for the doctor, possible ML features | seed | patient entry / wearable |
| Doctor-patient assignment | access control | seed | admin |

## Synthetic data in this repo (all labelled)
- `supabase/seed.sql`: 6 fictional accounts, 30 days, scenarios controlled / rising / severe event / sparse+dirty (`python -m pulse_data.simulate seed`).
- `data/synthetic/readings.csv` + `daily_context.csv`: 200 patients × 90 days, `is_synthetic=true`, ~0.3% swapped entries to exercise cleaning (`python -m pulse_data.simulate csv`; not committed).
- `samples/readings_sample.csv`: CSV-import demo with 3 deliberately bad rows.

### Demo seed: real statistics, fictional people (30 Oct 2026)
The seed has 12 fictional patients: 4 scenario patients with hand-picked factors, plus 8 "cohort" patients whose risk factors are drawn from published shares (`STEPS_DZ` in `pulse_data/simulate.py`). Every row is labelled `simulated`.

| Value | Source |
|---|---|
| Sex of hypertensive patients (55 % women) | Algerian STEPS 2016–2017: hypertension 34.2 % women vs 28.3 % men ([Moussouni et al. 2022](https://pmc.ncbi.nlm.nih.gov/articles/PMC9386961/)) |
| Age bands 30–44 / 45–59 / 60–69 (39.3 / 27.7 / 11.6 %) | same, sample age distribution (18–29 left out) |
| Smoking current / former / never (11.1 / 11.9 / 76.9 %) | same (overall only; the paper gives no split by sex) |
| Diabetes 17.5 %, high cholesterol 29.6 % | same (overall only) |
| BMI underweight / normal / overweight / obese (3.3 / 36.6 / 35.0 / 24.9 %) | same |
| Abdominal obesity 67.8 % overall, cut-offs waist > 94 cm men / > 80 cm women | same. How it depends on BMI is **assumed** (0 / 36 / 85 / 100 % by BMI band), chosen so the overall share stays 67.8 % and waist stays consistent with BMI |
| **Assumed** (no published Algerian figure found): height (men 172 ± 7 cm, women 160 ± 6 cm), salt-habit answers, bread portions, language, ring values (heart rate, HRV, SpO2, skin temperature), BP levels and trends; names are picked to match the drawn sex | generator choices; labelled here |
With 8 cohort patients, the drawn shares will not match the published percentages exactly; the generator follows the distributions, and a small sample varies.

World context, for the pitch (not used to generate values): WHO estimates about 33 % of adults aged 30–79 have hypertension, about half are unaware, and about 21 % are controlled (WHO *Global report on hypertension*, Sept 2023, as reported by [Down To Earth](https://www.downtoearth.org.in/health/every-1-in-3-adults-has-hypertension-but-only-half-know-it-91822); check the WHO report itself before quoting exact figures). The global mean salt intake is 10.8 g/day against a target of < 5 g ([WHO global report on sodium intake reduction, 2023](https://www.who.int/publications-detail-redirect/9789240069985)).

### Synthetic ring data (ML phase 2, 30 Oct 2026)
`python -m pulse_data.simulate csv` also writes (git-ignored):
- `wearable_samples.csv`: same columns as `public.wearable_samples` + `is_synthetic`.
  - Heart rate every 10 min at night, hourly by day; 6 SpO2 samples per night; nightly HRV and skin temperature.
  - About 10 % of days have no ring data (ring not worn).
- `ring_episodes.csv`: 65 injected, labelled anomaly episodes (`hr_rise`, `spo2_dip`, `hrv_drop`), used to score the ring monitor.
- `patients.csv`: per-patient synthetic home-BP target (135/85 or 130/80) for the weekly classifier.

Ring values come from a separate random generator per patient, so the BP files are byte-identical to before (`tests/test_simulate_stability.py`). The coupling to blood pressure is **invented**: night heart rate +0.25 bpm and HRV −0.3 ms per mmHg of the latent BP effect. The demo seed holds 28 days of ring data for Karim, Nadia and Fatima; Karim has a simulated night heart-rate rise 3 and 2 days before seeding.

### Medical reference values (`ml/pulse_ml/reference.py`, pending clinician review)
| Value | Source |
|---|---|
| Home-BP categories: 120/80, 130/80, 135/85 (= office 140/90), 145/90 (= office 160/100) | 2017 ACC/AHA guideline, Table 11, home (HBPM) column ([ACC summary](https://www.acc.org/~/media/Non-Clinical/Files-PDFs-Excel-MS-Word-etc/Guidelines/2017/Guidelines_Made_Simple_2017_HBP.pdf)). Applied only to home means, never to office grades |
| Resting heart rate 60–100 bpm (adults) | [Mayo Clinic](https://www.mayoclinic.org/healthy-lifestyle/fitness/expert-answers/heart-rate/faq-20057979). The AHA page could not be retrieved; fit people can be normal below 60 |
| SpO2 target 94–98 % (88–92 % if at risk of hypercapnic failure) | [BTS oxygen guideline 2017](https://www.brit-thoracic.org.uk/quality-improvement/guidelines/emergency-oxygen) (O'Driscoll et al., Thorax 2017;72 Suppl 1) |
| SpO2 accuracy limits (darker skin pigmentation, circulation, nail polish) | FDA safety communication, 19 Feb 2021 ([summary](https://www.hpnonline.com/surgical-critical-care/med-surg-equipment/article/21211195/fda-safety-communication-pulse-oximeter-accuracy-and-limitations)) |
| HRV, skin temperature | no population reference used; personal baseline only |

### Real wearable dataset considered (not downloaded)
[PPG-DaLiA](https://archive.ics.uci.edu/dataset/495/ppg+dalia) (UCI, CC BY 4.0): 15 people, wrist PPG with ECG heart-rate ground truth, during daily activities (not rest or night). It is optional: only usable as a real heart-rate series to sanity-check false flags. Credit is required if it is used.

The generator's effects (missed dose +6 mmHg next day, sodium, activity, sleep) are **invented**. A model trained on them demonstrates the pipeline only; metrics on synthetic data say nothing about real patients.

## Public datasets checked for the ML phase (next-day BP forecasting)
The target needs **many patients × many days of timestamped home readings**. Findings (web search, 29 Oct 2026; re-verify licences before use):

| dataset | what it has | licence / access | usable for next-day forecast? |
|---|---|---|---|
| [NHANES oscillometric BP (BPXO, 2017–2020)](https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/P_BPXO.htm) | 3 consecutive readings per participant at one visit, Omron HEM-907XL | public-use files (CDC/NCHS data-use terms) | **No**: cross-sectional, no day-to-day series. Useful for value distributions / plausibility checks |
| [Mendeley "Trends and seasonality… HBPM"](https://data.mendeley.com/datasets/pjcv33hpp7/1) | home SBP/DBP/HR, Microlife BP 3AG1, ~384 days | CC BY-NC 3.0 | **Partly**: one patient only. OK for a single-patient temporal sanity check, not for patient-level evaluation; non-commercial |
| [`bp` R package sample data](https://medrxiv.org/content/10.1101/2022.05.12.22274995v1.full.txt) | small HBPM/ABPM samples (e.g. Omron, twice daily) | software open source; data licence not confirmed | Maybe, small; check licence |
| Ohasama study | large longitudinal home-BP cohort | not public | No |
| MIMIC / ICU waveform sets (PhysioNet) | hospital/ICU arterial BP, PPG | credentialed, DUA | No: ICU, not home monitoring |
| Hilo and other vendors | longitudinal real-world BP | commercial partnership | Not for a hackathon |

**Conclusion:** no openly licensed, multi-patient, longitudinal home-BP dataset was found. Plan for the ML phase:
1. Build and test the full pipeline on the labelled synthetic set (patient-level split by `patient_key`).
2. Run a temporal sanity check on the single-patient Mendeley series (respect CC BY-NC; don't commit the file).
3. Report results as "synthetic / single-patient": no clinical or generalisation claims.
4. Real performance needs real consented data collected through PULSE (or a data-sharing agreement).

Do not commit downloaded datasets; keep them under `data/` (git-ignored) with their licence noted.
