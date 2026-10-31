# Emergency escalation: design and phased plan

Status (2026-10-31, branch `feat/emergency-escalation`): **phase P1 implemented and tested locally; not deployed.**
- Done: migration M11 `20261031130000_emergency_escalation.sql`; `app/services/escalation.py` (eligibility,
  ladder, statuses, retries, timeouts, cancel, resolve, idempotency, one active escalation per patient);
  `app/escalation_worker.py`; routes in `app/routers/escalation.py`; non-urgent in-app notifications; frontend
  panel "Qui est prévenu ?", local alarm (foreground only), doctor banner, notifications page.
- Channels in P1: in-app only. Trusted contacts, facilities and the Protection Civile are recorded as **not
  notified** (`skipped`, `no_channel` / `no_agreement` / `no_official_channel`).
- **Off by default** (`PULSE_ESCALATION_ENABLED`): it stays off in staging and production until a clinician
  approves the triggers, the delays (§3) and the wording.
- Not done (blocked; see §8): web push, SMS/voice (provider contract + ANPDP), native alarm app, facility
  agreements, any DGPC channel, facility admin screens.
- Evidence: backend 510 tests (32 escalation); a 12-step end-to-end run on a local Auth+API+worker stack; frontend
  42 tests. Browser test of the new screens: not done (see the PR description).
- It **extends** the existing emergency episodes (`emergency_events`, `api/app/routers/emergency.py`,
  `frontend/src/pages/patient/EmergencyScreen.jsx`, `frontend/src/lib/incident.js`). It does not create a second
  emergency system.
- External facts and their sources are in `docs/ALGERIA_EMERGENCY_FEASIBILITY.md`.

## 0. Non-negotiable rules (from CLAUDE.md and Ayoub's instructions)

1. **Escalation never delays urgent guidance.**
   - The emergency screen and the patient's own call to 14 are always first.
   - Escalation runs beside them; it never replaces them.
2. **Only deterministic rules can start an escalation** (`app/analysis/rules.py`), or the patient themself
   (the emergency button).
   - These never start one: ML estimates, `live-v1` early warnings, ring/wearable flags, `R-RING-1`
     (which stays disabled), and trend alerts.
3. **Provenance gate:**
   - Readings labelled `simulated` never start an escalation.
   - Mixed-provenance evidence never starts one either: if any reading behind the decision is not
     `manual` or `device`, there is no escalation.
   - Red-flag symptoms entered by the patient count as patient-reported, so they are eligible.
4. **Honest statuses:**
   - "delivered" only from a provider receipt;
   - "acknowledged" only from a human action;
   - never "called", "received by emergency services" or "help is coming".
5. **No unverified number is ever contacted automatically.**
   - Emergency numbers stay `verified: false` until they are checked.
   - Hospital numbers are never hardcoded. They come from an admin-verified facility record with a source and date.
6. **Everything is recorded** in an append-only timeline. Nothing is deleted.
7. **It must work offline** on the patient's side: the existing local queue (`lib/incident.js`) keeps the
   episode, and the server escalates as soon as the episode reaches it.

## 1. Severity levels

| Class | Triggered by (deterministic) | Escalation |
|---|---|---|
| **Information**: `none`, `notice` (R-TGT-1), `trend` (R-TRD-1) | Above target, trend | None. In-app only. Notice can be dismissed (Q5, `docs/proposals/M10_ALERT_DISMISSAL.md`) |
| **Urgent review** (severity `urgent`) | R-SEV-1/2/3 (≥ 180/120) **without** red-flag symptoms, from manual or device readings | Patient: existing symptom check, plus a re-measure after 60 s. Doctor: notified for review, with an acknowledgement expected within the policy delay (default 30 min, configurable). **Never** contacts trusted contacts or emergency services by itself |
| **Emergency** (severity `emergency`) | R-EMG-1 (red-flag symptom), a severe reading combined with red-flag symptoms, or the patient's **Emergency** button | Full ladder (§3): local alarm, doctor, trusted contacts, emergency-services fallback |

The severity is **computed on the server** from the rule evaluation and the provenance gate. The
`trigger_reason` sent by the client is recorded but never trusted to start an escalation by itself. One exception:
the patient's Emergency button (`manual`) is always eligible, because it is the patient's own decision.

## 2. State machines

### 2.1 Escalation (one per emergency episode): `emergency_events.escalation_status`

```
            ┌──────────── cancel (patient: "fausse alerte", reason required) ────────────┐
            │                                                                             ▼
 created ──► notification_attempted ──► delivered ──► acknowledged ──► resolved      cancelled
                     │      ▲               │             │
                     │      └── retry ──────┘             │
                     └──── timeout / failure ──► escalated ──► (next step: back to notification_attempted)
```

| Status | Meaning (exact) | Set by |
|---|---|---|
| `created` | The episode exists and is eligible; no notification has been attempted yet | API (create) |
| `notification_attempted` | At least one notification was handed to a channel (in-app, push, SMS or voice) | Worker |
| `delivered` | At least one provider receipt confirms delivery to a device. **Not "read"** | Worker (receipt webhook) |
| `acknowledged` | A human (doctor or trusted contact) pressed "J'ai vu / je m'en occupe". **It means seen, not that help has arrived** | API (ack) |
| `escalated` | A step timed out or failed and the next step was scheduled | Worker |
| `resolved` | Closed with an outcome by the patient, the doctor or a contact (an outcome is required; it is not a diagnosis) | API |
| `cancelled` | The patient cancelled (false alarm). Pending steps stop; contacts already notified get a "cancelled" follow-up | API |

Terminal states are `resolved` and `cancelled`. Every change is a timeline row (§4.3). Allowed transitions are
enforced in one service function, like `alerts.ALLOWED`.

### 2.2 Notification step (each target and channel attempt): `escalation_steps.status`

`scheduled → sending → sent → delivered → acknowledged`, with the terminal side exits `failed`, `expired`
(no acknowledgement before `ack_deadline`) and `cancelled`.

The episode status is derived from its steps (for example, the first `sent` step moves the episode to
`notification_attempted`). The derived status is written in the same transaction.

## 3. Escalation ladder (policy `emergency-v1`, all delays configurable and versioned)

| Stage | Target | Channel by phase (§7) | Starts | Ack window → next |
|---|---|---|---|---|
| 0 | Patient | Emergency screen (existing) with the 14 call button | t = 0, always | — (never waits) |
| 1 | Patient's phone | Loud alarm. P1: in-app while open. P3: native alarm. Buttons: **"Je vais bien"**, **"J'ai besoin d'aide"**, **"Fausse alerte"** | t = 0 | 60 s without an answer → stages 2 and 3 marked "patient unresponsive" |
| 2a | Assigned doctor (active assignment) | P1: in-app + web push. P2: SMS/voice | t = 0 + `cancel_grace` (30 s) | 5 min → 2b |
| 2b | Verified associated facility (only if `agreement_status = 'active'`) | P2: SMS/voice | after 2a times out | 5 min → next contact |
| 3 | Trusted contacts, in **priority order**, only those with consent and a verified phone | P2: SMS with an ack link (+ location link if the patient consented); voice optional | t = 0 + `cancel_grace`, contact #1; then #2 after 3 min without an ack, and so on | Last contact expires → stage 4 reminder |
| 4 | Emergency services | **No automated channel exists.** Fallback: the patient's screen keeps the 14 button; every message to the doctor and contacts says "Si vous ne pouvez pas joindre {prénom}, appelez le 14 et donnez cette position"; the timeline records "relais 14 demandé", never "14 notified" | With stages 2 and 3 | — |

Default delays are placeholders and **need clinical review**: `cancel_grace` 30 s, patient alarm 60 s, doctor
5 min, contact 3 min, urgent review 30 min.

**Retries:**
- per step, up to 3 attempts with backoff (10 s, 30 s, 90 s) on provider errors;
- never retry after `delivered`;
- a voice call retries only on no-answer, up to 2 times.

**Urgent review (non-emergency)** uses only stage 2a with the 30 min window. If it times out, a second
reminder goes to the doctor and the alert is marked "not seen" on the doctor dashboard. Contacts are never
notified.

## 4. Data model (proposal "M11", after M10; draft only, numbering fixed at approval time)

### 4.1 `emergency_events`: additive columns

`severity text check (severity in ('urgent','emergency'))`, `escalation_status text` (§2.1),
`escalation_policy text` (for example `emergency-v1`), `evidence_provenance text check (in ('manual','device','patient_reported','mixed','simulated'))`,
`escalation_eligible boolean not null default false`,
`cancelled_at`, `cancelled_by`, `cancel_reason`, `resolved_at`, `resolved_by`, `resolution_outcome`.
CHECKs:
- `escalation_eligible ⇒ evidence_provenance in ('manual','device','patient_reported')`;
- the terminal statuses require their timestamps.

Partial unique index: **one active escalation per patient**:
`(patient_id) where escalation_status not in ('resolved','cancelled') and escalation_eligible`.
New triggers attach to the active episode, the same way alerts absorb readings.

### 4.2 New tables

| Table | Key columns | Notes |
|---|---|---|
| `escalation_steps` | `id`, `event_id`, `stage`, `target_kind` (`patient_device`, `doctor`, `facility`, `contact`), `target_id`, `channel` (`in_app`, `web_push`, `fcm`, `apns`, `sms`, `voice`), `sequence`, `due_at`, `ack_deadline`, `status` (§2.2), `attempts`, `max_attempts`, `provider`, `provider_message_id`, `idempotency_key unique`, `last_error`, `sent_at`, `delivered_at`, `acknowledged_at`, `acknowledged_by_kind`, `ack_token_hash`, `ack_token_expires_at` | Work queue and record. `idempotency_key = event_id:stage:target_id:channel:attempt` |
| `escalation_timeline` | `id bigint identity`, `event_id`, `step_id`, `at`, `kind`, `actor_kind`, `actor_id`, `details jsonb` | Append-only (UPDATE, DELETE and TRUNCATE rejected by trigger). This is the source for the timeline API |
| `care_facilities` | `id`, `name`, `wilaya`, `oncall_phone`, `verified_by`, `verified_at`, `verification_source`, `agreement_status` (`none`, `pending`, `active`, `ended`), `agreement_ref`, `active` | Admin-managed. Without `active` agreement plus verification, the facility is never contacted |
| `doctor_facility_affiliations` | `doctor_id`, `facility_id`, `role`, `active` | Links the doctor to the facility |
| `notification_devices` | `id`, `user_id`, `platform` (`web`, `android`, `ios`), `token` (stored encrypted or hashed where possible), `created_at`, `last_seen_at`, `revoked_at` | Push targets |
| `escalation_policies` | `name`, `version`, `config jsonb`, `approved_by`, `approved_at` | Delays, order and channels. Changing it needs clinical sign-off; the episode records the version it used |

`trusted_contacts`: additive columns:
- `priority smallint`;
- `phone_verified_at`;
- `consent_contact_at` (the contact agreed to receive alerts);
- `consent_location boolean` (the patient agreed to share location with this contact);
- `consent_text_version`, `locale` (`fr`, `ar`);
- `revoked_at`.

A contact is eligible only if `active` and `phone_verified_at` and `consent_contact_at` are set and `revoked_at`
is null.

RLS:
- The patient reads their own episodes, steps and timeline. Doctors read them only through an active assignment.
- Contacts never get database access: they use a tokenized page through the API.
- Admins manage facilities but cannot read episodes.
- The worker uses a dedicated role with the minimum rights (insert and update on steps and timeline, read on
  contacts and facilities).

## 5. Escalation engine

- **Where it runs:** a separate worker process (`python -m app.escalation.worker`), not in the request path.
  - It shares the backend codebase and the database.
  - One worker is enough at first. Locking with `FOR UPDATE SKIP LOCKED` lets several run safely.
  - A Postgres-backed queue (`escalation_steps.due_at`) means no extra infrastructure. An optional
    `LISTEN/NOTIFY` wakes the worker on new steps, and it polls every 2 s as a fallback.
- **Start:**
  - `POST /patients/{id}/emergency-events` (the existing route) evaluates eligibility in the same transaction:
    rules, provenance gate, and an active doctor or contact.
  - It sets `severity` and `escalation_status = 'created'`, and inserts the first steps according to the policy.
  - The client sees `escalation: {status, steps[]}` in the response.
- **Idempotency:**
  - The episode id is the client UUID (existing).
  - Steps have unique idempotency keys, and the key is passed to providers that accept one.
  - A worker crash between send and record can produce at most one duplicate per provider attempt. This is the
    accepted cost of at-least-once sending; the alternative risks a lost alert.
  - Acknowledgement and cancel calls are idempotent: a repeat returns the current state.
- **Duplicate prevention:**
  - one active escalation per patient (§4.1);
  - repeated triggers within the active episode attach evidence and never restart the ladder;
  - one message per target per stage, unless it is a retry.
- **Cancellation:**
  - The patient can cancel; the reason is required (`false_alarm`, `feel_better`, `other`).
  - Pending steps become `cancelled`. Targets already notified get a short "annulé par {prénom} à HH:MM" message
    on the same channel.
  - A cancellation never deletes anything.
  - **Safety:** the cancel button sits behind a confirmation, and the emergency screen stays available afterwards.
- **Timeouts:** the worker turns steps past `ack_deadline` into `expired` and schedules the next stage
  (`escalated`).
- **Provider abstraction:**
  - Interface: `send(step) → {provider_message_id}` or an error class (`retryable`, `permanent`), and
    `parse_receipt(request) → {message_id, status}`.
  - Implementations:
    - `InAppChannel` (P1);
    - `WebPushChannel` (P1);
    - `FakeChannel` for tests and demos, which writes `simulated` in the timeline and is shown as
      "simulé" in the UI;
    - `SmsChannel` and `VoiceChannel` (P2, provider chosen later);
    - `FcmChannel` and `ApnsChannel` (P3).
  - Providers are selected by configuration. Secrets live in the environment, never in the repository.
- **Receipts:**
  - `POST /webhooks/{provider}/status`, authenticated by the provider's signature (rejected otherwise).
  - Maps to `delivered` or `failed`.
- **Observability:**
  - every transition goes to the timeline;
  - a health endpoint reports the worker heartbeat and queue lag;
  - an alert to the team fires if the worker is down for more than 60 s (P2). If the worker is down, the
    patient's emergency screen still works, because it is client-side.

## 6. API (proposal: contract change, Ayoub to approve; `python -m app.export_openapi`)

| Route | Who | Purpose |
|---|---|---|
| `POST /patients/{id}/emergency-events` (existing) | Patient | Also returns `severity`, `escalation_status` and `steps` |
| `POST /emergency-events/{id}/patient-response` | Patient | `{"response": "ok" \| "need_help"}` (stage 1). Idempotent |
| `POST /emergency-events/{id}/cancel` | Patient | `{"reason": …}`. Idempotent |
| `POST /emergency-events/{id}/resolve` | Patient, assigned doctor | `{"outcome": …, "note": …}` |
| `GET /emergency-events/{id}/timeline` | Patient, assigned doctor | Ordered events with actor kinds, never tokens or phone numbers |
| `GET /doctor/escalations?status=active` | Doctor | Active escalations of assigned patients |
| `POST /escalation-steps/{id}/acknowledge` | Doctor (target) | "J'ai vu / je m'en occupe" |
| `GET /ack/{token}` · `POST /ack/{token}` | Trusted contact (no account) | Minimal page: patient first name, time, "a déclenché une alerte", location if consented, buttons "Je m'en occupe" / "Je ne peux pas". The token is single-use for the action, expires in 24 h, is stored as a hash and rate-limited |
| `POST /me/notification-devices`, `DELETE /me/notification-devices/{id}` | Any user | Push registration |
| `POST /trusted-contacts/{id}/verification` · `POST /trusted-contacts/{id}/verification/confirm` | Patient | OTP to the contact's phone (P2; needs SMS). Records the contact's consent |
| `PATCH /trusted-contacts/{id}` (existing) | Patient | Adds `priority`, `consent_location` |
| `GET/POST/PATCH /admin/facilities` | Admin | Verified facilities and agreement status |
| `POST /webhooks/{provider}/status` | Provider | Delivery receipts (signed) |

Errors use the existing envelope `{"error": {code, message, details}}`, and invalid transitions return 409
`invalid_transition`.

## 7. Frontend

- **Patient, emergency screen:** the existing screen stays first and unchanged in its order (call 14, card, contact,
  share). A new **"Qui est prévenu"** panel shows one line per step with honest states:
  - "En attente", "Envoyé", "Reçu par le téléphone" (receipt), "Vu par Dr X" (acknowledged), "Pas de réponse",
    "Échec";
  - in P1 the doctor line says "Notification dans l'application", and nothing says "SMS" or "appel" unless that
    channel is live.
  - Below the panel are the **Fausse alerte** button (with a confirmation and a reason) and **Je vais bien**.
- **Patient, local alarm (P1):** while the app is open, a full-screen red overlay with a looping sound (Web Audio,
  started by the user's tap that opened the episode), vibration (Android) and a Wake Lock. The text is explicit:
  "L'alarme ne sonne que si PULSE est ouvert."
- **Patient, settings:**
  - trusted contacts with priority (drag order), per-contact location consent, verification status and
    "invitation envoyée";
  - a **"Tester l'alarme"** button that is local only and sends nothing;
  - notification permission onboarding;
  - P3: battery-optimisation guidance for the patient's phone brand.
- **Doctor:**
  - a persistent banner for active escalations of assigned patients (polling every 15 s, or SSE);
  - a web push permission prompt;
  - the "J'ai vu / je m'en occupe" button;
  - the timeline in the existing `DoctorEmergencies` report (`components/doctor/DoctorRecordSections.jsx`).
- **Trusted contact page** (`/ack/:token`): a public, minimal, bilingual FR/AR page (RTL for Arabic) with no
  medical data beyond "alerte déclenchée", and the 14 instruction.
- **Admin:** a facilities list with verification fields and agreement status. No access to episodes.
- **Offline:** unchanged queue (`lib/incident.js`). The panel shows "Hors ligne : personne n'est encore prévenu
  par PULSE. Appelez le 14."

## 8. Phased plan

| Phase | Content | Depends on | Tests | Gate |
|---|---|---|---|---|
| **P0 Decisions** | Clinical review of the severity mapping, delays and wording; legal review (ANPDP, consent texts); choice of SMS/voice provider (quotes); contact with DGPC about verifying 14/1021 and a possible channel | Ayoub, a clinician, a lawyer | — | Ayoub approves this design |
| **P1 Engine on current technology** | M10 and M11 (local → staging); worker; state machine; `InApp`, `WebPush` and `Fake` channels; doctor acknowledgement; cancel; timeline; in-app alarm; contact ack page (link shown in the app only, no sending); provenance gate | P0 approval, staging | Unit: transition matrix, eligibility (simulated, mixed and ML never escalate; manual button always does), idempotency (double create, double ack, double cancel), one active escalation per patient, timeouts → `escalated`, cancellation stops pending steps, retry/backoff, worker crash and restart (no lost step), clock-controlled tests. API: RLS (other patient, unassigned doctor 403), contract. Frontend: honest labels, offline banner, cancel confirmation. E2E on staging with `FakeChannel` | Staging run; Ayoub approves the production migration |
| **P2 SMS and voice** | `SmsChannel` and `VoiceChannel` behind the abstraction; contact OTP verification and consent; receipts webhook; cancellation follow-ups; message templates FR/AR | Provider contract, sender ID, ANPDP steps, consent texts approved | Provider sandbox; signed-webhook tests; delivery to team phones only (never emergency numbers); receipt mapping; rate limits | Legal OK and Ayoub approval before any real recipient |
| **P3 Native alarm** | Android app (alarm channel, full-screen intent declaration, FCM high priority, `setAlarmClock` re-alarm); later iOS (Critical Alerts request) | Developer accounts, Play declaration, Apple entitlement | **Real-device matrix**: at least 3 Android brands (including Xiaomi/Oppo-type battery managers) × locked, DND, battery saver, app killed. No claim of a guaranteed alarm before this passes | Device test report |
| **P4 Institutions** | Verified facilities with agreements; any DGPC channel if one is offered | Written agreements | Joint test procedure with the institution | Agreement signed |

**Effort estimates** (indicative): P1 about 6–8 developer-days including tests; P2 about 3–4 days after the
contract; P3 about 2–3 weeks for Android including device testing.

## 9. Risks

| Risk | Kind | Mitigation |
|---|---|---|
| A false sense of safety ("PULSE will call for help") | Clinical | Wording reviewed by a clinician; the 14 call is always first; honest statuses; onboarding explains the limits |
| Alarm fatigue or false alarms upset contacts | Clinical / social | Server-side eligibility; cancel grace; the urgent class never contacts relatives; clinician-reviewed delays |
| A doctor's acknowledgement is read as "a doctor is handling it" | Clinical / legal | Wording "a vu l'alerte"; contacts are still notified unless the patient cancels or resolves |
| A delayed or failed notification (provider, network, OEM battery) | Operational | Multiple channels; retries; ladder; worker health alert; P3 device testing |
| Location and health data sent to contacts; storage abroad | Privacy / legal | Explicit per-contact consent; minimal content; ANPDP authorization; fictional data until then |
| Wrong or unverified numbers (emergency services, hospitals) | Safety | `verified` flags; admin verification with a source; never call emergency numbers automatically or in tests |
| SMS spoofing or reuse of ack links | Security | Hashed single-use tokens with expiry; no medical detail on the page; rate limits |
| Worker outage | Operational | Health endpoint and alert; the client-side emergency screen is independent |
| Simulated or ML data reaching the engine | Safety | Provenance gate at the database CHECK and in the service; tests |
| Liability without an agreement with institutions | Legal | No automatic hospital or DGPC contact without a signed agreement |

## 10. Approvals needed before any work starts

1. This design (severity mapping, statuses, ladder, data model), with a clinician's review of the delays and wording.
2. The M10 and M11 contract and migration changes (local → staging → production, each approved separately).
3. The staging project (`docs/STAGING_SETUP.md`), which has a cost.
4. The provider choice and contract, after a legal review; the native-app decision and developer accounts.
