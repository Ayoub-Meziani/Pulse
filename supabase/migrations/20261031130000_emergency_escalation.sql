-- M11: emergency escalation (docs/EMERGENCY_ESCALATION_DESIGN.md), extending emergency_events.
-- Additive: existing events keep escalation_eligible = false and no escalation status.
-- The live project's default privileges grant ALL on new public objects to anon/authenticated,
-- so every new object revokes first and grants only what it needs. Only the API (privileged role)
-- and the escalation worker write escalation data; clients read through RLS.

-- ---------------------------------------------------------------- emergency_events
alter table public.emergency_events
  add column severity text check (severity in ('urgent', 'emergency')),
  add column evidence_provenance text
    check (evidence_provenance in ('manual', 'device', 'patient_reported', 'mixed', 'simulated', 'imported',
                                   'estimated', 'none')),
  add column escalation_eligible boolean not null default false,
  add column escalation_status text check (escalation_status in (
    'created', 'notification_attempted', 'delivered', 'acknowledged', 'escalated', 'resolved', 'cancelled')),
  add column escalation_policy text,
  add column patient_response text check (patient_response in ('ok', 'need_help')),
  add column patient_responded_at timestamptz,
  add column cancelled_at timestamptz,
  add column cancel_reason text check (cancel_reason in ('false_alarm', 'feel_better', 'other')),
  add column resolved_at timestamptz,
  add column resolution_outcome text check (char_length(resolution_outcome) <= 500),
  add column location_captured_at timestamptz,
  add column location_accuracy_m double precision check (location_accuracy_m >= 0);

-- Only deterministic, real evidence can make an episode eligible (never simulated, mixed, imported, estimated or ML).
alter table public.emergency_events add constraint emergency_eligible_evidence check (
  not escalation_eligible or evidence_provenance in ('manual', 'device', 'patient_reported'));
alter table public.emergency_events add constraint emergency_status_needs_eligibility check (
  (escalation_status is null) = (not escalation_eligible));
alter table public.emergency_events add constraint emergency_cancel_recorded check (
  escalation_status is distinct from 'cancelled' or (cancelled_at is not null and cancel_reason is not null));
alter table public.emergency_events add constraint emergency_resolve_recorded check (
  escalation_status is distinct from 'resolved' or (resolved_at is not null and resolution_outcome is not null));
alter table public.emergency_events add constraint emergency_location_time check (
  location_captured_at is null or location_lat is not null);
-- One active escalation per patient: new triggers are recorded on the active one, never start a second ladder.
create unique index emergency_one_active_escalation on public.emergency_events (patient_id)
  where escalation_eligible and escalation_status not in ('resolved', 'cancelled');

-- Clients may no longer write the escalation columns directly (the API owns them).
revoke insert, update on public.emergency_events from authenticated;
grant insert (id, patient_id, alert_id, trigger_reason, symptoms_snapshot, location_lat, location_lon,
              location_shared_with_consent, actions_attempted, reported_outcome, started_at, ended_at)
  on public.emergency_events to authenticated;
grant update (location_lat, location_lon, location_shared_with_consent, actions_attempted, reported_outcome, ended_at)
  on public.emergency_events to authenticated;

-- ---------------------------------------------------------------- trusted_contacts: order and contact consent
alter table public.trusted_contacts
  add column priority smallint not null default 1 check (priority between 1 and 9),
  add column phone_verified_at timestamptz,
  add column contact_consented_at timestamptz;  -- the contact agreed to receive alerts (needs a verified channel)

-- ---------------------------------------------------------------- care facilities (never contacted without an agreement)
create table public.care_facilities (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  wilaya text,
  oncall_phone text check (oncall_phone ~ '^\+?[0-9 ()-]{6,20}$'),
  verified_by uuid references public.profiles (id) on delete set null,
  verified_at timestamptz,
  verification_source text,
  agreement_status text not null default 'none' check (agreement_status in ('none', 'pending', 'active', 'ended')),
  agreement_ref text,
  active boolean not null default true,
  created_at timestamptz not null default now(),
  check ((verified_at is null) = (verified_by is null)),
  check (verified_at is null or verification_source is not null),
  check (agreement_status <> 'active' or (verified_at is not null and oncall_phone is not null))
);
create table public.doctor_facility_affiliations (
  doctor_id uuid not null references public.profiles (id) on delete cascade,
  facility_id uuid not null references public.care_facilities (id) on delete cascade,
  active boolean not null default true,
  primary key (doctor_id, facility_id)
);

-- ---------------------------------------------------------------- escalation steps (work queue + record)
create table public.escalation_steps (
  id uuid primary key default gen_random_uuid(),
  event_id uuid not null references public.emergency_events (id) on delete cascade,
  patient_id uuid not null references public.profiles (id) on delete cascade,
  stage text not null check (stage in ('doctor', 'doctor_reminder', 'facility', 'contact', 'emergency_services',
                                       'patient_reminder')),
  target_kind text not null check (target_kind in ('doctor', 'facility', 'contact', 'emergency_services', 'patient')),
  target_id uuid,
  channel text not null check (channel in ('in_app', 'web_push', 'sms', 'voice', 'fake', 'none')),
  sequence smallint not null default 1,
  status text not null default 'scheduled' check (status in (
    'scheduled', 'sending', 'sent', 'delivered', 'acknowledged', 'failed', 'expired', 'cancelled', 'skipped')),
  skip_reason text check (skip_reason in ('no_channel', 'no_official_channel', 'not_verified', 'no_agreement',
                                          'no_consent', 'superseded')),
  due_at timestamptz not null,
  ack_window_seconds integer check (ack_window_seconds > 0),
  ack_deadline timestamptz,
  attempts smallint not null default 0,
  max_attempts smallint not null default 3 check (max_attempts between 1 and 10),
  idempotency_key text not null unique,
  provider text,
  provider_message_id text,
  last_error text,
  sent_at timestamptz,
  delivered_at timestamptz,
  acknowledged_at timestamptz,
  acknowledged_by uuid references public.profiles (id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check ((status = 'skipped') = (skip_reason is not null)),
  check (status <> 'acknowledged' or acknowledged_at is not null),
  check (status <> 'delivered' or delivered_at is not null),
  check (attempts <= max_attempts)
);
create index escalation_steps_due on public.escalation_steps (due_at) where status in ('scheduled', 'sending');
create index escalation_steps_open_ack on public.escalation_steps (ack_deadline) where status in ('sent', 'delivered');
create index escalation_steps_event on public.escalation_steps (event_id, created_at);
create index escalation_steps_target on public.escalation_steps (target_kind, target_id) where status in ('sent', 'delivered');

-- ---------------------------------------------------------------- timeline (append-only)
create table public.escalation_timeline (
  id bigint generated always as identity primary key,
  event_id uuid not null references public.emergency_events (id) on delete cascade,
  patient_id uuid not null references public.profiles (id) on delete cascade,
  step_id uuid references public.escalation_steps (id) on delete set null,
  at timestamptz not null default clock_timestamp(),
  kind text not null,
  actor_kind text not null check (actor_kind in ('patient', 'doctor', 'contact', 'system')),
  actor_id uuid,
  details jsonb not null default '{}'::jsonb
);
create index escalation_timeline_event on public.escalation_timeline (event_id, at, id);

create function private.escalation_timeline_append_only() returns trigger
  language plpgsql set search_path = '' as $$
begin
  raise exception 'escalation_timeline is append-only';
end;
$$;
create trigger escalation_timeline_no_update_delete before update or delete on public.escalation_timeline
  for each row execute function private.escalation_timeline_append_only();
create trigger escalation_timeline_no_truncate before truncate on public.escalation_timeline
  for each statement execute function private.escalation_timeline_append_only();

-- ---------------------------------------------------------------- in-app notifications (non-urgent and escalation)
create table public.notifications (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  patient_id uuid references public.profiles (id) on delete cascade,
  kind text not null check (kind in ('alert_created', 'alert_raised', 'alert_reviewed', 'alert_resolved',
                                     'escalation', 'escalation_update')),
  alert_id uuid references public.alerts (id) on delete cascade,
  event_id uuid references public.emergency_events (id) on delete cascade,
  step_id uuid references public.escalation_steps (id) on delete set null,
  urgent boolean not null default false,
  created_at timestamptz not null default now(),
  read_at timestamptz,
  check (alert_id is not null or event_id is not null)
);
create index notifications_inbox on public.notifications (user_id, created_at desc);
create unique index notifications_once_per_step on public.notifications (step_id) where step_id is not null;

-- ---------------------------------------------------------------- access
alter table public.care_facilities enable row level security;
alter table public.doctor_facility_affiliations enable row level security;
alter table public.escalation_steps enable row level security;
alter table public.escalation_timeline enable row level security;
alter table public.notifications enable row level security;

revoke all on public.care_facilities, public.doctor_facility_affiliations, public.escalation_steps,
              public.escalation_timeline, public.notifications from anon, authenticated;
grant select on public.care_facilities, public.doctor_facility_affiliations, public.escalation_steps,
               public.escalation_timeline, public.notifications to authenticated;

create policy care_facilities_read on public.care_facilities for select to authenticated
  using (private.current_app_role() in ('doctor', 'admin'));
create policy affiliations_read on public.doctor_facility_affiliations for select to authenticated
  using (doctor_id = (select auth.uid()) or private.current_app_role() = 'admin');
create policy escalation_steps_read on public.escalation_steps for select to authenticated
  using (private.can_read_patient(patient_id));
create policy escalation_timeline_read on public.escalation_timeline for select to authenticated
  using (private.can_read_patient(patient_id));
create policy notifications_read_own on public.notifications for select to authenticated
  using (user_id = (select auth.uid()));

-- Every change to steps and facilities is also in audit_log.
create trigger escalation_steps_audit after insert or update or delete on public.escalation_steps
  for each row execute function private.audit();
create trigger care_facilities_audit after insert or update or delete on public.care_facilities
  for each row execute function private.audit();
create trigger escalation_steps_touch before update on public.escalation_steps
  for each row execute function private.touch_updated_at();
