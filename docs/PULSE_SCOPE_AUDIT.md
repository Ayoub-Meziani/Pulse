# PULSE — V1 scope completeness audit

Date: 2026-10-30 (evening). Author: Claude Code for Ayoub. Branch: `feat/v1-completion` from `main` `00ea3b2`.
Status words: **Verified** = works end to end against the real API and was exercised in a browser or an API-level
acceptance run; **Implemented, not fully verified**; **Partial**; **Backend only**; **Frontend only**;
**Designed only** (schema or contract exists, no working feature); **Discussed, not implemented**;
**Proposed, never approved**; **Decision needed** (Ayoub and/or clinician).

## Sources used

| Ref | Source | What it is |
|---|---|---|
| C | `docs/conception.pdf` v0.9 (29 Oct 2026, "draft for team critique") | The only full product specification in the repository: scope §4, rules §5, state machine §6, emergency workflow §7, data model §10, API §11, permissions §12, screens §14, acceptance §15 |
| D | `docs/decisions.md` | Decisions D1–D20 (D13–D16 describe the abandoned SQLite slice) |
| H | `docs/PULSE_GLOBAL_PROJECT_HANDOFF.md` (untracked, 30 Oct 18:47) | Status of every module at that time |
| F | `docs/frontend/*.md`, `docs/frontend/lovable/*` (untracked, 30 Oct) | Frontend master spec, route inventory, gap register, decisions D-01…D-12 |
| A | `PULSE_*.md` on `main` (architecture, plans, blockers B1–B31, contracts) and branch `AI` `docs/data/*` | Backend and data documentation |
| S | Code: `supabase/migrations`, `api/app`, `contract/openapi.json`, `frontend/src` on `main` | What exists |

**Limitation:** earlier conversations (the hackathon brief "Problématique 2", the first team concept notes and
any chat between team members) are not in the repository. Section 2 of C summarises how the first concept was
changed; nothing beyond C, H, F and A is claimed here as a requirement.

---

## Executive summary

1. **What PULSE was meant to be (C §1).** A mobile-first web app for people with hypertension and their
   doctors: patients record readings (typed, or a clearly labelled simulated device); PULSE explains each one
   against a target, spots trends, and switches to a short emergency flow (call, medical card, location,
   trusted contact) on a dangerous reading or red-flag symptom; every alert and emergency is recorded for the
   patient's own doctor, who follows up from a dashboard. Priority order: 1 emergency action, 2 readings and
   alerts, 3 doctor follow-up and history, 4 journal, lifestyle guidance, AI summary.
2. **What it does today (`main` 00ea3b2).** Priorities 2 and 3 work end to end (readings, validation, rules,
   alerts, history, summaries with provenance, doctor list and patient record, notes, care-plan view,
   wearables view, stored predictions). Priority 1 is only partly there: the emergency screen shows the
   numbers and the disclaimer, but the medical card, the trusted-contact call/share, location, the incident
   record and the outcome are not wired in the frontend, although the API for them exists and is tested.
3. **Important missing functionality.** The emergency incident workflow in the UI (C §7, MVP), the doctor's
   incident report (MVP), the journal (MVP, API returns 501), profile and trusted-contact editing (MVP),
   doctor care-plan editing (MVP), the 15-second doctor refresh (C §8.2), the "dismiss notice" state and the
   alert event timeline (C §6; not in the built API).
4. **Why sport and nutrition are not visible.** They were never specified as tracking modules. C §2 turned
   the first concept's "sport and food: what to do / avoid this week" into **general education cards
   (activity, salt, sleep), "if time"**, sourced, clinician-reviewed and labelled "general information, not a
   prescription", with the doctor's own advice shown separately. Patients were to record food and activity as
   **journal entries** (categories `food`, `activity`), and the journal is still a 501 stub. Separately, the
   data/AI developer added a structured `lifestyle_logs` table (meals with sodium, activity type/intensity/
   steps, sleep, stress, Ramadan fasting) and diet-habit fields on the profile (bread portions, salt at table,
   salty processed food) — database and seed only, no API, no screen; exposing them is open decision **B22**
   and frontend decision **D-11** explicitly kept them out of the UI. The guidance cards were never written or
   reviewed. So: journal = **agreed but not built**; structured sport/food tracking = **designed in the
   database, never agreed for the product**; guidance cards = **"if time", content and clinical review missing**.
5. **Needed for the intended V1.** The emergency incident workflow (frontend on the existing API), the doctor
   incident report, the journal (backend + frontend; it is also where food and activity are recorded),
   profile/contact editing and doctor care-plan editing. All are specified in C and the contract. Plus an
   isolated staging environment.
6. **Defer to V2 (or needs a decision first).** Structured lifestyle tracking (activity/meals/sodium/sleep),
   general guidance cards, medications and adherence, body measurements, diet-habit profile fields, the AI
   weekly summary for doctors, weekly reports / ring flags / band approval, live early warnings (M9 / live-v1),
   lock-screen card and Medical ID guide, "attract attention" sound, missing-reading reminder, daily
   morning/evening means, alert dismiss + event timeline (contract change), Arabic UI throughout.

---

## 1. Feature inventory

Columns: **Spec** = where it was specified; **DB / API / UI** = exists (✓), partial (~), no (✗); **Works** =
works end to end with real API data; **Tests** = automated (backend pytest / frontend vitest / API acceptance)
and browser checks performed in this project.

### A. Blood-pressure monitoring

| Feature | Spec | DB | API | UI | Works | Tests | Status | Remaining |
|---|---|---|---|---|---|---|---|---|
| Manual reading with context (rested, position, pulse, time) | C §4, §14.1 | ✓ | ✓ | ✓ | Yes | pytest, acceptance S2, browser | **Verified** | — |
| Repeat-safe submission (client id) | D17 | ✓ | ✓ | ✓ | Yes | pytest (incl. concurrent), acceptance S3, vitest | **Verified** (UI double-tap not browser-tested) | — |
| Validation (pulse-v1 trigger: valid / needs_review / invalid) | C §5.1, M1/M3 | ✓ | ✓ | ✓ | Yes | pytest, acceptance S4 | **Verified** | C's V1–V3 "reject with 422" became "store as invalid + DATA-INVALID" (documented in contract) |
| Provenance (manual / simulated / estimated / device) shown everywhere | C §5.4, D18 | ✓ | ✓ | ✓ | Yes | pytest, browser | **Verified** | — |
| Simulated device feed | C §4 ("script + dev endpoint") | ✓ | ✗ (no dev endpoint) | n/a | Seed only | — | **Partial** | `POST /dev/simulate` never built; simulated history is seeded by script |
| History + trend chart with target line | C §14.1 | ✓ | ✓ | ✓ | Yes | browser | **Verified** | Severe markers on chart not drawn |
| 7/30-day summary, trend, provenance counts | C §13, D20 | ✓ | ✓ | ✓ | Yes | pytest, browser | **Verified** | — |
| Daily morning/evening means | contract `/daily` | ✓ | 501 | ✗ | No | contract test (501) | **Designed only** | Deferrable (C does not list it) |
| Deterministic rules R-TGT-1, R-TRD-1, R-SEV-1/2/3, R-EMG-1 | C §5.3 | ✓ | ✓ | ✓ | Yes | pytest T1–T16 equivalents | **Verified** | Clinician review of thresholds and wording (B13, S2) |
| Symptom check after severe reading + red flags → emergency | C §4 | ✓ | ✓ | ✓ | Yes | pytest, acceptance S5, browser | **Verified** | — |
| "I feel unwell" / symptom-only report | C §4 | ✓ | ✓ | ✓ | Yes | acceptance, browser | **Verified** | — |
| Recheck timer 60 s | C §4 | n/a | ✓ (`recheck_after_seconds`) | ✓ | Yes | vitest, browser (timer seen) | **Verified** | — |
| Symptom ↔ reading link stored | C §10 (`measurement_id`) | ✗ | validated, not stored | n/a | No | pytest (null) | **Designed only** (B24) | Needs a migration |
| Symptom history list | — (added D18) | ✓ | ✓ | ✓ | Yes | pytest, browser | **Verified** | — |
| Alert state machine: acknowledge, review, close with note | C §6 | ✓ | ✓ | ✓ | Yes | pytest, browser (doctor review + close) | **Verified** | — |
| Alert "dismiss" (notice only) and "escalated" states | C §6 | ✗ | ✗ | ✗ | No | — | **Discussed, not implemented** | Contract + schema change; Ayoub decision |
| Alert event timeline (alert_events) | C §6, §10 | `audit_log` (admin-readable) | ✗ | ✗ | No | — | **Discussed, not implemented** | Endpoint over audit data; decision (B30 privacy) |
| Patient summary shown to doctor | C §14.2 | ✓ | ✓ | ✓ | Yes | browser | **Verified** | — |

### B. Sport and physical activity

| Feature | Spec | DB | API | UI | Works | Status | Remaining |
|---|---|---|---|---|---|---|---|
| Record activity as a journal entry (category `activity`) | C §10 `journal_entries`, §14.1 Journal (MVP) | ✓ | 501 | ✗ | No | **Designed only → implemented on this branch** (see §4) | — |
| Structured activity log (type, intensity, steps, duration) | Not in C. `lifestyle_logs` (M1, data/AI dev); `docs/data` on `AI` | ✓ (+316 seed rows on live, simulated) | ✗ | ✗ | No | **Designed only; never agreed for the product (B22, D-11)** | Decision Q1 |
| Activity from a wearable (`source = device`) | `AI` `docs/data/DEVICE_INTEGRATION.md` | ✓ | ✗ | ✗ | No | **Proposed, never approved** | Device integration (none exists) |
| General activity guidance card | C §2, §4, §14.1 "Weekly guidance" ("if time") | ✗ | ✗ | ✗ | No | **Discussed, not implemented** | Sourced content + clinician review (Q3) |
| Exercise plan / prescription | C §2 rejects it ("medical advice") | — | — | — | — | **Out of scope by design** | — |
| Link between activity and BP trends | Nowhere specified | — | — | — | — | **Not specified** | Would need a clinical/product spec; must never trigger alerts |

### C. Nutrition / food system ("système alimentaire")

| Feature | Spec | DB | API | UI | Works | Status | Remaining |
|---|---|---|---|---|---|---|---|
| Food diary as journal entries (category `food`) | C §10, §14.1 (MVP) | ✓ | 501 | ✗ | No | **Designed only → implemented on this branch** | — |
| Structured meal log (meal type, description, sodium mg + basis) | Not in C; `lifestyle_logs` (M1) | ✓ | ✗ | ✗ | No | **Designed only; never agreed (B22, D-11)** | Decision Q1 |
| Dietary habits (bread portions/day, salt at table, salty processed food) | M6 (Algerian STEPS factors), applied live before review (B21) | ✓ | ✗ (B22) | ✗ | No | **Designed only; exposure undecided** | Decision Q2 |
| Ramadan fasting days | `lifestyle_logs.category = fasting` (M6) | ✓ | ✗ | ✗ | No | **Designed only** | Decision Q1 |
| General salt/food guidance card | C §2, §4 ("if time") | ✗ | ✗ | ✗ | No | **Discussed, not implemented** | Sourced content + clinician review (Q3) |
| Nutritional analysis, food database, personalised diet, AI nutrition advice | Nowhere; C §2 rejects personalised diet | — | — | — | — | **Out of scope** | — |

### D. Wearables and devices

| Feature | Spec | DB | API | UI | Works | Status | Remaining |
|---|---|---|---|---|---|---|---|
| Device list (simulated flagged) | D18 | ✓ | ✓ | ✓ | Yes | **Verified** (pytest, acceptance S7/S8, browser) | — |
| Wearable samples (HR, SpO2, HRV, skin temp), labelled, separate from BP | D18 | ✓ | ✓ | ✓ | Yes | **Verified** | — |
| Patient without wearable has a complete experience | brief | n/a | ✓ | ✓ | Yes | **Verified** (browser S7) | — |
| Device registration / real sync | C §2 (real device only if on hand) | ✓ | ✗ | ✗ | No | **Out of V1** (no device) | — |
| Ring flags, personal bands, weekly reports (ML) | `AI` M7 | ✓ | ✗ | ✗ | No | **Backend data only; deferred** (Ayoub, earlier instruction) | Endpoints + clinical review |
| Live early warnings (`live-v1`, M9) | `AI` `358ad4c` | ✓ **on live since ~22:00 UTC** | ✗ | ✗ | No | **Not approved by Ayoub** (see incident §10d) | Ayoub decision Q6 |
| R-RING-1 (ring SpO2 rule) | `AI` proposal | ✗ | ✗ | ✗ | No | **Proposed, disabled** | Clinician review |

### E. Clinical and doctor functionality

| Feature | Spec | DB | API | UI | Works | Status | Remaining |
|---|---|---|---|---|---|---|---|
| Assigned-patient list sorted by urgency | C §14.2 | ✓ | ✓ | ✓ | Yes | **Verified** | 15-s refresh (C §8.2) → this branch |
| Patient record (overview, readings incl. invalid, symptoms, alerts, wearable, estimate, notes, care plan) | C §14.2 | ✓ | ✓ | ✓ | Yes | **Verified** (browser, all tabs) | — |
| Doctor notes: private note + advice visible to patient | C §7.6, §12 | ✓ | ✓ | ✓ | Yes | **Verified** (pytest, acceptance, browser) | — |
| Care plan: doctor sets target | C §4, §14.2 (MVP) | ✓ | ✓ PUT | read only | Partial | **Backend implemented, frontend missing → this branch** | — |
| Incident (emergency event) report for doctor | C §7.6, §14.2 (MVP) | ✓ | ✓ | ✗ | No | **Backend implemented, frontend missing → this branch** | — |
| Journal review by doctor | C §14.2 (MVP) | ✓ | 501 | ✗ | No | **Designed only → this branch** | — |
| Stored ML estimate, doctor only, labelled | D7/D8, step 7 | ✓ | ✓ | ✓ | Yes (model_unavailable locally) | **Verified** | Model version decision (mbp-v1.1) |
| AI-drafted weekly summary for doctor | C §4, §13.3 ("if time") | `weekly_reports` (M7) | ✗ | ✗ | No | **Deferred** | Review + endpoint |
| Admin minimal view | — | n/a | `/me`, config | ✓ | Yes | **Implemented, not browser-verified** (no admin account) | — |

### F. Emergency workflow (C §7 — "core of the product")

| Feature | Spec | DB | API | UI | Works | Status | Remaining |
|---|---|---|---|---|---|---|---|
| Urgence button on every patient screen | C §7.3 | n/a | n/a | ✓ | Yes | **Verified** (browser, mobile) | — |
| Call button with configured number, demo mode | C §7.3, §7.4 | n/a | ✓ | ✓ | Yes | **Verified** | Number 14 unverified (D3) |
| FR + AR text | C §4 | n/a | ✓ | ✓ | Yes | **Verified** | — |
| Medical card for a bystander | C §7.3 (MVP) | ✓ | ✓ `/emergency-card` | ✗ | No | **Backend implemented, frontend missing → this branch** | — |
| Trusted contact call + "share my location" | C §7.3, §7.5 (MVP) | ✓ | ✓ (contacts, card) | ✗ | No | **Backend implemented, frontend missing → this branch** | — |
| Location with consent (8-s timeout, manual field) | C §7.5 (MVP) | ✓ | ✓ PATCH event | ✗ | No | **→ this branch** | HTTPS needed on phones |
| Incident record + action log (taps, never "sent") | C §7.6 (MVP) | ✓ | ✓ | ✗ | No | **Backend implemented, frontend missing → this branch** | — |
| Patient-reported outcome | C §7.3 (MVP) | ✓ | ✓ | ✗ | No | **→ this branch** | — |
| Works offline from local cache | C §4, §8.2 (MVP) | n/a | n/a | ✗ | No | **→ this branch (config + card cached)** | Queue of actions offline: partial |
| Lock-screen card image, Medical ID guide | C §7.2 ("if time, high") | — | — | ✗ | No | **Discussed, not implemented** | V2 |
| "Attract attention" sound | C §2 ("if time") | — | — | ✗ | No | **Discussed, not implemented** | V2 |
| Nearest emergency departments map link | C §4 ("if time") | — | — | ✗ | No | **Discussed, not implemented** | V2 |

### G. Other patient-facing modules

| Feature | Spec | DB | API | UI | Works | Status | Remaining |
|---|---|---|---|---|---|---|---|
| Login, role-based navigation, session refresh | C §4 | ✓ | ✓ | ✓ | Yes | **Verified** | Rate limiting (step 10) |
| Registration screen | C §4: none ("seeded accounts") | — | — | — | — | **Out of scope by design** (D-10) | Accounts are provisioned |
| Profile view | C §14.1 | ✓ | ✓ | ✓ | Yes | **Verified** | — |
| Profile editing, trusted contacts add/edit/remove | C §4 (MVP, "patient edits") | ✓ | ✓ | ✗ | No | **Backend implemented, frontend missing → this branch** | — |
| Journal « demander à mon médecin » | C §4, §14.1 (MVP) | ✓ | 501 | ✗ | No | **Designed only → this branch** | — |
| Doctor advice visible to patient | C §7.6 | ✓ | ✓ | ✓ | Yes | **Verified** | — |
| Medications list / adherence | C §10 ("as entered"), M1 tables | ✓ | ✗ | ✗ | No | **Designed only** | Decision Q4 (medication display needs care) |
| Body measurements (weight, waist) | M6 | ✓ | ✗ | ✗ | No | **Designed only** | Decision Q2 |
| Missing-reading reminder banner | C §4 ("if time") | — | — | ✗ | No | **Discussed, not implemented** | V2 |
| Education / weekly guidance cards | C §4, §14.1 ("if time") | — | — | ✗ | No | **Discussed, not implemented** | Q3 |
| Arabic UI throughout | C §4: out | — | — | — | — | **Out of scope by design** | — |
| Push/SMS notifications, dispatch, unconsciousness detection | C §4: out | — | — | — | — | **Out of scope by design** | Never implied |

---

## 2. Classification of missing functionality

| Class | Items |
|---|---|
| **Essential for V1** (specified as MVP in C, API/schema already agreed) | Emergency incident workflow in the UI (card, contact call/share, location, action log, outcome, offline cache); doctor incident report; journal (backend + patient + doctor review) — this is also where food and activity are recorded; profile + trusted-contact editing; doctor care-plan editing; doctor list refresh every 15 s |
| **Important, after the staging foundation** | Alert dismiss/escalated states and event timeline (contract change); symptom↔reading link (B24, migration); daily means; translation of alert texts to French (clinician review) |
| **V2** | Lock-screen card, Medical ID guide, attention sound, ED map link, reminder banner, AI weekly summary, weekly reports / flags / bands endpoints, device sync |
| **Needs Ayoub's decision or clinical review** | Q1–Q7 below |

## 3. Questions for Ayoub (blocking those items only)

| # | Question | Why it blocks |
|---|---|---|
| Q1 | Should V1 include **structured** lifestyle tracking (`lifestyle_logs`: activity type/intensity/steps/duration, meals with optional sodium, sleep, stress, fasting days), or is the journal (free text, categories `food`/`activity`) enough for V1? If yes: patient-entered only, shown to the doctor as context, never used by any rule or alert? | Never specified in C; D-11 kept it out of the UI; B22 open |
| Q2 | Expose the M6 profile fields (sex, smoking, condition codes, bread portions, salt at table, salty processed food) and body measurements in the profile? | B22; these were applied live before review (B21) |
| Q3 | Weekly general guidance cards (activity, salt, sleep): who writes the content, from which sources, and who signs it off clinically? | C requires "sourced, reviewed, labelled general"; no content exists |
| Q4 | Show medications ("as entered") and adherence? Display only, never advice? | Medication display is safety-sensitive (C §5 safety boundary) |
| Q5 | Alert "dismiss" (notice only) and the alert event timeline: add them to the contract? | Contract change; audit data is admin-readable (B30) |
| Q6 | M9 (`live_early_warning`) is now **applied on live** and **merged into `main`** via PR #4 (self-merged by the AI contributor). Keep, or revert in a new migration / new commit? Is `live-v1` part of V1? | You stated M9 is not approved; see incident §10d |
| Q7 | Staging: which Supabase organisation, may Claude create a project there (cost/plan), and where should staging API + frontend be hosted? | No staging exists; creating cloud resources needs your decision and access |

## 4. Recommended implementation order (what this branch does)

1. Journal: backend endpoints (GET/POST, doctor review) + tests + contract; patient journal screen (categories
   including **Alimentation** and **Activité physique**, « demander à mon médecin ») and doctor journal tab.
2. Emergency workflow completion on the existing API: incident record with action log (taps only), medical
   card from `/emergency-card`, trusted-contact call + share location (consent, 8-s timeout, manual field),
   outcome, offline cache of config and card.
3. Doctor incident report (list + report with readings around the event).
4. Profile + trusted-contact editing; doctor care-plan editing; doctor list refresh every 15 s.
5. Staging foundation (blocked on Q7; tooling and checklist prepared).
6. After decisions: Q1–Q5 items, then the V2 list.

## 5. Safety implications (unchanged rules)

- Journal, lifestyle and guidance content never feed the deterministic rules, alerts or emergency guidance.
- Food/activity entries are the patient's words; PULSE does not analyse them or give diet/exercise advice.
- Emergency actions are logged as attempts (`confirmed: false`); the UI never says a call was made, a message
  sent or help dispatched. Location is stored only with consent in the same request.
- ML (stored estimates, ring flags, M9 early warnings) stays doctor-only, advisory and out of the safety path.
