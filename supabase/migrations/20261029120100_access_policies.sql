-- PULSE access control: row-level security on every table.
-- Patients: own records. Doctors: actively assigned patients only. Admin: read everything.
-- Service role (seed, import CLI, future rule engine) bypasses RLS and owns the remaining writes.

-- ---------------------------------------------------------------- helpers (security definer, not API-exposed)

create function private.current_app_role() returns text
language sql stable security definer set search_path = '' as $$
  select role from public.profiles where id = auth.uid()
$$;

create function private.is_assigned_doctor(patient uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.doctor_patient_assignments a
                 where a.doctor_id = auth.uid() and a.patient_id = patient and a.status = 'active')
$$;

create function private.is_my_doctor(doctor uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.doctor_patient_assignments a
                 where a.patient_id = auth.uid() and a.doctor_id = doctor and a.status = 'active')
$$;

create function private.can_read_patient(patient uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select patient = auth.uid() or private.is_assigned_doctor(patient) or private.current_app_role() = 'admin'
$$;

grant usage on schema private to authenticated;
grant execute on all functions in schema private to authenticated;

-- ---------------------------------------------------------------- baseline grants
-- Supabase grants ALL on public tables to anon/authenticated by default. Anonymous users get
-- nothing; TRUNCATE (which ignores RLS) is removed; writes are re-granted per table below.

revoke all on all tables in schema public from anon;
revoke all on all tables in schema public from authenticated;
grant select on all tables in schema public to authenticated;

do $$
declare t text;
begin
  foreach t in array array[
    'profiles', 'patient_profiles', 'doctor_patient_assignments', 'devices', 'ingestion_batches',
    'measurements', 'symptom_reports', 'lifestyle_logs', 'medications', 'medication_adherence_events',
    'journal_entries', 'care_plans', 'doctor_notes', 'alerts', 'trusted_contacts', 'emergency_events', 'audit_log'
  ] loop
    execute format('alter table public.%I enable row level security', t);
  end loop;
end $$;

-- ---------------------------------------------------------------- read policies

create policy profiles_read on public.profiles for select to authenticated
  using (private.can_read_patient(id) or private.is_my_doctor(id));

create policy assignments_read on public.doctor_patient_assignments for select to authenticated
  using (doctor_id = (select auth.uid()) or patient_id = (select auth.uid())
         or private.current_app_role() = 'admin');

create policy audit_read on public.audit_log for select to authenticated
  using (private.current_app_role() = 'admin');

do $$
declare t text;
begin
  foreach t in array array[
    'devices', 'ingestion_batches', 'measurements', 'symptom_reports', 'lifestyle_logs', 'medications',
    'medication_adherence_events', 'journal_entries', 'care_plans', 'doctor_notes', 'alerts',
    'trusted_contacts', 'emergency_events'
  ] loop
    execute format('create policy %I on public.%I for select to authenticated using (private.can_read_patient(patient_id))',
                   t || '_read', t);
  end loop;
  execute 'create policy patient_profiles_read on public.patient_profiles for select to authenticated using (private.can_read_patient(user_id))';
end $$;

-- ---------------------------------------------------------------- patient writes

-- Own profile: display name and time zone only (column grant), so role cannot be self-assigned.
grant update (display_name, timezone) on public.profiles to authenticated;
create policy profiles_update_own on public.profiles for update to authenticated
  using (id = (select auth.uid())) with check (id = (select auth.uid()));

grant insert, update on public.patient_profiles to authenticated;
create policy patient_profiles_write_own on public.patient_profiles for insert to authenticated
  with check (user_id = (select auth.uid()));
create policy patient_profiles_update_own on public.patient_profiles for update to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

grant insert, update on public.devices to authenticated;
create policy devices_insert_own on public.devices for insert to authenticated
  with check (patient_id = (select auth.uid()) and device_type <> 'simulator');
create policy devices_update_own on public.devices for update to authenticated
  using (patient_id = (select auth.uid())) with check (patient_id = (select auth.uid()) and device_type <> 'simulator');

-- Clients enter readings manually; csv_import / device_sync / simulated come through server tooling.
-- Measurements are append-only for clients (no update/delete grant).
grant insert on public.measurements to authenticated;
create policy measurements_insert_own on public.measurements for insert to authenticated
  with check (patient_id = (select auth.uid()) and source = 'manual' and provenance <> 'simulated'
              and ingestion_batch_id is null);

grant insert on public.symptom_reports to authenticated;
create policy symptoms_insert_own on public.symptom_reports for insert to authenticated
  with check (patient_id = (select auth.uid()) and source in ('patient_reported', 'bystander'));

grant insert, update, delete on public.lifestyle_logs to authenticated;
create policy lifestyle_insert_own on public.lifestyle_logs for insert to authenticated
  with check (patient_id = (select auth.uid()) and source = 'patient_reported');
create policy lifestyle_update_own on public.lifestyle_logs for update to authenticated
  using (patient_id = (select auth.uid())) with check (patient_id = (select auth.uid()) and source = 'patient_reported');
create policy lifestyle_delete_own on public.lifestyle_logs for delete to authenticated
  using (patient_id = (select auth.uid()));

grant insert on public.medication_adherence_events to authenticated;
create policy adherence_insert_own on public.medication_adherence_events for insert to authenticated
  with check (patient_id = (select auth.uid()) and source = 'patient_reported');

grant insert on public.journal_entries to authenticated;
create policy journal_insert_own on public.journal_entries for insert to authenticated
  with check (patient_id = (select auth.uid()) and doctor_review_status = 'not_reviewed');

grant insert, update, delete on public.trusted_contacts to authenticated;
create policy contacts_insert_own on public.trusted_contacts for insert to authenticated
  with check (patient_id = (select auth.uid()));
create policy contacts_update_own on public.trusted_contacts for update to authenticated
  using (patient_id = (select auth.uid())) with check (patient_id = (select auth.uid()));
create policy contacts_delete_own on public.trusted_contacts for delete to authenticated
  using (patient_id = (select auth.uid()));

grant insert, update on public.emergency_events to authenticated;
create policy emergency_insert_own on public.emergency_events for insert to authenticated
  with check (patient_id = (select auth.uid()));
create policy emergency_update_own on public.emergency_events for update to authenticated
  using (patient_id = (select auth.uid())) with check (patient_id = (select auth.uid()));

-- ---------------------------------------------------------------- shared: medications

grant insert, update on public.medications to authenticated;
create policy medications_insert on public.medications for insert to authenticated
  with check ((patient_id = (select auth.uid()) and source = 'patient_reported' and prescribed_by is null)
              or (private.is_assigned_doctor(patient_id) and source = 'clinician' and prescribed_by = (select auth.uid())));
create policy medications_update on public.medications for update to authenticated
  using ((patient_id = (select auth.uid()) and source = 'patient_reported')
         or (private.is_assigned_doctor(patient_id) and source = 'clinician'))
  with check ((patient_id = (select auth.uid()) and source = 'patient_reported' and prescribed_by is null)
              or (private.is_assigned_doctor(patient_id) and source = 'clinician' and prescribed_by is not null));

-- ---------------------------------------------------------------- doctor writes

grant update (doctor_review_status, reviewed_by, reviewed_at) on public.journal_entries to authenticated;
create policy journal_review_by_doctor on public.journal_entries for update to authenticated
  using (private.is_assigned_doctor(patient_id))
  with check (private.is_assigned_doctor(patient_id) and (reviewed_by is null or reviewed_by = (select auth.uid())));

grant insert, update on public.doctor_notes to authenticated;
create policy doctor_notes_insert on public.doctor_notes for insert to authenticated
  with check (doctor_id = (select auth.uid()) and private.is_assigned_doctor(patient_id));
create policy doctor_notes_update on public.doctor_notes for update to authenticated
  using (doctor_id = (select auth.uid()) and private.is_assigned_doctor(patient_id))
  with check (doctor_id = (select auth.uid()) and private.is_assigned_doctor(patient_id));

-- Any assigned doctor may supersede a plan; every change is in audit_log.
grant insert, update on public.care_plans to authenticated;
create policy care_plans_insert on public.care_plans for insert to authenticated
  with check (clinician_id = (select auth.uid()) and private.is_assigned_doctor(patient_id));
create policy care_plans_update on public.care_plans for update to authenticated
  using (private.is_assigned_doctor(patient_id)) with check (private.is_assigned_doctor(patient_id));

-- No client write policies (service role only this round): doctor_patient_assignments,
-- ingestion_batches, alerts, audit_log.
