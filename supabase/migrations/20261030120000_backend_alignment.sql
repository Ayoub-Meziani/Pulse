-- M3 backend_alignment (PULSE_INTEGRATION_CONTRACTS.md §3.1).
-- The live project's default privileges grant ALL on new public objects to anon/authenticated,
-- so every new object below revokes first and grants only what it needs.

-- 1. Persistent above-target trend alerts.
alter table public.alerts drop constraint alerts_alert_class_check;
alter table public.alerts add constraint alerts_alert_class_check check (alert_class in (
  'routine', 'above_target', 'above_target_trend', 'severely_high', 'possible_emergency',
  'follow_up', 'lifestyle_review', 'data_quality_review'));

-- 2. Alert episodes that stay open across several readings.
alter table public.alerts add column persistent boolean not null default false;

-- 4. Readings attached to an alert episode (same patient enforced by composite keys).
alter table public.alerts add constraint alerts_id_patient_id_key unique (id, patient_id);
create table public.alert_measurements (
  alert_id uuid not null,
  measurement_id uuid not null,
  patient_id uuid not null,
  attached_at timestamptz not null default now(),
  primary key (alert_id, measurement_id),
  foreign key (alert_id, patient_id) references public.alerts (id, patient_id) on delete cascade,
  foreign key (measurement_id, patient_id) references public.measurements (id, patient_id)
);
create index alert_measurements_patient on public.alert_measurements (patient_id);
revoke all on public.alert_measurements from anon, authenticated;
grant select on public.alert_measurements to authenticated;
alter table public.alert_measurements enable row level security;
create policy alert_measurements_read on public.alert_measurements for select to authenticated
  using (private.can_read_patient(patient_id));
-- Written by the backend (privileged connection) only.

-- 5. Patient confirms they rested 5 minutes before measuring (null = not asked).
alter table public.measurements add column rested_5_min boolean;

-- 6. An empty symptom list records a "none of these" answer.
alter table public.symptom_reports drop constraint symptom_reports_symptoms_check;
alter table public.symptom_reports add constraint symptom_reports_symptoms_check check (symptoms <@ array[
  'chest_pain', 'shortness_of_breath', 'back_pain', 'weakness', 'numbness', 'vision_change',
  'difficulty_speaking', 'severe_headache', 'confusion', 'dizziness', 'nausea', 'palpitations', 'other'
]::text[]);

-- 7. Doctor notes are private to the clinical side. Patients no longer read the row directly;
-- the API returns them only `advice` and `follow_up_at` (contract §2.4 NoteOut).
drop policy doctor_notes_read on public.doctor_notes;
create policy doctor_notes_read on public.doctor_notes for select to authenticated
  using (private.is_assigned_doctor(patient_id) or private.current_app_role() = 'admin');
