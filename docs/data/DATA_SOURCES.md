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
