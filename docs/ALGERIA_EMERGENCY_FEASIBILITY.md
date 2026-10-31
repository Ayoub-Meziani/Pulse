# Emergency escalation in Algeria: feasibility (services, providers, platforms, law)

Date: 2026-10-31. Method: web research only. **No provider was contacted, no account was opened, no message
was sent and no emergency number was dialled or tested.**

Labels:
- **FACT**: stated by the named source. The source is official only where that is said.
- **CLAIM**: stated by a vendor or a third party, not verified.
- **ASSUMPTION**: my inference.
- **UNKNOWN**: not found.

## 1. Conclusions

1. **No automated channel to the Protection Civile was found.**
   - FACT (search): no public API, dispatch integration, data interface or SMS line for 14 or 1021 was found.
   - FACT: the official DGPC site lists WhatsApp and Facebook channels.
   - These are not a dispatch interface. Treat them as unsuitable for emergencies unless DGPC states otherwise.
   - The only supported path today is a **voice call by a person**: the patient, a trusted contact or the doctor.
   - PULSE must never send an SMS to 14 or 1021, and must never claim that emergency services were notified.
2. **The emergency numbers themselves are not verified from an official source.**
   - 14 and 1021 (Protection Civile) are consistent across secondary sources.
   - The medical numbers (SAMU 115? 16?) are contradictory across sources.
   - `verified: false` stays in `api/app/config.py` until checked by phone with DGPC or with an official
     publication.
3. **SMS to Algerian mobiles is feasible, but only through a contracted provider, and is not a reliable alarm.**
   - Delivery receipts depend on the provider and the operator.
   - Twilio does not support two-way SMS to Algeria and rejects generic sender IDs, especially on Mobilis.
   - Local aggregators need a contract, and some need a registered Algerian business.
   - Acknowledgement must use a web link, not an SMS reply.
4. **Voice calls to contacts are technically possible** (for example Twilio Voice, about $1.84/min to mobiles,
   per Twilio's rate page). They need a provider account, a caller ID policy, a recorded French/Arabic message
   and legal review.
5. **A loud alarm on a locked phone requires a native app.**
   - A web app/PWA can sound an alarm **only while it is open in the foreground**.
   - iOS web push is silent: it cannot play a custom sound or an alarm.
   - Android: a native app with an alarm-category notification channel and a full-screen intent is the realistic
     path. Since 2025, Google Play limits the full-screen intent permission to calling and alarm apps, and
     requires a declaration.
   - iOS: bypassing silent mode and Focus needs Apple's Critical Alerts entitlement, which Apple grants
     case by case and sometimes refuses.
   - Nothing should be promised until it has been tested on real devices.
6. **Hospitals:** no hospital API or integration was found (UNKNOWN). Any hospital notification needs a
   written agreement with a named facility, a verified on-call number, and a person who answers.
   PULSE must not hardcode hospital numbers.
7. **Law:**
   - Health data is sensitive data under Law 18-07, and its processing needs ANPDP authorization.
   - Transfers abroad (Supabase in Paris, Twilio in the US) need prior ANPDP authorization.
   - Real patients therefore require legal review first. The prototype uses fictional data only.

## 2. Algerian emergency services

| Service | Number / channel | Status | Source |
|---|---|---|---|
| Protection Civile (fire, rescue, ambulance) | 14, 1021 | **CLAIM** (consistent across secondary sources; not confirmed on an official page in this research) | [Wikipedia FR](https://fr.wikipedia.org/wiki/Protection_civile_en_Alg%C3%A9rie), [L'Écho d'Algérie](https://lechodalgerie.dz/la-protection-civile-rappelle-ses-numeros-durgence-1021-et-14mesures-preventives-renforcees-pour-proteger-les-citoyens-face-aux-fortes-chaleurs/), [Radio Algérie](https://news.radioalgerie.dz/fr/node/41764), [TSA](https://www.tsa-algerie.com/lalgerie-en-alerte-face-aux-intemperies-voici-les-numeros-a-contacter/) |
| Emergency calls while roaming | 14 and others via the three operators since 26 May 2025 | **CLAIM** (news) | [Just-Info DZ](https://just-infodz.com/itinerance-du-numero-durgence-en-algerie-le-service-officiellement-lance/) |
| DGPC digital channels | WhatsApp, Facebook (listed on the official site) | **FACT** (official site). Not an emergency dispatch interface (ASSUMPTION) | [dgpc.dz](https://dgpc.dz/en/home/) |
| Medical emergency (SAMU) | 115? 16? 14? | **Contradictory**: travel guides disagree | [Voyageurs du Monde](https://www.voyageursdumonde.fr/voyage-sur-mesure/voyages/guide-voyage/algerie/infos-pratiques/guide-de-voyage), [Gouvernement du Canada](https://voyage.gc.ca/assistance/ambassades-consulats/algerie), [visiearth](https://visiearth.pages.dev/dz/emergency-and-practical-essentials/) |
| Police / Gendarmerie | 1548 or 17 / 1055 | **CLAIM** (sources disagree on police) | [TSA](https://www.tsa-algerie.com/?p=287327), [ITU E.129](https://itu.int/net/itu-t/inrdb/e129_important_numbers.aspx) |
| SMS or text access to 14/1021 | None found | **UNKNOWN** (no source; France's 114 SMS line is unrelated) | — |
| API / CAD integration / location push (AML, eCall-like) | None found | **UNKNOWN** | [MHEWC Algeria](https://www.mhewc.org/algeria/) is about multi-hazard early warning, not individual dispatch |
| Third-party "SOS" apps | Unofficial apps exist | **FACT** that they exist; their affiliation with DGPC is not established | [Google Play `com.protection.civile`](https://play.google.com/store/apps/details?id=com.protection.civile&hl=en_US), [sos.dzairzone.com](https://sos.dzairzone.com/) |

**Safe fallback (current technology, no agreement needed):**
1. The patient's own call through a `tel:` link (existing emergency screen).
2. A trusted contact and the doctor are asked, in their notification, to call 14 with the shared location.
3. Every tap is recorded as "tapped, not confirmed".

**What an official integration would need (ASSUMPTION):**
- contact with DGPC (Direction Générale de la Protection Civile) and probably the Ministry of Health;
- a written agreement defining the channel, data format, location format, acknowledgement and liability;
- testing on a non-emergency test line provided by DGPC.

## 3. Provider comparison

| Provider | Service | Coverage | API | Location | Delivery confirmation | Cost | Authorization | Reliability |
|---|---|---|---|---|---|---|---|---|
| Protection Civile 14/1021 | Voice (human) | National (CLAIM) | **None** | Told verbally by the caller | The call is answered (human) | Free call | None to call; integration needs an agreement | Highest available; depends on the caller |
| [Twilio Programmable SMS](https://www.twilio.com/en-us/guidelines/dz/sms) | SMS to Algerian mobiles | Mobilis, Djezzy, Ooredoo (FACT, guideline page) | REST + delivery webhooks | Link in the text (needs location consent) | Delivery receipts where the operator returns them (UNKNOWN per operator); **two-way not supported** (FACT) | Not checked (see Twilio's DZ price page) | Account and KYC; numeric sender ID not fully supported; generic alphanumeric IDs rejected, especially Mobilis (FACT) | Sender-ID filtering is a delivery risk (third parties disagree: [SureSMS](https://suresms.com/en/country-rules/algeria/), [LINK Mobility](https://docs.linkmobility.com/regulatory-guidelines/sender-id/algeria), [Messente](https://support.messente.com/algeria-sms-regulations), [ClickSend](https://help.clicksend.com/en/articles/46389-algeria-213)) |
| [Twilio Programmable Voice](https://www.twilio.com/en-us/voice/pricing/dz) | Outbound calls with a recorded or TTS message | Algerian mobiles and landlines | REST + call status webhooks; keypress acknowledgement possible ("press 1") | Read out or sent by SMS | Answered / no answer / busy, plus optional keypress (FACT for the product in general; not tested to DZ) | **$1.8365/min to mobile, $0.1161/min local** (FACT, Twilio rate page, undated) | Account; caller ID rules for DZ UNKNOWN | UNKNOWN for DZ; must be tested |
| [BudgetSMS](https://www.budgetsms.net/sms-gateway-pricing/dz/algeria/) | SMS | DZ | HTTP API | Link | DLR (CLAIM) | ≈ €0.089 Djezzy, ≈ €0.17–0.18 Mobilis/Ooredoo (CLAIM) | Account | UNKNOWN |
| [BulkSMS](https://www.bulksms.com/countries/a/algeria), [EasySendSMS](https://www.easysendsms.com/gateway/Algeria), [Sent](https://www.sent.dm/resources/algeria-sms-pricing) | SMS | DZ (CLAIM) | HTTP API | Link | DLR (CLAIM) | Per message (CLAIM) | Account | UNKNOWN |
| Local aggregators ([bar9](https://bar9.dev/), [Sobersys](https://sobersys.com/en/), [Hostraha](https://www.hostraha.com/bulk-sms)) | SMS, sometimes local sender IDs | DZ | HTTP API (CLAIM) | Link | DLR (CLAIM) | Quote | bar9 requires a registered Algerian business (CLAIM); operators do not publish APIs, so access comes through contracts ([note](https://packagist.org/packages/djouamaah/laravel-algeria-sms)) | Probably better local delivery (ASSUMPTION) |
| Mobile operators direct (Mobilis, Djezzy, Ooredoo) | Business SMS / short code | Own network | Contract only | Link | Contract-defined | Quote | Business contract | UNKNOWN |
| Firebase Cloud Messaging | Push to the Android native app (and web push in Chrome) | Worldwide (needs Google Play services) | REST (HTTP v1) | In-app | "Sent" from FCM; delivery is not guaranteed. High priority wakes the app during Doze maintenance windows ([Android docs](https://developer.android.com/training/monitoring-device-state/doze-standby)) | Free | Google account and app | Good, not guaranteed; OEM battery killers reduce it |
| Apple Push (APNs) | Push to the iOS native app; Critical Alerts with an entitlement | Worldwide | HTTP/2 | In-app | No delivery receipt | Free (Apple developer account $99/year) | Critical Alerts entitlement is decided by Apple ([forum](https://developer.apple.com/forums/thread/794822), [guide](https://newly.app/articles/critical-alerts-entitlement)) | Good; critical-alert approval is uncertain |
| Web Push (VAPID) | Push to the PWA | Chrome/Firefox/Edge; iOS 16.4+ only when installed to the home screen | Standard | In-app | None | Free | None | Lowest for alarms: iOS silent, Android throttled |
| WhatsApp Business Platform | Template messages | Popular in DZ (ASSUMPTION) | Cloud API | Location message | Sent/delivered/read webhooks | Per conversation (not checked) | Meta business verification; template approval | Not an emergency channel; possible for contacts (to evaluate) |

**Costs are indicative**. Before any decision, get written quotes in DZD/EUR, including sender-ID registration and
monthly minimums.

## 4. Local alarm: web/PWA versus native app

| Capability | Web app / PWA | Native Android | Native iOS |
|---|---|---|---|
| Loud sound while the app is open | Yes (Web Audio after a user tap; vibration on Android; Screen Wake Lock) | Yes | Yes |
| Sound when the app is closed or the phone is locked | **No.** Web push uses the default notification sound; [iOS web push cannot play a custom sound](https://intercom.help/progressier/en/articles/6753668-is-it-possible-for-a-pwa-to-play-a-sound-upon-receiving-a-push-notification) ([Apple forum](https://developer.apple.com/forums/thread/778080), [MagicBell](https://www.magicbell.com/blog/pwa-ios-limitations-safari-support-complete-guide)) | Yes: notification channel with alarm audio attributes, `setAlarmClock()` for scheduled re-alarms (the system leaves Doze just before it fires) | Only a standard notification sound (≤ 30 s), unless Critical Alerts are granted |
| Full-screen over the lock screen | No | Full-screen intent. **Since 22 Jan 2025 Google Play grants `USE_FULL_SCREEN_INTENT` by default only to calling and alarm apps**, so PULSE needs a Play declaration ([Play policy](https://support.google.com/googleplay/android-developer/answer/13392821), [AOSP](https://source.android.com/docs/core/permissions/fsi-limits)) | No full-screen for third-party apps (ASSUMPTION; CallKit is for VoIP calls and is not allowed for alarms) |
| Do Not Disturb / silent mode | No | Alarm-usage audio usually plays under DND when "alarms" are allowed, which is the user's setting. Channel DND bypass needs notification-policy access granted by the user ([API notes](https://learn.microsoft.com/en-us/dotnet/api/android.app.notificationchannel.setbypassdnd?view=net-android-37.0)). **To test per device** | Only with Critical Alerts (entitlement plus the user's opt-in) |
| Background reliability | Throttled ([note](https://byacraft.pages.dev/notes/notification-architecture)) | FCM high priority + foreground service. OEM battery optimisation (Xiaomi, Oppo, etc.) can delay alarms; the user may need to exempt the app | APNs; generally reliable |
| Effort | Already in place (emergency screen) | New app (Kotlin, or a wrapper such as Capacitor with native plugins), Play listing, declaration | New app, Apple developer account, entitlement request |

**Recommendation:**
- **Phase 1 (current technology):** an in-app alarm while the app is open, plus web push for doctors' browsers.
  It must be labelled honestly: "the alarm sounds only while PULSE is open".
- **Phase 2:** an Android native shell (most Algerian phones run Android, per ASSUMPTION; to verify) with an
  alarm channel and FCM, tested on at least 3 brands. Submit the Play full-screen-intent declaration.
- **Phase 3:** iOS, after a Critical Alerts entitlement request with a clinical justification.

## 5. Hospital and doctor notification

| Target | Current technology | Needs |
|---|---|---|
| Assigned doctor (in the app) | Yes: in-app list plus web push to the doctor's browser; acknowledgement by button | Nothing external |
| Assigned doctor (phone) | No | SMS or voice provider (§3), the doctor's verified number and consent |
| "Associated hospital" | No | A named facility, a **verified** on-call number entered by an admin with a recorded source, a written agreement saying someone will answer and act, and a test procedure. No hospital API was found (UNKNOWN) |

## 6. Legal and privacy (Algeria)

- **FACT (law firm notes):**
  - Law 18-07 treats health data as sensitive. Processing it needs prior authorization from the ANPDP rather than
    a declaration.
  - Transfers of personal data abroad need prior ANPDP authorization, except for listed exceptions.
  - Penalties include fines and imprisonment.
  - Sources: [Gide 2023 alert](https://www.gide.com/sites/default/files/2023-07gide_alerteclient_anpdp_fr_7.pdf),
    [Gide analysis](https://www.gide.com/en/news-insights/protection-of-personal-data-focus-on-algerian-regulations/),
    [LPA note 2018](https://www.lpalaw.com/wp-content/uploads/2018/07/Smart-News-Algérie-Juillet-2018.pdf).
- **CLAIM:** Law 18-07 was amended by Law 25-11 ([Zoom Algérie](https://zoomalgerie.com/loi-18-07-protection-donnees-algerie/),
  [TSA](https://www.tsa-algerie.com/donnees-personnelles-lalgerie-modifie-sa-legislation-ce-qui-va-changer/)).
  The details were not verified: read the official text in the Journal officiel.
- **Impact on PULSE (ASSUMPTION, needs a lawyer):**
  - Production hosting in Paris and any US provider (Twilio, Firebase) are transfers abroad.
  - Sending a patient's location and condition to a trusted contact is processing of sensitive data. It needs
    the patient's explicit consent and the contact's consent to receive it.
  - Recording call outcomes and timelines is also processing.
  - Until legal review and ANPDP steps are done, PULSE stays on fictional data.

## 7. What is doable, by dependency

| Capability | Current tech | External provider | Official agreement | Native app |
|---|---|---|---|---|
| Escalation engine, state machine, timeline, idempotency, cancellation (server) | ✓ | | | |
| In-app alarm while the app is open | ✓ | | | |
| Doctor in-app notification and acknowledgement; web push to the doctor's browser | ✓ (web push is free) | | | |
| Trusted-contact acknowledgement page (tokenized link) | ✓ | (the SMS to deliver the link) | | |
| SMS to contacts or the doctor | | ✓ (contract, sender ID) | | |
| Voice calls to contacts | | ✓ | | |
| Contact phone verification (OTP) | | ✓ (SMS) | | |
| Lock-screen loud alarm, DND behaviour | | (FCM/APNs, free) | | ✓ (+ Play declaration / Apple entitlement) |
| Hospital on-call notification | | ✓ (SMS/voice) | ✓ (facility) | |
| Automatic request to Protection Civile | | | ✓ (DGPC; no channel exists) | |
| Legal basis for real patients | | | ✓ (ANPDP authorization, lawyer) | |

## 8. Other sources consulted

- Android Doze and high-priority FCM: <https://developer.android.com/training/monitoring-device-state/doze-standby>.
- Third-party voice rates (lower than Twilio, CLAIM): <https://autocalls.ai/country/algeria>, <https://docs.zernio.com/pricing/calls>.
- iOS Critical Alerts experiences: <https://jhan.bearblog.dev/i-cant-understand-apples-critical-alert-policy/>,
  <https://developer.apple.com/forums/thread/792320>, <https://github.com/nightscout/Trio/issues/998>.
- Supabase pricing: see `docs/STAGING_SETUP.md` §2.
