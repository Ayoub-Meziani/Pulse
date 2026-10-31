# Safety and limitations

PULSE is a hackathon prototype. **It is not a medical device and has not been clinically validated.**

## Alert rules (prototype policy, needs clinician review)

Source: American Heart Association patient guidance on hypertensive crisis (180/120 or higher,
re-measure after 1–2 minutes, call emergency services with symptoms).

| Rule | Condition | Result |
|---|---|---|
| R-EMG-1 | any red-flag symptom (chest pain, shortness of breath, back pain, numbness, weakness, change in vision, difficulty speaking) | emergency, whatever the reading |
| R-SEV-1 | systolic ≥ 180 or diastolic ≥ 120 | severe: symptom check, recheck in 60 s |
| R-SEV-2 | recheck within 15 min still ≥ 180 / ≥ 120 | severe, marked persistent |
| R-SEV-3 | recheck within 15 min below 180 / 120 | severe alert stays open for the doctor |
| R-TGT-1 | reading ≥ target (default 140/90 until a doctor sets a care plan) | notice |
| R-TRD-1 | ≥ 3 valid readings in 7 days with mean ≥ target | trend |

Validation: impossible values are rejected (systolic 50–300, diastolic 30–200, pulse 25–250,
systolic > diastolic, not > 5 min in the future). Unusual pulse pressure (< 20 or > 120) is stored
as `questionable`, still evaluated by the safety rules, and excluded from averages and trends.

Values needing clinician sign-off: thresholds, 60 s recheck, default target (140/90 vs 135/85 for
home readings), trend window, symptom list, all text in `api/app/analysis/texts.py`.

## File imports and wearables (proposed decision D26)

| Data | What happens |
|---|---|
| Imported readings measured within the last hour | the same rules as a manual reading (symptom check, recheck, alerts) |
| Older imported readings | history only, no alert; if one was 180/120 or higher, the patient is asked to measure now |
| Simulated readings (demo files) | stored and labelled; never create or change an alert (the rules' result is shown as a preview) |
| Ring / bracelet samples | context for the doctor; never read by any rule or alert. R-RING-1 is not implemented and stays disabled (B26): nothing happens when a ring value crosses a limit |
| Ring ML outputs (flags, live early warnings, weekly reports, personal ranges) | doctor only, experimental, not clinically reviewed, behind a server switch that is off by default; no notification: visible only while the doctor's screen is open |

Needing clinician sign-off as well: the 1-hour window for imported readings and the `IMPORT-*` texts.

## What PULSE does not do

- No diagnosis, no medication advice, no treatment decisions.
- No ambulance dispatch, SMS gateway, or real-time doctor notification.
- No detection of fainting or unconsciousness; a blood-pressure cuff cannot do this.
- A web app cannot run in the background or show information on a locked phone.
- No hardware integration exists yet; demo readings are `simulated` and labelled as such.
- ML output is advisory, for the doctor only; it never drives safety alerts or patient guidance.

## Data

All demo accounts and readings are fictional (`python -m app.seed`). Do not load real patient data.
