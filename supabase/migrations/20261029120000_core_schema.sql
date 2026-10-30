-- PULSE core schema (Supabase / PostgreSQL 17).
-- Prototype only: fictional demo data. Validation thresholds are engineering defaults
-- pending clinician review. See docs/DATA_DICTIONARY.md for every table and field.

create schema if not exists private;  -- helpers; not exposed through the Supabase API

-- ---------------------------------------------------------------- helpers

create function private.is_valid_tz(tz text) returns boolean
language plpgsql immutable set search_path = '' as $$
begin
  perform timestamptz '2000-01-01 00:00+00' at time zone tz;
  return true;
exception when others then
  return false;
end $$;

create function private.touch_updated_at() returns trigger
language plpgsql set search_path = '' as $$
begin
  new.updated_at := now();
  return new;
end $$;

-- Trigger args are (column, required_role) pairs, e.g. ('doctor_id', 'doctor').
create function private.enforce_roles() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
  i int := 0;
  uid uuid;
  got text;
begin
  while i < tg_nargs loop
    uid := (to_jsonb(new) ->> tg_argv[i])::uuid;
    if uid is not null then
      select role into got from public.profiles where id = uid;
      if got is distinct from tg_argv[i + 1] then
        raise exception '%.% must reference a % profile', tg_table_name, tg_argv[i], tg_argv[i + 1]
          using errcode = '23514';
      end if;
    end if;
    i := i + 2;
  end loop;
  return new;
end $$;

-- ---------------------------------------------------------------- people

create table public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  role text not null default 'patient' check (role in ('patient', 'doctor', 'admin')),
  display_name text not null check (length(trim(display_name)) between 1 and 120),
  timezone text not null default 'Africa/Algiers' check (private.is_valid_tz(timezone)),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- Every new auth user gets a profile. Role is always 'patient': signup metadata is
-- user-controlled, so doctor/admin roles are granted only by the service role.
create function private.handle_new_user() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  insert into public.profiles (id, display_name)
  values (new.id, coalesce(nullif(trim(new.raw_user_meta_data ->> 'display_name'), ''),
                           split_part(coalesce(new.email, 'user'), '@', 1)));
  return new;
end $$;

create trigger on_auth_user_created after insert on auth.users
  for each row execute function private.handle_new_user();

create table public.patient_profiles (
  user_id uuid primary key references public.profiles (id) on delete cascade,
  relevant_conditions text[] not null default '{}',
  allergies text,
  medication_context text,  -- patient-supplied summary for the emergency card; structured list is `medications`
  regular_doctor_id uuid references public.profiles (id) on delete set null,
  regular_clinic text,
  emergency_preferences jsonb not null default '{}'::jsonb,
  consent_location boolean not null default false,
  data_consent_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.doctor_patient_assignments (
  id uuid primary key default gen_random_uuid(),
  doctor_id uuid not null references public.profiles (id) on delete cascade,
  patient_id uuid not null references public.profiles (id) on delete cascade,
  status text not null default 'active' check (status in ('active', 'ended')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  ended_at timestamptz,
  check (doctor_id <> patient_id),
  check ((status = 'ended') = (ended_at is not null))
);
create unique index assignments_one_active on public.doctor_patient_assignments (doctor_id, patient_id)
  where status = 'active';
create index assignments_patient on public.doctor_patient_assignments (patient_id) where status = 'active';

-- ---------------------------------------------------------------- measurement ingestion

create table public.devices (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid not null references public.profiles (id) on delete cascade,
  device_type text not null check (device_type in ('bp_cuff', 'wearable', 'phone_app', 'simulator')),
  -- What the device can do for blood pressure: a cuff measures, a ring/watch at most estimates.
  bp_capability text not null check (bp_capability in ('measured', 'estimated', 'none', 'simulated')),
  manufacturer text,
  model text,
  external_device_id text,  -- vendor serial / device id, if supplied
  label text,
  created_at timestamptz not null default now(),
  unique (id, patient_id),
  check ((device_type = 'simulator') = (bp_capability = 'simulated'))
);
create unique index devices_external_id on public.devices (patient_id, external_device_id)
  where external_device_id is not null;

create table public.ingestion_batches (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid not null references public.profiles (id) on delete cascade,
  source text not null check (source in ('csv_import', 'device_sync', 'simulated')),
  device_id uuid,
  file_name text,
  file_sha256 text check (file_sha256 ~ '^[0-9a-f]{64}$'),
  rows_total integer not null default 0 check (rows_total >= 0),
  rows_inserted integer not null default 0 check (rows_inserted >= 0),
  rows_duplicate integer not null default 0 check (rows_duplicate >= 0),
  rows_rejected integer not null default 0 check (rows_rejected >= 0),
  rejections jsonb not null default '[]'::jsonb,  -- [{row, reasons[]}] only; never health values
  created_by uuid references public.profiles (id) on delete set null,
  created_at timestamptz not null default now(),
  unique (id, patient_id),
  foreign key (device_id, patient_id) references public.devices (id, patient_id)
);
create unique index batches_file_once on public.ingestion_batches (patient_id, file_sha256)
  where file_sha256 is not null;

create table public.measurements (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid not null references public.profiles (id) on delete cascade,
  device_id uuid,
  ingestion_batch_id uuid,
  source text not null check (source in ('manual', 'device_sync', 'csv_import', 'simulated')),
  provenance text not null default 'measured' check (provenance in ('measured', 'estimated', 'simulated')),
  method text not null default 'unknown'
    check (method in ('cuff_oscillometric', 'cuff_auscultatory', 'wearable_estimate', 'unknown')),
  -- Storage sanity bounds only. The validation policy lives in private.validate_measurement().
  systolic smallint not null check (systolic between 1 and 400),
  diastolic smallint not null check (diastolic between 1 and 300),
  pulse smallint check (pulse between 1 and 400),
  unit text not null default 'mmHg' check (unit = 'mmHg'),
  measured_at timestamptz not null,
  measured_tz text check (measured_tz is null or private.is_valid_tz(measured_tz)),
  body_position text check (body_position in ('sitting', 'standing', 'lying')),
  arm text check (arm in ('left', 'right')),
  context text check (length(context) <= 500),
  external_id text,  -- reading id supplied by the device; never invented
  validation_status text not null default 'needs_review'
    check (validation_status in ('valid', 'needs_review', 'invalid')),
  quality_flags text[] not null default '{}' check (quality_flags <@ array[
    -- set by the validation trigger
    'systolic_not_above_diastolic', 'systolic_implausible', 'diastolic_implausible',
    'pulse_implausible', 'measured_in_future', 'unusual_value_recheck',
    'estimated_not_cuff', 'possible_duplicate',
    -- may be reported by a device (Bluetooth Blood Pressure Profile measurement status)
    'body_movement', 'cuff_fit_issue', 'irregular_pulse', 'improper_position'
  ]::text[]),
  validation_policy_version text not null default 'unvalidated',
  raw_payload jsonb check (pg_column_size(raw_payload) <= 16384),
  created_by uuid references public.profiles (id) on delete set null,
  created_at timestamptz not null default now(),
  unique (id, patient_id),
  foreign key (device_id, patient_id) references public.devices (id, patient_id),
  foreign key (ingestion_batch_id, patient_id) references public.ingestion_batches (id, patient_id),
  constraint measurements_simulated_labelled check (source <> 'simulated' or provenance = 'simulated'),
  constraint measurements_estimate_labelled check (method <> 'wearable_estimate' or provenance = 'estimated'),
  constraint measurements_valid_order check (validation_status <> 'valid' or systolic > diastolic),
  constraint measurements_external_needs_device check (external_id is null or device_id is not null)
);
create index measurements_patient_time on public.measurements (patient_id, measured_at desc);
create unique index measurements_device_reading on public.measurements (device_id, external_id)
  where external_id is not null;

-- Validation policy pulse-v1. Status is always computed here, so no client can mark its own
-- reading valid; flags sent by a device can only make the status worse.
-- invalid      = not a usable physiological value (excluded from analytics and ML)
-- needs_review = stored and shown for clinical review with its flags
create function private.validate_measurement() returns trigger
language plpgsql set search_path = '' as $$
declare
  hard text[] := '{}';
  soft text[] := coalesce(new.quality_flags, '{}');
begin
  if new.systolic <= new.diastolic then hard := array_append(hard, 'systolic_not_above_diastolic'); end if;
  if new.systolic not between 50 and 300 then hard := array_append(hard, 'systolic_implausible'); end if;
  if new.diastolic not between 25 and 200 then hard := array_append(hard, 'diastolic_implausible'); end if;
  if new.pulse not between 25 and 250 then hard := array_append(hard, 'pulse_implausible'); end if;
  if new.measured_at > now() + interval '5 minutes' then hard := array_append(hard, 'measured_in_future'); end if;

  if new.systolic not between 70 and 250 or new.diastolic not between 40 and 150 then
    soft := array_append(soft, 'unusual_value_recheck');
  end if;
  if new.provenance = 'estimated' then soft := array_append(soft, 'estimated_not_cuff'); end if;
  -- ponytail: misses two identical inserts racing in parallel; fine for manual entry
  if exists (
    select 1 from public.measurements m
    where m.patient_id = new.patient_id and m.id <> new.id
      and m.systolic = new.systolic and m.diastolic = new.diastolic
      and m.pulse is not distinct from new.pulse
      and m.measured_at between new.measured_at - interval '2 minutes' and new.measured_at + interval '2 minutes'
  ) then
    soft := array_append(soft, 'possible_duplicate');
  end if;

  new.quality_flags := array(select distinct f from unnest(hard || soft) f order by f);
  new.validation_status := case
    when cardinality(hard) > 0 then 'invalid'
    when cardinality(new.quality_flags) > 0 then 'needs_review'
    else 'valid' end;
  new.validation_policy_version := 'pulse-v1';
  new.created_by := coalesce(auth.uid(), new.created_by);
  return new;
end $$;

create trigger measurements_validate
  before insert or update of systolic, diastolic, pulse, measured_at, provenance, quality_flags
  on public.measurements for each row execute function private.validate_measurement();

-- ---------------------------------------------------------------- patient-reported context

create table public.symptom_reports (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid not null references public.profiles (id) on delete cascade,
  symptoms text[] not null check (cardinality(symptoms) > 0 and symptoms <@ array[
    'chest_pain', 'shortness_of_breath', 'back_pain', 'weakness', 'numbness', 'vision_change',
    'difficulty_speaking', 'severe_headache', 'confusion', 'dizziness', 'nausea', 'palpitations', 'other'
  ]::text[]),
  onset_at timestamptz,
  reported_at timestamptz not null default now(),
  source text not null default 'patient_reported'
    check (source in ('patient_reported', 'bystander', 'clinician', 'simulated')),
  notes text check (length(notes) <= 2000),
  created_at timestamptz not null default now(),
  unique (id, patient_id),
  check (onset_at is null or onset_at <= reported_at + interval '5 minutes')
);
create index symptoms_patient_time on public.symptom_reports (patient_id, reported_at desc);

create table public.lifestyle_logs (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid not null references public.profiles (id) on delete cascade,
  category text not null check (category in ('meal', 'activity', 'sleep', 'stress', 'other')),
  started_at timestamptz not null,
  ended_at timestamptz,
  source text not null default 'patient_reported' check (source in ('patient_reported', 'device', 'simulated')),
  description text check (length(description) <= 1000),
  meal_type text check (meal_type in ('breakfast', 'lunch', 'dinner', 'snack')),
  sodium_mg numeric(7, 1) check (sodium_mg >= 0),
  sodium_basis text check (sodium_basis in ('label', 'estimated')),  -- never implied from a meal name
  activity_type text check (length(activity_type) <= 100),
  intensity text check (intensity in ('light', 'moderate', 'vigorous')),
  steps integer check (steps >= 0),
  sleep_quality smallint check (sleep_quality between 1 and 5),  -- patient-rated, 5 = best
  stress_level smallint check (stress_level between 1 and 5),    -- patient-rated, 5 = highest
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint lifestyle_time_order check (ended_at is null or ended_at between started_at and started_at + interval '24 hours'),
  constraint lifestyle_sodium_basis check ((sodium_mg is null) = (sodium_basis is null)),
  constraint lifestyle_meal_fields check (category = 'meal' or (meal_type is null and sodium_mg is null)),
  constraint lifestyle_activity_fields check (category = 'activity' or (activity_type is null and intensity is null and steps is null)),
  constraint lifestyle_sleep_fields check (category = 'sleep' or sleep_quality is null),
  constraint lifestyle_sleep_end check (category <> 'sleep' or ended_at is not null),
  constraint lifestyle_stress_fields check (category = 'stress' or stress_level is null)
);
create index lifestyle_patient_time on public.lifestyle_logs (patient_id, started_at desc);

create table public.medications (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid not null references public.profiles (id) on delete cascade,
  name text not null check (length(name) <= 200),
  dose_text text,      -- as written by the clinician/patient; PULSE never computes or changes doses
  schedule_text text,
  source text not null check (source in ('clinician', 'patient_reported')),
  prescribed_by uuid references public.profiles (id) on delete restrict,
  active boolean not null default true,
  started_on date,
  ended_on date,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (id, patient_id),
  check (ended_on is null or started_on is null or ended_on >= started_on),
  check ((source = 'clinician') = (prescribed_by is not null))
);

-- Adherence is only what was reported; a prescription never implies a dose was taken.
create table public.medication_adherence_events (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid not null,
  medication_id uuid not null,
  status text not null check (status in ('taken', 'missed', 'skipped')),
  scheduled_for timestamptz,
  taken_at timestamptz,
  source text not null default 'patient_reported' check (source in ('patient_reported', 'device', 'simulated')),
  note text check (length(note) <= 500),
  reported_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  foreign key (medication_id, patient_id) references public.medications (id, patient_id) on delete cascade,
  check (status = 'taken' or taken_at is null)
);
create index adherence_patient_time on public.medication_adherence_events (patient_id, reported_at desc);

create table public.journal_entries (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid not null references public.profiles (id) on delete cascade,
  category text not null check (category in ('symptoms', 'food', 'activity', 'medication', 'question', 'other')),
  entry_text text not null check (length(entry_text) between 1 and 4000),
  created_at timestamptz not null default now(),
  doctor_review_status text not null default 'not_reviewed' check (doctor_review_status in ('not_reviewed', 'reviewed')),
  reviewed_by uuid references public.profiles (id) on delete set null,
  reviewed_at timestamptz,
  check ((doctor_review_status = 'reviewed') = (reviewed_at is not null))
);
create index journal_patient_time on public.journal_entries (patient_id, created_at desc);

-- ---------------------------------------------------------------- clinician-authored

create table public.care_plans (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid not null references public.profiles (id) on delete cascade,
  clinician_id uuid not null references public.profiles (id) on delete restrict,
  status text not null default 'active' check (status in ('draft', 'active', 'superseded', 'completed')),
  effective_from date not null,
  effective_to date,
  review_date date,
  target_systolic smallint check (target_systolic between 90 and 200),   -- clinician-defined, mmHg
  target_diastolic smallint check (target_diastolic between 50 and 130), -- clinician-defined, mmHg
  monitoring_readings_per_day smallint check (monitoring_readings_per_day between 1 and 12),
  monitoring_instructions text,
  lifestyle_recommendations text,
  follow_up_instructions text,
  clinician_guidance text not null,
  supersedes_id uuid references public.care_plans (id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (effective_to is null or effective_to >= effective_from),
  check (review_date is null or review_date >= effective_from),
  check (target_systolic is null or target_diastolic is null or target_systolic > target_diastolic)
);
-- One active plan per patient; a revision is a new row and the old one becomes 'superseded'.
create unique index care_plans_one_active on public.care_plans (patient_id) where status = 'active';

create table public.doctor_notes (
  id uuid primary key default gen_random_uuid(),
  doctor_id uuid not null references public.profiles (id) on delete restrict,
  patient_id uuid not null references public.profiles (id) on delete cascade,
  note text not null check (length(note) between 1 and 8000),
  advice text,
  follow_up_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index doctor_notes_patient_time on public.doctor_notes (patient_id, created_at desc);

-- ---------------------------------------------------------------- alerts and emergencies

create table public.alerts (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid not null references public.profiles (id) on delete cascade,
  measurement_id uuid,
  symptom_report_id uuid,
  alert_class text not null check (alert_class in (
    'routine', 'above_target', 'severely_high', 'possible_emergency',
    'follow_up', 'lifestyle_review', 'data_quality_review')),
  trigger_source text not null default 'rule_engine' check (trigger_source in ('rule_engine', 'clinician', 'patient')),
  rule_code text not null,
  rule_version text,
  reason text not null,
  actions text[] not null default '{}',
  status text not null default 'open' check (status in ('open', 'acknowledged', 'reviewed', 'resolved')),
  created_at timestamptz not null default now(),
  acknowledged_at timestamptz,
  acknowledged_by uuid references public.profiles (id) on delete set null,
  reviewed_at timestamptz,
  reviewed_by uuid references public.profiles (id) on delete set null,
  resolved_at timestamptz,
  resolved_by uuid references public.profiles (id) on delete set null,
  resolution_note text,
  foreign key (measurement_id, patient_id) references public.measurements (id, patient_id),
  foreign key (symptom_report_id, patient_id) references public.symptom_reports (id, patient_id),
  check (status <> 'acknowledged' or acknowledged_at is not null),
  check (status <> 'reviewed' or reviewed_at is not null),
  check (status <> 'resolved' or resolved_at is not null)
);
create index alerts_patient_status_time on public.alerts (patient_id, status, created_at desc);
-- The same rule never fires twice for the same event.
create unique index alerts_once_per_measurement on public.alerts (measurement_id, rule_code)
  where measurement_id is not null;
create unique index alerts_once_per_symptom_report on public.alerts (symptom_report_id, rule_code)
  where symptom_report_id is not null;

create table public.trusted_contacts (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid not null references public.profiles (id) on delete cascade,
  name text not null,
  relationship text,
  phone text not null check (phone ~ '^\+?[0-9 ()-]{6,20}$'),
  consented_at timestamptz not null default now(),
  active boolean not null default true
);

create table public.emergency_events (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid not null references public.profiles (id) on delete cascade,
  alert_id uuid references public.alerts (id) on delete set null,
  trigger_reason text not null,
  symptoms_snapshot text[] not null default '{}',
  location_lat double precision check (location_lat between -90 and 90),
  location_lon double precision check (location_lon between -180 and 180),
  location_shared_with_consent boolean not null default false,
  actions_attempted jsonb not null default '[]'::jsonb,  -- [{action, at, confirmed}]; confirmed only if verified
  reported_outcome text,
  started_at timestamptz not null default now(),
  ended_at timestamptz,
  check ((location_lat is null) = (location_lon is null)),
  check (location_lat is null or location_shared_with_consent),
  check (ended_at is null or ended_at >= started_at)
);
create index emergency_patient_time on public.emergency_events (patient_id, started_at desc);

-- ---------------------------------------------------------------- audit trail

create table public.audit_log (
  id bigint generated always as identity primary key,
  table_name text not null,
  row_id uuid,
  action text not null,
  actor uuid,  -- auth.uid() of the caller; null for service-role / migrations
  changed_at timestamptz not null default now(),
  old_data jsonb,
  new_data jsonb
);
create index audit_row on public.audit_log (table_name, row_id);

create function private.audit() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  insert into public.audit_log (table_name, row_id, action, actor, old_data, new_data)
  values (tg_table_name,
          case when tg_op = 'DELETE' then old.id else new.id end,
          tg_op, auth.uid(),
          case when tg_op <> 'INSERT' then to_jsonb(old) end,
          case when tg_op <> 'DELETE' then to_jsonb(new) end);
  return case when tg_op = 'DELETE' then old else new end;
end $$;

-- ---------------------------------------------------------------- triggers

create trigger patient_profiles_roles before insert or update on public.patient_profiles
  for each row execute function private.enforce_roles('user_id', 'patient', 'regular_doctor_id', 'doctor');
create trigger assignments_roles before insert or update on public.doctor_patient_assignments
  for each row execute function private.enforce_roles('doctor_id', 'doctor', 'patient_id', 'patient');
create trigger care_plans_roles before insert or update on public.care_plans
  for each row execute function private.enforce_roles('clinician_id', 'doctor', 'patient_id', 'patient');
create trigger doctor_notes_roles before insert or update on public.doctor_notes
  for each row execute function private.enforce_roles('doctor_id', 'doctor', 'patient_id', 'patient');
create trigger medications_roles before insert or update on public.medications
  for each row execute function private.enforce_roles('prescribed_by', 'doctor', 'patient_id', 'patient');

do $$
declare t text;
begin
  foreach t in array array['profiles', 'patient_profiles', 'doctor_patient_assignments', 'lifestyle_logs',
                           'medications', 'care_plans', 'doctor_notes'] loop
    execute format('create trigger %I before update on public.%I for each row execute function private.touch_updated_at()',
                   t || '_touch', t);
  end loop;
  foreach t in array array['profiles', 'doctor_patient_assignments', 'care_plans', 'doctor_notes',
                           'medications', 'alerts'] loop
    execute format('create trigger %I after insert or update or delete on public.%I for each row execute function private.audit()',
                   t || '_audit', t);
  end loop;
end $$;
