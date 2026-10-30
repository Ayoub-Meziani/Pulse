-- M7 ml_monitoring: ring monitoring, doctor-approved personal bands, weekly doctor reports.
-- Built as required by the backend review (PULSE_ML_phase2_review.pdf). Everything here is ADVISORY:
-- no safety rule reads these tables (review H6). Doctor / admin read only (review M4).
-- New tables revoke anon/authenticated first (the live default privileges would grant ALL).

-- Polling index for the ring monitor (review M6).
create index wearable_samples_created_at on public.wearable_samples (created_at);

-- ---------------------------------------------------------------- personal ring bands
-- Ring metrics only. BP targets stay in care_plans (review H5).
-- statistic = what the band is compared with (review M8):
--   night_median       median of the night window (00:00-06:00 local); heart_rate = resting heart rate
--   night_min          lowest value of the night window (spo2)
--   live_10min_median  median of a rolling 10-minute live window
create table public.patient_bands (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid not null references public.profiles (id) on delete cascade,
  metric text not null check (metric in ('heart_rate', 'hrv_rmssd', 'spo2', 'skin_temperature')),
  statistic text not null check (statistic in ('night_median', 'night_min', 'live_10min_median')),
  low numeric(6, 2) not null,
  high numeric(6, 2) not null,
  basis text not null check (basis in ('reference', 'model_proposal', 'doctor')),
  status text not null default 'proposed' check (status in ('proposed', 'active', 'superseded', 'rejected')),
  proposed_model_version text,
  approved_by uuid references public.profiles (id) on delete set null,
  approved_at timestamptz,
  effective_from date,
  supersedes_id uuid references public.patient_bands (id) on delete set null,
  created_at timestamptz not null default now(),
  unique (id, patient_id),
  check (low < high),
  check (status <> 'active' or (approved_by is not null and approved_at is not null and effective_from is not null))
);
create unique index patient_bands_one_active on public.patient_bands (patient_id, metric, statistic)
  where status = 'active';
create trigger patient_bands_roles before insert or update on public.patient_bands
  for each row execute function private.enforce_roles('approved_by', 'doctor', 'patient_id', 'patient');

-- ---------------------------------------------------------------- ring flags (advisory)
create table public.wearable_flags (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid not null references public.profiles (id) on delete cascade,
  metric text not null check (metric in ('heart_rate', 'hrv_rmssd', 'spo2', 'skin_temperature', 'multivariate')),
  kind text not null check (kind in ('outside_reference', 'personal_anomaly', 'multivariate_anomaly')),
  window_kind text not null check (window_kind in ('live_10min', 'night')),
  window_start timestamptz not null,
  window_end timestamptz not null,
  value numeric(7, 2),                 -- the window statistic; null for multivariate
  score numeric(8, 3),                 -- robust z or anomaly score
  reference_basis text not null check (length(reference_basis) <= 300),  -- which reference / band / baseline
  band_id uuid,
  model_version text not null,
  review_status text not null default 'open' check (review_status in ('open', 'confirmed', 'dismissed')),
  reviewed_by uuid references public.profiles (id) on delete set null,
  reviewed_at timestamptz,
  review_note text check (length(review_note) <= 2000),
  created_at timestamptz not null default now(),
  foreign key (band_id, patient_id) references public.patient_bands (id, patient_id),
  check (window_end > window_start),
  check ((kind = 'multivariate_anomaly') = (metric = 'multivariate')),
  check ((review_status = 'open') = (reviewed_at is null))
);
create unique index wearable_flags_once on public.wearable_flags (patient_id, metric, kind, window_start);
create index wearable_flags_patient_time on public.wearable_flags (patient_id, window_start desc);
create trigger wearable_flags_roles before insert or update on public.wearable_flags
  for each row execute function private.enforce_roles('reviewed_by', 'doctor', 'patient_id', 'patient');

-- ---------------------------------------------------------------- weekly doctor reports
create table public.weekly_reports (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid not null references public.profiles (id) on delete cascade,
  week_start date not null check (extract(isodow from week_start) = 1),   -- patient-local Monday (review L5)
  home_bp_category text check (home_bp_category in ('normal', 'elevated', 'stage_1_range', 'stage_2_range')),
  control_status text not null check (control_status in ('at_or_below_target', 'above_target', 'insufficient_data')),
  next_week_above_target_prob numeric(4, 3) check (next_week_above_target_prob between 0 and 1),
  model_versions jsonb not null default '{}',
  summary jsonb not null default '{}' check (pg_column_size(summary) <= 16384),
  status text not null default 'ready' check (status in ('ready', 'reviewed')),
  reviewed_by uuid references public.profiles (id) on delete set null,
  reviewed_at timestamptz,
  doctor_comment text check (length(doctor_comment) <= 4000),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (patient_id, week_start),
  check ((status = 'reviewed') = (reviewed_at is not null))
);
create trigger weekly_reports_roles before insert or update on public.weekly_reports
  for each row execute function private.enforce_roles('reviewed_by', 'doctor', 'patient_id', 'patient');
create trigger weekly_reports_touch before update on public.weekly_reports
  for each row execute function private.touch_updated_at();

-- Doctor decisions are clinical decisions: audit them (review M3).
create trigger patient_bands_audit after insert or update or delete on public.patient_bands
  for each row execute function private.audit();
create trigger wearable_flags_audit after insert or update or delete on public.wearable_flags
  for each row execute function private.audit();
create trigger weekly_reports_audit after insert or update or delete on public.weekly_reports
  for each row execute function private.audit();

-- ---------------------------------------------------------------- access (doctor / admin only, review M4)
revoke all on public.patient_bands, public.wearable_flags, public.weekly_reports from anon, authenticated;
grant select on public.patient_bands, public.wearable_flags, public.weekly_reports to authenticated;
alter table public.patient_bands enable row level security;
alter table public.wearable_flags enable row level security;
alter table public.weekly_reports enable row level security;

create policy patient_bands_read on public.patient_bands for select to authenticated
  using (private.is_assigned_doctor(patient_id) or private.current_app_role() = 'admin');
create policy wearable_flags_read on public.wearable_flags for select to authenticated
  using (private.is_assigned_doctor(patient_id) or private.current_app_role() = 'admin');
create policy weekly_reports_read on public.weekly_reports for select to authenticated
  using (private.is_assigned_doctor(patient_id) or private.current_app_role() = 'admin');

-- Doctor review columns (journal_entries pattern, review M1). The reviewer must be the caller.
grant update (review_status, reviewed_by, reviewed_at, review_note) on public.wearable_flags to authenticated;
create policy wearable_flags_review on public.wearable_flags for update to authenticated
  using (private.is_assigned_doctor(patient_id))
  with check (private.is_assigned_doctor(patient_id) and (review_status = 'open' or reviewed_by = (select auth.uid())));

grant update (status, reviewed_by, reviewed_at, doctor_comment) on public.weekly_reports to authenticated;
create policy weekly_reports_review on public.weekly_reports for update to authenticated
  using (private.is_assigned_doctor(patient_id))
  with check (private.is_assigned_doctor(patient_id) and (status = 'ready' or reviewed_by = (select auth.uid())));

-- Band approval / rejection by the assigned doctor; activation goes through approve_band (review M2).
grant update (status, approved_by, approved_at, effective_from, low, high, basis, supersedes_id)
  on public.patient_bands to authenticated;
create policy patient_bands_doctor_update on public.patient_bands for update to authenticated
  using (private.is_assigned_doctor(patient_id))
  with check (private.is_assigned_doctor(patient_id) and (approved_by is null or approved_by = (select auth.uid())));

-- Activate a proposed band in one transaction: supersede the current active band, then activate this one.
-- security invoker: RLS stays in force for doctors; the backend's privileged connection passes doctor_id
-- explicitly. If the doctor changes low/high, basis becomes 'doctor'. Not exposed by the API (private schema).
create function private.approve_band(p_band_id uuid, p_doctor_id uuid,
                                     p_low numeric default null, p_high numeric default null)
returns uuid language plpgsql security invoker set search_path = '' as $$
declare
  b public.patient_bands;
  previous uuid;
begin
  select * into b from public.patient_bands where id = p_band_id for update;
  if not found or b.status <> 'proposed' then
    raise exception 'band % is not a visible proposed band', p_band_id using errcode = '23514';
  end if;
  if auth.uid() is not null and auth.uid() <> p_doctor_id then
    raise exception 'the approving doctor must be the signed-in user' using errcode = '42501';
  end if;
  if not exists (select 1 from public.doctor_patient_assignments a
                 where a.doctor_id = p_doctor_id and a.patient_id = b.patient_id and a.status = 'active') then
    raise exception 'doctor is not actively assigned to this patient' using errcode = '42501';
  end if;
  update public.patient_bands set status = 'superseded'
   where patient_id = b.patient_id and metric = b.metric and statistic = b.statistic and status = 'active'
  returning id into previous;
  update public.patient_bands
     set status = 'active', approved_by = p_doctor_id, approved_at = now(), effective_from = current_date,
         low = coalesce(p_low, b.low), high = coalesce(p_high, b.high), supersedes_id = previous,
         basis = case when coalesce(p_low, b.low) <> b.low or coalesce(p_high, b.high) <> b.high
                      then 'doctor' else b.basis end
   where id = p_band_id;
  return p_band_id;
end $$;
revoke all on function private.approve_band(uuid, uuid, numeric, numeric) from public, anon;
grant execute on function private.approve_band(uuid, uuid, numeric, numeric) to authenticated;
