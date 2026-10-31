-- M10: dismissal of notice alerts (Q5, decided by Ayoub 2026-10-31) and an append-only audit_log.
-- Additive: no existing row changes. Proposal: docs/proposals/M10_ALERT_DISMISSAL.md.

-- 1. A new terminal-for-the-patient status. Only notice alerts (above_target, rule R-TGT-1) can carry it.
alter table public.alerts drop constraint alerts_status_check;
alter table public.alerts add constraint alerts_status_check
  check (status in ('open', 'acknowledged', 'reviewed', 'resolved', 'dismissed'));

alter table public.alerts
  add column dismissed_at timestamptz,
  add column dismissed_by uuid references public.profiles (id) on delete set null,
  add column dismissal_reason text
    check (dismissal_reason in ('remeasured_lower', 'measurement_error', 'other')),
  add column dismissal_note text check (char_length(dismissal_note) <= 500);

-- A dismissed alert always records when and why; 'other' needs an explanation.
alter table public.alerts add constraint alerts_dismissal_recorded check (
  status <> 'dismissed' or (dismissed_at is not null and dismissal_reason is not null));
alter table public.alerts add constraint alerts_dismissal_other_note check (
  dismissal_reason is distinct from 'other' or dismissal_note is not null);
-- Defence in depth: the API refuses first; severe, trend and emergency alerts can never carry a dismissal.
alter table public.alerts add constraint alerts_dismiss_notice_only check (
  dismissed_at is null or alert_class = 'above_target');

-- 2. audit_log is the alert timeline: nobody may rewrite or remove it (rolled-back transactions are unaffected).
create function private.audit_log_append_only() returns trigger
  language plpgsql set search_path = '' as $$
begin
  raise exception 'audit_log is append-only';
end;
$$;
create trigger audit_log_no_update_delete before update or delete on public.audit_log
  for each row execute function private.audit_log_append_only();
create trigger audit_log_no_truncate before truncate on public.audit_log
  for each statement execute function private.audit_log_append_only();
