# CSV examples for the in-app import

Every value here is fictional. Try these files on the local stack (`docs/LOCAL_DEVELOPMENT.md`).

- **Blood pressure:** patient → **Historique → Importer un fichier**.
- **Ring:** patient dashboard → **Bracelet** panel.

## The format

**Blood pressure (cuff export)**

| Column | Required | Values |
|---|---|---|
| `measured_at` | yes | `2026-10-22T08:00:00+01:00` or `2026-10-22 08:00`. Without an offset, the time is read in the patient's time zone. |
| `systolic`, `diastolic` | yes | whole numbers, in mmHg |
| `pulse` | no | whole number, in bpm |
| `unit` | no | `mmHg` only |
| `position` | no | `sitting`, `standing` or `lying` |
| `arm` | no | `left` or `right` |
| `note` | no | free text, up to 500 characters |

**Ring export:** `measured_at`, `metric`, `value` are required; `unit` and `external_id` are optional.

| Metric | Unit |
|---|---|
| `heart_rate` | `bpm` |
| `spo2` | `%` |
| `hrv_rmssd` | `ms` |
| `skin_temperature` | `°C` |

Other rules:
- Lines starting with `#` are comments.
- A file whose first line starts with `# SIMULATED` or `# SYNTHETIC` can only be imported as **Données simulées**. Simulated readings never create an alert: the screen shows what the rules would have done.
- Importing the same file twice gives "Ce fichier a déjà été importé".
- Rows that are already stored are counted as duplicates and skipped.

## Fixed examples (old dates: they go to the history)

All four are marked `# SIMULATED`.

| File | What you should see |
|---|---|
| `cuff_minimal.csv` | 4 readings added, no alert. |
| `cuff_all_columns.csv` | 4 readings added, with position, arm and note in the history. |
| `cuff_with_errors.csv` | 4 rows kept, 5 refused, each with its reason (see below). |
| `ring_export.csv` | 6 values added. 2 rows refused, see below. |

The 5 refused rows in `cuff_with_errors.csv`:

| Line | Reason |
|---|---|
| 4 | top number is not a whole number |
| 5 | bottom number is missing |
| 6 | unit is not mmHg |
| 7 | unknown position |
| 8 | the time cannot be read |

Of the 4 rows it keeps, `1/1` and `120/130` are stored as **invalid** and never used.

The 2 refused rows in `ring_export.csv`:
- line 9: heart rate 400, refused by the database;
- line 10: `blood_sugar`, unknown metric.

Ring values never raise an alert.

## Fresh files: try the alerts, the symptom check and the alarm

An imported reading goes through the same rules as a typed one only if it was measured **in the last 10 minutes** and **after your latest reading**. These files must therefore be made just before you upload them:

```
.venv\Scripts\python -m pulse_data.simulate test-csv-now
```

This writes `data\demo\test\` (git-ignored), one reading stamped this minute per file. Upload one within about 8 minutes, without typing a reading in between. Choose **Mesures réelles** for the `TEST_` files.
To try again, wait 2 minutes before making new files: the same values within 2 minutes count as one reading (a duplicate).

| File | What you should see |
|---|---|
| `TEST_now_severe.csv` (186/118) | Severe alert, symptom check, then the 60 s recheck. The alarm starts at once and stops only when the patient confirms the red alert with their password. The doctor sees the alert. |
| `TEST_now_low.csv` (65/40) | "Tension basse", symptom check, then the 60 s recheck. No alarm: the alarm is for severe and emergency alerts. |
| `TEST_now_normal.csv` (124/80) | Saved, no alert. |
| `TEST_now_invalid.csv` (1/1/1) | "Mesure non valide" and the symptom check; never used, no alert. |
| `simulated_now_severe.csv` (186/118) | Must be imported as **Données simulées**. It shows "Ce que les règles auraient fait: Très élevée", with no alert and no alarm. Use this one on stage. |

The `TEST_` files are fictional readings that the app accepts as measured, so the full real-reading path can be tried. Use them only on the local stack, ideally with a test account. Never use them on a shared database or in the presentation, where the simulated file shows the same rules honestly labelled.

## Larger examples (old dates: they go to the history)

Both are marked `# SIMULATED`: import them as **Données simulées**.

| File | What you should see |
|---|---|
| `historique_tension_14j.csv` | 28 readings (morning and evening, 17–30 Oct 2026), slowly rising from about 130/83 to about 148/92, with pulse, position, arm and a few notes. No alert. |
| `bracelet_3_nuits.csv` | 1,164 ring values: 3 nights, 23:00–07:00, every 5 minutes. On the last night SpO2 drops to about 91–92 % between 02:10 and 03:00 (heart rate up, HRV down). Never an alert. |
