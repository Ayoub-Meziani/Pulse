-- M4 ml_predictions (PULSE_INTEGRATION_CONTRACTS.md §3.1, §4).
-- Model estimates, kept apart from measurements and alerts. Doctor-only; written by the ML batch job.

create table public.ml_predictions (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid not null references public.profiles (id) on delete cascade,
  target_date date not null,                -- patient-local date being predicted
  target text not null check (target = 'morning_mean_bp'),
  status text not null check (status in ('ok', 'insufficient_history')),
  predicted_systolic numeric(5, 1),
  predicted_diastolic numeric(5, 1),
  interval_systolic_low numeric(5, 1),
  interval_systolic_high numeric(5, 1),
  interval_diastolic_low numeric(5, 1),
  interval_diastolic_high numeric(5, 1),
  model_version text not null,
  trained_on text not null,                 -- e.g. 'synthetic:pulse-sim-v1'
  features_until timestamptz not null,
  n_readings_used int not null check (n_readings_used >= 0),
  created_at timestamptz not null default now(),
  unique (patient_id, target_date, model_version),
  constraint ml_predictions_values_iff_ok check (
    (status = 'ok') = (predicted_systolic is not null and predicted_diastolic is not null)),
  constraint ml_predictions_interval_order check (
    (interval_systolic_low is null or interval_systolic_low <= interval_systolic_high)
    and (interval_diastolic_low is null or interval_diastolic_low <= interval_diastolic_high))
);
create index ml_predictions_patient_date on public.ml_predictions (patient_id, target_date desc);

revoke all on public.ml_predictions from anon, authenticated;
grant select on public.ml_predictions to authenticated;
alter table public.ml_predictions enable row level security;
-- Assigned doctors and admin only; patients do not see model estimates.
create policy ml_predictions_read on public.ml_predictions for select to authenticated
  using (private.is_assigned_doctor(patient_id) or private.current_app_role() = 'admin');
