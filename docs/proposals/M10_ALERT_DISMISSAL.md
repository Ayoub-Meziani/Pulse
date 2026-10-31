# M10 proposal: notice-alert dismissal and alert timeline (Q5)

Status: **proposal only. Not a migration, not applied anywhere.** Prepared 2026-10-31 for Ayoub (Q5 decision).
The SQL below is a draft for review. It must not be copied into `supabase/migrations/` until Ayoub approves it.
After approval it runs on the local and test databases, then on staging, and on production only with a separate
approval (`docs/engineering/PULSE_DATABASE_SYNC_POLICY.md`).

## 1. Decision being implemented (Ayoub, Q5)

- Only **notice** alerts can be dismissed: `alert_class = 'above_target'`, rule `R-TGT-1`.
- Only the patient (for their own alert) or the assigned doctor can dismiss. A reason is required.
- History is kept and nothing is deleted.
- The timeline is built from `audit_log`.

## 2. Current state (FACT, `main` `301e45b`)

| Item | State |
|---|---|
| Status CHECK | `alerts_status_check`: `open`, `acknowledged`, `reviewed`, `resolved` (core schema) |
| Transitions | `api/app/services/alerts.py` `ALLOWED`: `open → {acknowledged, reviewed}`, `acknowledged → {reviewed}`, `reviewed → {resolved}`. Resolving severe or emergency alerts needs a note |
| Level | Derived from `alert_class` (`vocab.ALERT_CLASS_TO_LEVEL`). A notice raised to severe changes `alert_class`, so it stops being dismissable |
| History | Trigger `private.audit()` writes every INSERT, UPDATE and DELETE of `alerts` to `audit_log`, with the old row, the new row and `auth.uid()` |
| Deletion | No API route and no RLS policy deletes alerts. Only the cascade from deleting a profile removes them |

## 3. Behaviour

| Topic | Rule |
|---|---|
| Allowed from | `open` or `acknowledged`, with `alert_class = 'above_target'` only. Any other class returns 409 `invalid_transition` (severe, emergency and trend alerts are never dismissable) |
| Who | The patient who owns the alert, or a doctor with an **active** assignment to that patient. Admins cannot dismiss. Anyone else gets 403 |
| Reason | One of `remeasured_lower`, `measurement_error`, `other`. `other` requires a note. Notes are at most 500 characters |
| Effect | Status `dismissed`. The alert leaves the active lists, so the next above-target reading opens a new notice instead of attaching to this one. It stays in "all alerts". The doctor can still review it (`dismissed → reviewed`) |
| Patient wording | "Votre médecin verra toujours cette alerte." (to be added to `app/analysis/texts.py` for clinician review) |
| Safety | Dismissing never changes rules, thresholds, emergency guidance or the emergency screen |

New transition table: `open → {acknowledged, reviewed, dismissed}`, `acknowledged → {reviewed, dismissed}`,
`dismissed → {reviewed}`, `reviewed → {resolved}`.

## 4. API (contract change: needs Ayoub's approval and `python -m app.export_openapi`)

- `POST /alerts/{id}/transition` accepts `{"to": "dismissed", "reason": "...", "note": "..."}`. The existing route
  is reused, so no new route is needed for dismissal.
- `AlertOut` gains `dismissed_at`, `dismissed_by_role` (`patient` or `doctor`), `dismissal_reason` and `dismissal_note`.
- New route `GET /alerts/{id}/events` returns a list of `{at, kind, actor_role, from_status, to_status, level, note}`:
  - **Kinds:** `created`, `level_raised`, `measurement_attached`, `status_changed`.
  - **Built from:** the `audit_log` rows of this alert, plus `alert_measurements.attached_at`.
  - **Order:** ascending time; ties are broken by audit id.
  - **Access:** the same as `GET /alerts/{id}`.
  - **Payload:** never the raw `old_data`/`new_data`, and never another user's id. Only the actor's role is returned.

## 5. Draft SQL (for review, not a migration)

```sql
-- M10 DRAFT: notice dismissal. Additive; no existing row changes.
alter table public.alerts drop constraint alerts_status_check;
alter table public.alerts add constraint alerts_status_check
  check (status in ('open', 'acknowledged', 'reviewed', 'resolved', 'dismissed'));

alter table public.alerts
  add column dismissed_at timestamptz,
  add column dismissed_by uuid references public.profiles (id) on delete set null,
  add column dismissal_reason text
    check (dismissal_reason in ('remeasured_lower', 'measurement_error', 'other')),
  add column dismissal_note text check (char_length(dismissal_note) <= 500);

-- A dismissed alert always records when and why.
alter table public.alerts add constraint alerts_dismissal_recorded check (
  status <> 'dismissed' or (dismissed_at is not null and dismissal_reason is not null));
-- 'other' needs an explanation.
alter table public.alerts add constraint alerts_dismissal_other_note check (
  dismissal_reason is distinct from 'other' or dismissal_note is not null);
-- Defence in depth: only notice alerts can carry a dismissal (the API enforces it first).
alter table public.alerts add constraint alerts_dismiss_notice_only check (
  dismissed_at is null or alert_class = 'above_target');
```

Optional part, to decide separately: make `audit_log` append-only.

```sql
create function private.audit_log_append_only() returns trigger
  language plpgsql as $$ begin raise exception 'audit_log is append-only'; end $$;
create trigger audit_log_no_update_delete before update or delete on public.audit_log
  for each row execute function private.audit_log_append_only();
create trigger audit_log_no_truncate before truncate on public.audit_log
  for each statement execute function private.audit_log_append_only();
```

Trade-off of the optional part: the trigger also blocks the privileged connection used by the API and
any future retention or erasure job. That job would then need its own reviewed migration. Recommended: include
it, because nothing deletes audit rows today.

**Rollback:** forward migration only. Remove the constraints and columns after checking that no row has
`status = 'dismissed'`. Never edit M10 after it is applied.

## 6. Tests to write with the implementation

- Transition matrix, covering actor (patient, assigned doctor, unassigned doctor, admin, other patient) × class
  (notice, trend, severe, emergency) × state. Severe, trend and emergency return 409. Unassigned doctors and
  other patients get 403.
- The reason is required; `other` requires a note; notes are at most 500 characters. The database CHECKs reject
  bad rows written directly.
- A dismissed alert is not active. The next above-target reading creates a new notice. A dismissed alert can move
  to `reviewed`.
- Timeline:
  - order and kinds;
  - a severity raise appears as `level_raised`;
  - attached readings appear;
  - there is no raw payload and no user ids.
- Contract freshness, plus both test profiles (`live` and `latest`).
- Frontend:
  - the patient sees a dismiss button only on notice alerts and must choose a reason;
  - the doctor sees the timeline in the alert detail.

Estimated effort after approval: about one day including tests. Dependencies: Ayoub's approval of the contract
change and of the migration, and a staging run before production.
