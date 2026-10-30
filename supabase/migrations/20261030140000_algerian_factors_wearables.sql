-- M6 algerian_factors_wearables: every factor of PULSE_DATA_LOGIC.pdf §6 and the wearable data of §5.
-- Sources for why each field exists: Algerian STEPS 2016-2017 (Moussouni et al., BMC Public Health 2022).
-- New tables revoke anon/authenticated first (the live default privileges would grant ALL).

-- ---------------------------------------------------------------- patient factors (patient fills)
alter table public.patient_profiles
  add column sex text check (sex in ('female', 'male')),
  add column smoking_status text check (smoking_status in ('never', 'former', 'current')),
  -- coded conditions for analytics; relevant_conditions stays free text for the emergency card
  add column condition_codes text[] not null default '{}' check (condition_codes <@ array[
    'hypertension', 'diabetes', 'dyslipidemia', 'chronic_kidney_disease', 'heart_disease',
    'stroke_history', 'pregnancy']::text[]),
  -- salt habits in the style of the STEPS questionnaire (patients rarely know milligrams)
  add column bread_portions_per_day smallint check (bread_portions_per_day between 0 and 20),
  add column adds_salt_at_table text check (adds_salt_at_table in ('never', 'rarely', 'sometimes', 'often', 'always')),
  add column salty_processed_food text check (salty_processed_food in ('never', 'rarely', 'sometimes', 'often', 'always'));
-- Covered by the existing table-level insert/update grant and the *_own policies.

alter table public.profiles add column preferred_language text check (preferred_language in ('fr', 'ar'));
grant update (preferred_language) on public.profiles to authenticated;

-- Ramadan / other fasting days: started_at = start of the fast, ended_at = iftar.
alter table public.lifestyle_logs drop constraint lifestyle_logs_category_check;
alter table public.lifestyle_logs add constraint lifestyle_logs_category_check
  check (category in ('meal', 'activity', 'sleep', 'stress', 'fasting', 'other'));

-- ---------------------------------------------------------------- weight, height, waist (BMI, abdominal obesity)
create table public.body_measurements (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid not null references public.profiles (id) on delete cascade,
  measured_at timestamptz not null,
  weight_kg numeric(5, 1) check (weight_kg between 20 and 300),
  height_cm numeric(4, 1) check (height_cm between 100 and 230),
  waist_cm numeric(4, 1) check (waist_cm between 40 and 200),
  source text not null check (source in ('patient_reported', 'clinician', 'device', 'simulated')),
  created_by uuid default auth.uid() references public.profiles (id) on delete set null,
  created_at timestamptz not null default now(),
  check (coalesce(weight_kg, height_cm, waist_cm) is not null)
);
create index body_measurements_patient_time on public.body_measurements (patient_id, measured_at desc);
revoke all on public.body_measurements from anon, authenticated;
grant select, insert on public.body_measurements to authenticated;
alter table public.body_measurements enable row level security;
create policy body_measurements_read on public.body_measurements for select to authenticated
  using (private.can_read_patient(patient_id));
create policy body_measurements_insert on public.body_measurements for insert to authenticated
  with check ((patient_id = (select auth.uid()) and source = 'patient_reported')
              or (private.is_assigned_doctor(patient_id) and source = 'clinician'));

-- ---------------------------------------------------------------- ring / bracelet / watch samples
-- Heart rate, HRV, SpO2, skin temperature. Device data, never a blood-pressure measurement.
create table public.wearable_samples (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid not null references public.profiles (id) on delete cascade,
  device_id uuid not null,
  metric text not null,
  value numeric(6, 2) not null,
  unit text not null,
  measured_at timestamptz not null,
  source text not null check (source in ('device_sync', 'csv_import', 'simulated')),
  external_id text,  -- sample id from the device or vendor export; never invented
  created_at timestamptz not null default now(),
  foreign key (device_id, patient_id) references public.devices (id, patient_id),
  constraint wearable_metric_unit check ((metric, unit) in (
    ('heart_rate', 'bpm'), ('hrv_rmssd', 'ms'), ('spo2', 'percent'), ('skin_temperature', 'celsius'))),
  constraint wearable_value_range check (case metric
    when 'heart_rate' then value between 25 and 250
    when 'hrv_rmssd' then value between 1 and 300
    when 'spo2' then value between 50 and 100
    when 'skin_temperature' then value between 20 and 45 end)
);
create index wearable_samples_patient_metric_time on public.wearable_samples (patient_id, metric, measured_at desc);
create unique index wearable_samples_device_sample on public.wearable_samples (device_id, external_id)
  where external_id is not null;
revoke all on public.wearable_samples from anon, authenticated;
grant select on public.wearable_samples to authenticated;
alter table public.wearable_samples enable row level security;
create policy wearable_samples_read on public.wearable_samples for select to authenticated
  using (private.can_read_patient(patient_id));
-- Written by FastAPI / the import tool (privileged connection) only.
