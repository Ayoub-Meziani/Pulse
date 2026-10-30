# PULSE data dictionary

Source of truth: `supabase/migrations/`. PostgreSQL 17 on Supabase. All timestamps are `timestamptz` (stored UTC, converted with the patient's `profiles.timezone` / `measurements.measured_tz`). Blood pressure is **mmHg**, pulse **bpm**, sodium **mg**.

Prototype only: fictional data. Alert thresholds, SpO2 limits, the band rule and wording were reviewed by the team's medical mentor on 30 Oct 2026; the validation limits (`pulse-v1`) are engineering defaults.

## Provenance: keep these separate
| Kind | Where | Rule |
|---|---|---|
| Raw/validated measurement | `measurements` | `source` = how it arrived, `provenance` = what it is, `validation_status` = data quality |
| Patient-reported | `symptom_reports`, `lifestyle_logs`, `journal_entries`, adherence | `source` column says who reported |
| Clinician-authored | `care_plans`, `doctor_notes`, clinician `medications` | authored by a `doctor` profile (trigger-enforced) |
| Rule alerts | `alerts` | deterministic rules only; never ML |
| ML predictions | *(ML phase: separate `ml_predictions` table)* | never stored as a measurement |
| Synthetic | any table | `source/provenance = 'simulated'`; seed + generator only |

## Tables

### profiles
One row per `auth.users` account, created by trigger.
| field | type | meaning |
|---|---|---|
| id | uuid PK → auth.users | |
| role | text | `patient` (default, always on signup) \| `doctor` \| `admin`; only the service role changes it |
| display_name | text | 1–120 chars |
| preferred_language | text, nullable | fr \| ar (M6); the user may update it |
| timezone | text | IANA zone, validated; default `Africa/Algiers`; used for local-day analytics |
| created_at / updated_at | timestamptz | |

### patient_profiles
Patient-only (trigger-enforced). `relevant_conditions text[]`, `allergies`, `medication_context` (free text for the emergency card), `regular_doctor_id` → doctor profile, `regular_clinic`, `emergency_preferences jsonb`, `consent_location bool`, `data_consent_at`, `birth_year` (M5, year only, 1900–2100, patient-entered). No full date of birth (data minimisation).
M6 adds:
- `sex` (female / male) and `smoking_status` (never / former / current).
- `condition_codes` (controlled list: hypertension, diabetes, dyslipidemia, chronic_kidney_disease, heart_disease, stroke_history, pregnancy; M8 adds copd, asthma, obstructive_sleep_apnea, atrial_fibrillation, heart_failure, thyroid_disease). COPD and atrial fibrillation change how ring values are judged (ml/README.md).
- Salt habits: `bread_portions_per_day` 0–20, plus `adds_salt_at_table` and `salty_processed_food` (never / rarely / sometimes / often / always).

### body_measurements (M6)
`measured_at`, `weight_kg` 20–300, `height_cm` 100–230, `waist_cm` 40–200 (at least one value), `source` patient_reported | clinician | device | simulated, `created_by`.
- **BMI:** computed when read, from the latest weight and height.
- **Abdominal obesity:** waist > 94 cm (men) / > 80 cm (women), the STEPS cut-offs.
- **Who writes:** the patient (`patient_reported`) or an assigned doctor (`clinician`). No update or delete.

### wearable_samples (M6)
Ring / bracelet / watch data, never a blood-pressure measurement.
- **Columns:** `device_id` (same patient), `metric` + `unit` as fixed pairs (heart_rate / bpm, hrv_rmssd / ms, spo2 / percent, skin_temperature / celsius), `value` (plausible range per metric), `measured_at`, `source` device_sync | csv_import | simulated, `external_id` (unique per device).
- **Access:** read like other patient data; written by the backend only.

### doctor_patient_assignments
Who may see whom. `doctor_id` (must be a doctor), `patient_id` (must be a patient), `status` active|ended, `ended_at` (required iff ended). One active row per pair. **This table drives all doctor access.**

### devices
`device_type` bp_cuff|wearable|phone_app|simulator; `bp_capability` measured|estimated|none|simulated (a ring/watch is at most `estimated`; simulator ⇔ simulated); `manufacturer`, `model`, `external_device_id` (unique per patient), `label`.

### ingestion_batches
One per import/sync. `source` csv_import|device_sync|simulated, `device_id`, `file_name`, `file_sha256` (unique per patient → the same file is never imported twice), `rows_total/inserted/duplicate/rejected`, `rejections jsonb` = `[{row, reasons[]}]` (**no health values**).

### measurements
| field | type | meaning |
|---|---|---|
| patient_id | uuid → profiles | |
| device_id | uuid, nullable | must belong to the same patient (composite FK) |
| ingestion_batch_id | uuid, nullable | same-patient batch |
| source | text | manual \| device_sync \| csv_import \| simulated |
| provenance | text | measured \| estimated \| simulated. `simulated` source ⇒ simulated provenance; `wearable_estimate` method ⇒ estimated |
| method | text | cuff_oscillometric \| cuff_auscultatory \| wearable_estimate \| unknown |
| systolic, diastolic | smallint, mmHg | storage bounds only (1–400 / 1–300) |
| pulse | smallint bpm, nullable | not every device reports it |
| unit | text | must be `mmHg` (explicit; no silent conversion) |
| measured_at | timestamptz | when the reading was taken |
| measured_tz | text, nullable | IANA zone where it was taken (falls back to profile tz) |
| body_position, arm, context | text | sitting/standing/lying, left/right, free note ≤500 |
| rested_5_min | boolean, nullable | patient confirmed 5 minutes' rest before measuring (M3; null = not asked) |
| external_id | text, nullable | reading id from the device; unique per device; **never invented** |
| validation_status | text | valid \| needs_review \| invalid (computed, see below) |
| quality_flags | text[] | controlled vocabulary, see below |
| validation_policy_version | text | `pulse-v1` |
| raw_payload | jsonb ≤16 KB | original device payload when useful |
| created_by, created_at | | `created_by` = auth.uid() of the inserter |

Append-only for app users (no update/delete). A wrong entry stays, flagged; analytics ignore `invalid`.

### Validation policy `pulse-v1` (trigger `private.validate_measurement`)
Runs on every insert, from every path. Client-supplied status is ignored; device flags can only make the status worse.

| layer | where | examples |
|---|---|---|
| 1. schema/format | adapter (`pulse_data/ingest.py`) | missing column, non-integer, unit ≠ mmHg, bad timestamp → row rejected and recorded in batch |
| 2. device-specific | adapter → `quality_flags` | `body_movement`, `cuff_fit_issue`, `irregular_pulse`, `improper_position` |
| 3. physiological plausibility | DB trigger | below |
| 4. clinical alert thresholds | backend (`api/app/analysis/rules.py`) | ≥180/120 is *not* a quality problem |
| 5. ML eligibility | **ML phase** | coverage, window length |

| flag | status | rule |
|---|---|---|
| systolic_not_above_diastolic | invalid | systolic ≤ diastolic |
| systolic_implausible | invalid | systolic outside 50–300 |
| diastolic_implausible | invalid | diastolic outside 25–200 |
| pulse_implausible | invalid | pulse outside 25–250 |
| measured_in_future | invalid | measured_at > now + 5 min |
| unusual_value_recheck | needs_review | systolic outside 70–250 or diastolic outside 40–150 |
| estimated_not_cuff | needs_review | provenance = estimated |
| possible_duplicate | needs_review | same patient, same values, within ±2 min (manual double entry) |
| device flags | needs_review | reported by the device |

`invalid` = not a usable physiological value. `needs_review` = kept, shown with its flags, **still reaches clinical review and alert rules**. Thresholds are engineering defaults awaiting clinician review.

### symptom_reports
`symptoms text[]` (empty = "none of these", M3) from: chest_pain, shortness_of_breath, back_pain, weakness, numbness, vision_change, difficulty_speaking, severe_headache, confusion, dizziness, nausea, palpitations, other. `onset_at`, `reported_at`, `source` patient_reported|bystander|clinician|simulated, `notes`. No severity scale (none clinically defined yet). Evaluated independently of BP.

### lifestyle_logs
One table, typed columns that only apply to their category (CHECK-enforced, no JSON blob).
| category | columns |
|---|---|
| fasting (M6) | started_at = start of the fast, ended_at = iftar; description optional |
| all | started_at, ended_at (≥ start, ≤ 24 h), source patient_reported\|device\|simulated, description |
| meal | meal_type breakfast/lunch/dinner/snack; sodium_mg + **required** sodium_basis label\|estimated |
| activity | activity_type, intensity light/moderate/vigorous, steps |
| sleep | ended_at required; sleep_quality 1–5 (patient-rated) |
| stress | stress_level 1–5 |
Missing logs mean "not recorded", never "did not happen".

### medications / medication_adherence_events
`medications`: name, dose_text, schedule_text (as written; PULSE never computes or changes doses), `source` clinician (requires `prescribed_by` doctor) | patient_reported, active, started_on/ended_on.
`medication_adherence_events`: status taken|missed|skipped, scheduled_for, taken_at (only when taken), source, reported_at. A prescription never implies a dose was taken.

### journal_entries
Patient notes for the doctor: category, entry_text, `doctor_review_status` not_reviewed|reviewed (+ reviewed_by/at).

### care_plans
Clinician-authored. `status` draft|active|superseded|completed (one active per patient), effective_from/to, review_date, `target_systolic/diastolic` (clinician targets, distinct from emergency thresholds), `monitoring_readings_per_day`, monitoring/lifestyle/follow-up text, `clinician_guidance`, `supersedes_id`. A revision = new row; the old row becomes superseded. Never modified by AI.

### doctor_notes
doctor_id, patient_id, note, advice, follow_up_at. Readable by assigned doctors and admin only (M3); patients get `advice`/`follow_up_at` through the API.

### alerts
`alert_class` routine|above_target|above_target_trend|severely_high|possible_emergency|follow_up|lifestyle_review|data_quality_review, `persistent` (episode stays open across readings; readings attached in `alert_measurements`), `trigger_source` rule_engine|clinician|patient, `rule_code`, `rule_version`, `reason`, `actions[]`, `status` open→acknowledged→reviewed→resolved with *_at/*_by, `resolution_note` (doctor's note when resolving; required by the API for severe/emergency), `measurement_id` / `symptom_report_id` (same-patient FKs). The same rule fires at most once per measurement and once per symptom report. Opening an alert never closes it.

### alert_measurements (M3)
`alert_id`, `measurement_id`, `patient_id`, `attached_at`. Readings that belong to one alert episode; same-patient composite FKs. Read like alerts; written by the backend only.

### ml_predictions (M4)
Model estimates, never measurements. `target_date` (patient-local), `target` = morning_mean_bp, `status` ok|insufficient_history (values present iff ok), predicted systolic/diastolic + interval, `model_version`, `trained_on` (e.g. `synthetic:pulse-sim-v1`), `features_until`, `n_readings_used`. Unique per (patient, date, model). **Assigned doctors and admin only**; written by the ML batch job.

### wearable_flags, patient_bands, weekly_reports (M7, advisory, doctor / admin only)
- **wearable_flags:** the ring monitor's flags, reviewed by the doctor (confirmed / dismissed). Never alerts, never a safety trigger.
- **patient_bands:** personal ring ranges. The model proposes; only the doctor activates, via `private.approve_band`.
- **weekly_reports:** the weekly summary for the doctor: home-BP category, control vs the care-plan target, model outputs, and the ring summary.

Field lists and access: [MIGRATIONS.md](MIGRATIONS.md) (M7).

### trusted_contacts / emergency_events
Contacts: name, relationship, phone, consented_at, active. Emergency events: trigger_reason, symptoms_snapshot, location only if `location_shared_with_consent`, `actions_attempted` `[{action, at, confirmed}]` (`confirmed` only when actually verified), reported_outcome, started/ended.

### audit_log
Insert/update/delete history for profiles, assignments, care_plans, doctor_notes, medications, alerts: table_name, row_id, action, actor (auth.uid()), old_data, new_data. Admin-read only.

## Missing-data policy
- Missing readings are not normal readings; coverage is reported by analytics, never filled in.
- No forward-filling, no imputed values written to tables.
- Optional fields are `null` when the source did not supply them (e.g. pulse, position).
- Synthetic rows are always labelled `simulated` and are excluded from any real-world evaluation.
