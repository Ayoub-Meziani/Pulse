-- M5 patient_birth_year. Age is the strongest hypertension factor in the Algerian STEPS survey;
-- the year alone is enough for age bands (data minimisation: no full date of birth).
-- Filled by the patient; covered by the existing table-level insert/update grant and
-- the patient_profiles_*_own policies (no new grant needed).
alter table public.patient_profiles
  add column birth_year smallint check (birth_year between 1900 and 2100);
