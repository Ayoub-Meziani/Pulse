-- M8 chronic_conditions: chronic illnesses that change blood pressure and what "normal" ring values are.
--   copd                     lower SpO2 targets (BTS 2017: 88-92 % if at risk of hypercapnic failure)
--   asthma                   respiratory; SpO2 context
--   obstructive_sleep_apnea  night SpO2 dips; very common with (resistant) hypertension
--   atrial_fibrillation      irregular pulse: ring HRV is not interpretable
--   heart_failure, thyroid_disease  cardiac / metabolic context for heart rate
-- Additive: widens the controlled list only (patient_profiles.condition_codes, patient-entered, doctor confirms).
alter table public.patient_profiles drop constraint patient_profiles_condition_codes_check;
alter table public.patient_profiles add constraint patient_profiles_condition_codes_check
  check (condition_codes <@ array[
    'hypertension', 'diabetes', 'dyslipidemia', 'chronic_kidney_disease', 'heart_disease', 'stroke_history',
    'pregnancy', 'copd', 'asthma', 'obstructive_sleep_apnea', 'atrial_fibrillation', 'heart_failure',
    'thyroid_disease']::text[]);
