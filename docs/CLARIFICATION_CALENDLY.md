# Clarification Call → Calendly Integration — Implementation Plan

## Context & Current Flow

After the coach confirms that the intro call went well, the participant receives an email asking for their confirmation. That email currently presents two token-based links:

1. **"Coaching kann starten"** → `response_participant/<start_coaching_token>/` → transitions `MatchingAttempt` to `MATCHING_COMPLETED`
2. **"Ich habe Klärungsbedarf"** → `response_participant/<clarification_needed_token>/` → transitions state to `CLARIFICATION_WITH_PARTICIPANT_NEEDED`, sends Slack/email escalation to BL contact, notifies coach

**Goal:** Replace option 2 with a direct Calendly booking link. The system records only the actual booking (confirmed via Calendly webhook) — no click tracking.

---

## How to Link the Booking Back to a MatchingAttempt

Two realistic options exist:

### Option A — UTM parameter ✅ Recommended
Append `?utm_campaign=matching-{id}` to the Calendly URL in the email. Calendly preserves UTM parameters through its booking flow and includes them in the webhook payload under `payload.tracking.utm_campaign`.

**Pros:** Zero Calendly configuration required. No API calls. The `tracking` object is purpose-built for this. Works with one shared event type URL.

**Cons:** The matching attempt ID is visible in the URL (not a security concern — it's validated server-side and not secret).

### Option B — Custom question pre-fill
Add a custom question (e.g. "Matching-ID") to the Calendly event type, then pre-fill it via `?a1={id}` in the URL. The answer appears in `questions_and_answers` in the webhook payload.

**Pros:** Data ends up in a named field in the payload.

**Cons:** Requires editing the Calendly event configuration. The pre-filled field is visible to the participant and can be edited. Question ordering in the Calendly UI can shift, breaking `a1` indexing. More fragile overall.

**→ Use Option A (UTM campaign).** It requires no Calendly setup, is reliable, and is exactly what the `tracking` field is designed for.

---

## Architecture Decisions

| Concern | Decision |
|---|---|
| **Linking booking to MatchingAttempt** | Primary: `utm_campaign=matching-{matching_attempt.id}` appended to the Calendly URL. Webhook parses `tracking.utm_campaign`. Fallback: participant email lookup when UTM is absent (e.g. staff test booking). |
| **Click tracking** | Not tracked. Only the actual booking (webhook-confirmed) is recorded. |
| **Booking model** | New `ClarificationCallBooking` model in `matching/` (separate from intake `CalendlyBooking` in `bookings/`). |
| **State machine** | One new state: `CLARIFICATION_CALL_SCHEDULED` (booking confirmed via webhook). |
| **Replacing old clarification path** | `CLARIFICATION_NEEDED` token type removed entirely. The email now embeds the Calendly URL directly — no token needed for the Calendly link. |
| **Calendly link** | `https://calendly.com/beginnerluft/check-in?utm_campaign=matching-{matching_attempt.id}` |
| **Webhook event-type discrimination** | `payload.scheduled_event.name`: `"Check In"` → clarification call; `"BeginnerLuft Erstgespräch"` → intake flow. UTM is not reliable for detection (both real payloads show `utm_campaign: null` on direct Calendly bookings). |

---

## Flow Diagram (New)

```
Participant receives email
         │
         ├── [Coaching kann starten] ──────────────────────────→ MATCHING_COMPLETED (token-based, unchanged)
         │
         └── [Ich möchte zuerst mit euch sprechen]
                  │  (direct Calendly link — no token, no redirect)
                  ▼
         https://calendly.com/beginnerluft/check-in?utm_campaign=matching-{id}
                  │
                  ▼
         Participant books (or doesn't — no action taken if they don't)
                  │
        ──────────────────────────────
        │                            │
  [Books call]               [Cancels booking]
        │                            │
        ▼                            ▼
  Calendly webhook          Calendly webhook
  (invitee.created)         (invitee.canceled)
        │                            │
        ├── Create ClarificationCallBooking     ├── Update status → "canceled"
        ├── Record CLARIFICATION_CALL_BOOKED    ├── Record CLARIFICATION_CALL_CANCELED
        └── FSM → CLARIFICATION_CALL_SCHEDULED  └── FSM ← back to AWAITING_INTRO_CALL_FEEDBACK_FROM_PARTICIPANT
                      │                              (participant can rebook or click "Coaching kann starten" again)
                      │
                      ├── [Participant clicks "Coaching kann starten" token]
                      │         └── FSM → MATCHING_COMPLETED (complete_matching accepts this source)
                      │
                      └── [Clarification call takes place → staff takes manual action, TBD]
```

---

## Phase 1 — ClarificationCallBooking Model

- [x] In `matching/models.py`, add `ClarificationCallBooking` before `MatchingEvent`:
  ```python
  class ClarificationCallBooking(models.Model):
      matching_attempt = models.ForeignKey(
          MatchingAttempt,
          on_delete=models.CASCADE,
          related_name="clarification_call_bookings",
      )
      calendly_event_uri = models.URLField(blank=True)
      calendly_invitee_uri = models.URLField(blank=True, unique=True)  # unique: idempotent on webhook re-delivery
      invitee_email = models.EmailField(blank=True)
      start_time = models.DateTimeField(null=True, blank=True)
      status = models.CharField(max_length=50, default="active")  # active | canceled
      # Parsed from Calendly questions_and_answers (Frage 1 + Frage 2)
      clarification_category = models.CharField(max_length=255, blank=True)  # e.g. "Ich habe das Gefühl, es hat nicht ganz..." / "Organisatorisches"
      clarification_description = models.TextField(blank=True)  # free-text answer to Frage 2
      raw_payload = models.JSONField(default=dict, blank=True)
      created_at = models.DateTimeField(auto_now_add=True)
      updated_at = models.DateTimeField(auto_now=True)

      class Meta:
          verbose_name = "Klärungsgespräch-Buchung"
          verbose_name_plural = "Klärungsgespräch-Buchungen"
          ordering = ["-created_at"]
  ```
  > `ForeignKey` (not OneToOne) so each booking/cancellation/rebooking creates its own record — the full history is preserved. `calendly_invitee_uri` is `unique=True` to make webhook re-delivery idempotent.
- [x] Generate migration: `python manage.py makemigrations matching`
- [x] Register in `matching/admin.py`:
  - `list_display`: `matching_attempt`, `invitee_email`, `start_time`, `status`, `clarification_category`, `created_at`
  - `list_filter`: `status`
  - `readonly_fields`: `raw_payload`, `created_at`, `updated_at`
  - Add `raw_id_fields = ("matching_attempt",)` for usability

---

## Phase 2 — Token & Email Function Cleanup

The Calendly link no longer needs a token — it's a plain URL embedded directly in the email.

- [x] In `matching/tokens.py`, **remove** `CLARIFICATION_NEEDED` from `ParticipantActionToken.Action` (no backward compat needed)
- [x] In `matching/tokens.py`, update `generate_start_coaching_and_clarification_needed_urls()`:
  - Only generate one token: `START_COACHING`
  - Construct the Calendly URL with pre-filled invitee data and UTM tracking:
    ```python
    from urllib.parse import urlencode
    participant = matching_attempt.participant
    params = urlencode({
        "utm_campaign": f"matching-{matching_attempt.id}",
        "name": f"{participant.first_name} {participant.last_name}".strip(),
        "email": participant.email,
    })
    calendly_url = f"{settings.CALENDLY_CHECKIN_URL}?{params}"
    ```
  - Return `(start_coaching_url, calendly_url)` — callers unpack by position so the signature stays compatible
  - Rename the function to `generate_participant_response_urls()` for clarity
- [x] Update the import in `emails/services.py` (line 17): replace `generate_start_coaching_and_clarification_needed_urls` with `generate_participant_response_urls`
- [x] Rename the unpacked variable on the call site in `emails/services.py` from `clarification_needed_url` → `calendly_url` (the context dict key will also change — see Phase 4)
- [x] Add `CALENDLY_CHECKIN_URL = "https://calendly.com/beginnerluft/check-in"` to `settings.py` (keeps the URL out of code)
  > **Note:** Calendly pre-fills `name` and `email` from the URL parameters automatically. The participant can still edit the fields if needed. The `name` parameter accepts a full name string; Calendly splits it into first/last on its side.

---

## Phase 3 — FSM & EventType Additions

### 3a — New State

- [x] In `MatchingAttempt.State`, add:
  ```python
  CLARIFICATION_CALL_SCHEDULED = "clarification_call_scheduled", "Klärungsgespräch gebucht"
  ```

- [x] Add `CLARIFICATION_CALL_SCHEDULED` to `MatchingAttempt.ACTIVESTATES`. Without this, `is_active` returns `False` for matching attempts awaiting a clarification call, breaking admin filters and automation guards.

- [x] Add two new FSM transitions to `MatchingAttempt`:
  ```python
  @transition(field=state,
              source=State.AWAITING_INTRO_CALL_FEEDBACK_FROM_PARTICIPANT,
              target=State.CLARIFICATION_CALL_SCHEDULED)
  def confirm_clarification_call_booking(self):
      """Calendly webhook confirmed a clarification call booking."""
      pass

  @transition(field=state,
              source=State.CLARIFICATION_CALL_SCHEDULED,
              target=State.AWAITING_INTRO_CALL_FEEDBACK_FROM_PARTICIPANT)
  def cancel_clarification_call_booking(self):
      """Calendly webhook reported a booking cancellation — revert so the participant can rebook or click 'Coaching kann starten'."""
      pass
  ```

- [x] Expand the existing `complete_matching()` transition to also accept `CLARIFICATION_CALL_SCHEDULED` as a source:
  ```python
  @transition(field=state,
              source=[State.AWAITING_INTRO_CALL_FEEDBACK_FROM_PARTICIPANT,
                      State.CLARIFICATION_CALL_SCHEDULED],
              target=State.MATCHING_COMPLETED)
  def complete_matching(self):
      pass
  ```
  > **Why:** the participant's "Coaching kann starten" token remains valid even after the matching attempt moves to `CLARIFICATION_CALL_SCHEDULED` (e.g. they book a call but then decide they don't need it). When they click that token, `handle_coaching_can_start_feedback_received_from_participant_event` calls `complete_matching()`. Without this source expansion, that call raises `TransitionNotAllowed`.

### 3b — New EventTypes

- [x] In `MatchingEvent.EventType`, add under section 4 (Intro Call Process):
  ```python
  # Clarification call via Calendly (replaces old CLARIFICATION_NEEDED token flow)
  CLARIFICATION_CALL_BOOKED = "clarification_call_booked", "TN hat Klärungsgespräch gebucht (Calendly)"
  CLARIFICATION_CALL_CANCELED = "clarification_call_canceled", "TN hat Klärungsgespräch abgesagt (Calendly)"
  ```

- [x] Generate migration: `python manage.py makemigrations matching`

---

## Phase 4 — Email Update

The participant feedback email lives in `emails/services.py` (`send_feedback_request_email_after_intro_call_to_participant()`). It calls the token helper which already returns two URLs — after Phase 2 the second URL is the Calendly link.

- [x] Find the email template used by this function and confirm the variable name for the second CTA URL
- [x] In `emails/services.py`, update the context dict: rename `"clarification_needed_url": clarification_needed_url` → `"calendly_url": calendly_url`
- [x] In the email template `emails/intro_call_feedback_request_to_participant.html`, rename `{{ clarification_needed_url }}` → `{{ calendly_url }}`
- [x] Update the CTA button copy for option 2:
  - Old: *"Ich habe Klärungsbedarf"* (implied one-click action)
  - New: *"Ich möchte zuerst ein kurzes Gespräch mit euch führen"* (makes clear they are booking a call)
- [x] Update surrounding text to clarify the participant lands on a Calendly booking page, not a confirmation form

---

## Phase 5 — Calendly Webhook Setup & Extension

### 5a — Register the Webhook in Calendly

Both the intake booking and the clarification call share the same webhook endpoint (`POST /bookings/calendly-webhook/`). The clarification call Calendly event type just needs to be added to the same subscription.

- [ ] In Calendly → **Account settings → Developer → Webhooks → Create new webhook subscription:**
  - **Webhook URL:** `https://{SITE_URL}/bookings/calendly-webhook/` (same endpoint as the intake webhook)
  - **Events:** `invitee.created`, `invitee.canceled`
  - **Scope:** select the clarification call event type (`beginnerluft/check-in`)
  - **Signing key:** copy the signing key shown by Calendly → set `CALENDLY_SIGNING_KEY` in production `.env` (if you use a different signing key per subscription, update the setting accordingly)
  - Note: if the same signing key is used for both subscriptions, no `.env` change is needed — the single key covers both

### 5b — Event-type discrimination & staging test detection

**Why `scheduled_event.name`, not UTM:** Both real payloads (intake and Check In) show `utm_campaign: null`. UTM is null whenever someone books directly in Calendly without following the email link (e.g. staff testing). `scheduled_event.name` is determined by Calendly's event type configuration and is always reliably present.

**Confirmed event type names (from real payloads):**
- Intake: `"BeginnerLuft Erstgespräch"`
- Clarification call: `"Check In"`

**Staging test detection for clarification calls:** Use the free-text description field. Real question label has a trailing space (`"Bitte beschreibe dein Anliegen kurz: "`), so match via `startswith` rather than exact equality.

- [x] In `bookings/views.py`, rework the `is_test_event` detection to run **before** routing, and handle both event types:
  ```python
  _scheduled_event_name = (scheduled_event.get("name") or "").strip()
  _is_clarification_call = _scheduled_event_name == "Check In"

  if _is_clarification_call:
      # For Check In events, detect test bookings via the free-text description field.
      # The real question label has a trailing space, so use startswith matching.
      _qa_list = invitee_data.get("questions_and_answers") or []
      _description_answer = next(
          ((qa.get("answer") or "") for qa in _qa_list
           if (qa.get("question") or "").strip().lower().startswith("bitte beschreibe")),
          "",
      )
      is_test_event = _description_answer.strip()[:4].lower() == "test"
  else:
      # Existing intake event test detection (unchanged)
      _TEST_QUESTION = "Hier kannst du uns dein Anliegen mitteilen:"
      _qa_list = invitee_data.get("questions_and_answers") or []
      _anliegen_answer = next(
          ((qa.get("answer") or "") for qa in _qa_list
           if (qa.get("question") or "").strip() == _TEST_QUESTION),
          "",
      )
      is_test_event = _anliegen_answer.strip()[:4].lower() == "test"
  ```
  > This replaces the current single-block `_TEST_QUESTION` / `_anliegen_answer` extraction. The staging/production filter logic that follows (`if environment == "production" and is_test_event: ...` etc.) is unchanged.

### 5c — Route Clarification Call Events Inside Existing Blocks

**Important:** The existing `invitee.created` and `invitee.canceled` blocks each end with `return HttpResponse(status=200)`. The clarification call routing must go **inside** these blocks (before the `return`), not after them — code placed after the return is unreachable.

- [x] Extract the MatchingAttempt lookup key just before the event routing blocks:
  ```python
  _tracking = (invitee_data.get("tracking") or {})
  _utm_campaign = (_tracking.get("utm_campaign") or "").strip()
  # Primary: parse matching attempt ID from UTM (present when participant clicks email link).
  # Fallback: invitee email (used when UTM is absent, e.g. staff test booking directly in Calendly).
  _clarification_matching_id = _utm_campaign.removeprefix("matching-") if _utm_campaign.startswith("matching-") else None
  _clarification_invitee_email = (invitee_data.get("email") or "").strip()
  ```

- [x] Modify the `invitee.created` block to delegate to the matching service for Check In events:
  ```python
  if event == "invitee.created":
      if _is_clarification_call:
          from matching.services import record_clarification_call_booked
          try:
              record_clarification_call_booked(
                  matching_attempt_id=_clarification_matching_id,
                  invitee_email=_clarification_invitee_email,
                  invitee_data=invitee_data,
                  scheduled_event=scheduled_event,
                  raw_payload=payload,
              )
          except Exception:
              logger.exception(
                  "Error recording clarification call booking — matching_id=%s email=%s",
                  _clarification_matching_id, _clarification_invitee_email,
              )
              return JsonResponse({"detail": "Error recording clarification call booking"}, status=500)
          return HttpResponse(status=200)

      # --- Existing intake booking path (unchanged) ---
      ...
      return HttpResponse(status=200)
  ```

- [x] Modify the `invitee.canceled` block the same way:
  ```python
  if event == "invitee.canceled":
      if _is_clarification_call:
          from matching.services import record_clarification_call_canceled
          try:
              record_clarification_call_canceled(
                  matching_attempt_id=_clarification_matching_id,
                  invitee_email=_clarification_invitee_email,
                  invitee_data=invitee_data,
                  raw_payload=payload,
              )
          except Exception:
              logger.exception(
                  "Error recording clarification call cancellation — matching_id=%s email=%s",
                  _clarification_matching_id, _clarification_invitee_email,
              )
              return JsonResponse({"detail": "Error recording clarification call cancellation"}, status=500)
          return HttpResponse(status=200)

      # --- Existing intake cancellation path (unchanged) ---
      ...
  ```

### 5d — Service Functions in `matching/services.py`

- [x] Add a helper to extract Q&A answers by question label:
  ```python
  def _extract_calendly_answer(questions_and_answers, labels):
      """Find an answer by matching question text against a list of possible labels (case-insensitive)."""
      normalised = [l.strip().lower() for l in labels]
      for item in questions_and_answers:
          if (item.get("question") or "").strip().lower() in normalised:
              return (item.get("answer") or "").strip()
      return ""
  ```

- [x] Add `_resolve_matching_attempt_for_clarification_call()` helper to centralise ID/email lookup:
  ```python
  def _resolve_matching_attempt_for_clarification_call(matching_attempt_id, invitee_email):
      """Resolve a MatchingAttempt for a clarification call webhook event.

      Primary: matching_attempt_id from UTM (present when participant clicks email link).
      Fallback: participant email lookup (when UTM is absent, e.g. staff test booking directly in Calendly).
      Returns the MatchingAttempt or None (after logging a warning).
      """
      if matching_attempt_id:
          try:
              return MatchingAttempt.objects.get(id=matching_attempt_id)
          except (MatchingAttempt.DoesNotExist, ValueError):
              logger.warning("Calendly clarification webhook: no MatchingAttempt found for id=%s", matching_attempt_id)
              return None
      # Fallback: find by invitee email in an eligible state
      ELIGIBLE_STATES = [
          MatchingAttempt.State.AWAITING_INTRO_CALL_FEEDBACK_FROM_PARTICIPANT,
          MatchingAttempt.State.CLARIFICATION_CALL_SCHEDULED,
      ]
      attempt = (
          MatchingAttempt.objects
          .filter(participant__email=invitee_email, state__in=ELIGIBLE_STATES)
          .order_by("-created_at")
          .first()
      )
      if attempt is None:
          logger.warning(
              "Calendly clarification webhook: no eligible MatchingAttempt found by email=%s", invitee_email
          )
      return attempt
  ```

- [x] Add `record_clarification_call_booked()`:
  ```python
  def record_clarification_call_booked(matching_attempt_id, invitee_email, invitee_data, scheduled_event, raw_payload):
      matching_attempt = _resolve_matching_attempt_for_clarification_call(matching_attempt_id, invitee_email)
      if matching_attempt is None:
          return

      qna = invitee_data.get("questions_and_answers") or []
      # Category question: exact label from real payload — no trailing space.
      # Description question: real label has trailing space ("Bitte beschreibe dein Anliegen kurz: "),
      # so list both variants to be safe.
      category = _extract_calendly_answer(qna, ["Was ist dein Anliegen für diesen Termin?"])
      description = _extract_calendly_answer(qna, ["Bitte beschreibe dein Anliegen kurz:", "Bitte beschreibe dein Anliegen kurz: "])
      invitee_uri = invitee_data.get("uri", "")

      with transaction.atomic():
          matching_attempt = _get_locked_matching_attempt(matching_attempt)
          # Keyed on calendly_invitee_uri — idempotent if Calendly re-delivers the same event.
          # Each distinct booking (new invitee_uri) creates a new record, preserving history.
          ClarificationCallBooking.objects.update_or_create(
              calendly_invitee_uri=invitee_uri,
              defaults={
                  "matching_attempt": matching_attempt,
                  "calendly_event_uri": scheduled_event.get("uri", ""),
                  "invitee_email": invitee_data.get("email", ""),
                  "start_time": parse_datetime(scheduled_event.get("start_time")),
                  "status": "active",
                  "clarification_category": category,
                  "clarification_description": description,
                  "raw_payload": raw_payload,
              },
          )
          if matching_attempt.state == MatchingAttempt.State.AWAITING_INTRO_CALL_FEEDBACK_FROM_PARTICIPANT:
              matching_attempt.confirm_clarification_call_booking()
              matching_attempt.save()
          create_matching_event(
              matching_attempt=matching_attempt,
              event_type=MatchingEvent.EventType.CLARIFICATION_CALL_BOOKED,
          )
  ```

- [x] Add `record_clarification_call_canceled()`:
  ```python
  def record_clarification_call_canceled(matching_attempt_id, invitee_email, invitee_data, raw_payload):
      matching_attempt = _resolve_matching_attempt_for_clarification_call(matching_attempt_id, invitee_email)
      if matching_attempt is None:
          return

      invitee_uri = invitee_data.get("uri", "")

      with transaction.atomic():
          matching_attempt = _get_locked_matching_attempt(matching_attempt)
          # Cancel only the specific booking that was canceled, matched by invitee URI.
          ClarificationCallBooking.objects.filter(
              calendly_invitee_uri=invitee_uri
          ).update(status="canceled")
          if matching_attempt.state == MatchingAttempt.State.CLARIFICATION_CALL_SCHEDULED:
              matching_attempt.cancel_clarification_call_booking()
              matching_attempt.save()
          create_matching_event(
              matching_attempt=matching_attempt,
              event_type=MatchingEvent.EventType.CLARIFICATION_CALL_CANCELED,
          )
  ```
  > Note: reverting the state to `AWAITING_INTRO_CALL_FEEDBACK_FROM_PARTICIPANT` means the participant's existing "Coaching kann starten" token in their email inbox becomes valid again, and the Calendly link is also still in that email so they can rebook.

---

## Phase 6 — Notifications for Booking Confirmed

The coach notification must respect `coach.preferred_communication_channel` — identical to the pattern used throughout `notification_handlers.py`. Staff (BL contact) are always notified via Slack (email fallback only if Slack fails, same pattern as `handle_escalation_notification_sent_to_staff_event`).

### 6a — Slack functions (`slack/services.py`)

- [x] Add `send_clarification_call_booked_info_to_staff_slack(matching_attempt)`:
  - Recipient: `bl_contact` (via `bl_contact.slack_user_id`)
  - Content:
    - Header: `📅 {participant} hat ein Klärungsgespräch gebucht`
    - Section: booking date/time from the most recent active booking (`matching_attempt.clarification_call_bookings.filter(status="active").order_by("-created_at").first()`)
    - Section: participant's answers (`clarification_category` + `clarification_description`) if present
    - Section: link to participant profile
  - Follow same try/except + `create_slack_log` pattern as all other functions in this file

- [x] Add `send_clarification_call_booked_info_to_coach_slack(matching_attempt)`:
  - Recipient: coach (via `coach.slack_user_id`)
  - Content:
    - Header: `ℹ️ Kurzes Update zum Coaching mit {participant.first_name}`
    - Section: participant has booked a short check-in call to clarify a few things; BL staff will handle it; coach needs to do nothing for now
    - Tone: calm, brief, reassuring
  - Follow same try/except + `create_slack_log` pattern

### 6b — Email functions (`emails/services.py` + template)

- [x] Add email template `emails/clarification_call_booked_info_to_coach.html`:
  - Adapts the tone/content of the Slack message above into an email
  - Inform coach that participant booked a short check-in call; BL will handle it; nothing to do for now
  - Reuse base template (`{% extends "emails/base_email.html" %}`)

- [x] Add `send_clarification_call_booked_info_to_coach_email(matching_attempt, triggered_by="system")` to `emails/services.py`:
  - Follow same `@transaction.atomic` + `_get_locked_matching_attempt` + `transaction.on_commit(lambda: send_email(...))` pattern as adjacent functions
  - Template: `emails/clarification_call_booked_info_to_coach.html`
  - Subject: `ℹ️ Kurzes Update: {participant.first_name} hat ein Klärungsgespräch gebucht`

---

## Phase 7 — Event Handlers & Dispatcher

- [x] In `matching/handlers/notification_handlers.py`, add:
  ```python
  def handle_clarification_call_booked_event(event):
      from matching.models import MatchingEvent
      if event.event_type != MatchingEvent.EventType.CLARIFICATION_CALL_BOOKED:
          return
      matching_attempt = event.matching_attempt
      coach = matching_attempt.matched_coach
      # Staff: always Slack first, email fallback
      try:
          send_clarification_call_booked_info_to_staff_slack(matching_attempt)
      except Exception:
          logger.warning("Failed to send clarification call booked Slack to staff for MA %s — falling back to email", matching_attempt.id, exc_info=True)
          send_escalation_info_email_to_staff(matching_attempt)  # generic fallback (reuse existing)
      # Coach: respect preferred_communication_channel
      if coach.preferred_communication_channel == Coach.CommunicationChannel.SLACK:
          send_clarification_call_booked_info_to_coach_slack(matching_attempt)
      elif coach.preferred_communication_channel == Coach.CommunicationChannel.EMAIL:
          send_clarification_call_booked_info_to_coach_email(matching_attempt)
      else:
          raise ValueError(f"Unsupported communication channel for coach {coach}: {coach.preferred_communication_channel}")

  def handle_clarification_call_canceled_event(event):
      from matching.models import MatchingEvent
      if event.event_type != MatchingEvent.EventType.CLARIFICATION_CALL_CANCELED:
          return
      # No automated notification — staff see this in the event log / admin
      logger.info("Clarification call canceled for matching attempt %s", event.matching_attempt_id)
  ```

- [x] In `matching/handlers/dispatcher.py`, register:
  ```python
  MatchingEvent.EventType.CLARIFICATION_CALL_BOOKED: [handle_clarification_call_booked_event],
  MatchingEvent.EventType.CLARIFICATION_CALL_CANCELED: [handle_clarification_call_canceled_event],
  ```

---

## Phase 8 — Tests

- [x] **Unit test: `record_clarification_call_booked()`**
  - Creates a new `ClarificationCallBooking` record and records event
  - A second call with the **same** `calendly_invitee_uri` is idempotent (updates, does not duplicate)
  - A second call with a **different** `calendly_invitee_uri` creates a second record (rebook scenario)
  - Transitions state from `AWAITING_INTRO_CALL_FEEDBACK_FROM_PARTICIPANT` → `CLARIFICATION_CALL_SCHEDULED`
  - Does not re-transition if already in `CLARIFICATION_CALL_SCHEDULED` (rebook without canceling first)
  - Handles non-existent `matching_attempt_id` gracefully (logs warning, does not raise)

- [x] **Unit test: `record_clarification_call_canceled()`**
  - Updates the matching `ClarificationCallBooking.status` to `"canceled"` (matched by `calendly_invitee_uri`)
  - Other bookings for the same `MatchingAttempt` are unaffected
  - Records `CLARIFICATION_CALL_CANCELED` event
  - Handles non-existent `matching_attempt_id` gracefully

- [x] **Integration test: Calendly webhook → clarification call path**
  - POST a valid `invitee.created` payload with `scheduled_event.name = "Check In"` and `tracking.utm_campaign = "matching-{id}"` → new `ClarificationCallBooking` created, `CLARIFICATION_CALL_BOOKED` event recorded, state = `CLARIFICATION_CALL_SCHEDULED`
  - POST the same `invitee.created` payload again (re-delivery) → idempotent, no duplicate record
  - POST a second `invitee.created` with a different `invitee_uri` (rebook after cancel) → second record created, state stays `CLARIFICATION_CALL_SCHEDULED`
  - POST a valid `invitee.canceled` payload → that specific `ClarificationCallBooking.status` = `"canceled"`, `CLARIFICATION_CALL_CANCELED` event recorded, state reverts to `AWAITING_INTRO_CALL_FEEDBACK_FROM_PARTICIPANT`
  - POST `"Check In"` payload with `utm_campaign = null` but matching participant email → resolved via email fallback
  - POST `"Check In"` payload where neither UTM nor email resolves a MatchingAttempt → no exception, warning logged
  - POST payload with `scheduled_event.name = "BeginnerLuft Erstgespräch"` → `_is_clarification_call` is False, existing intake flow handles it

- [x] **Unit test: `generate_participant_response_urls()`**
  - Returns a `START_COACHING` token URL and a Calendly URL with correct `utm_campaign`
  - No `CLARIFICATION_NEEDED` token is created

- [x] **Unit test: Slack notification functions**
  - `send_clarification_call_booked_info_to_staff_slack`: includes booking time, category, description
  - `send_clarification_call_booked_info_to_coach_slack`: sends to correct coach, no action required message

---

## Out of Scope / Follow-up Required

- **⚠️ Post-call workflow (manual step, TBD):** After the clarification call takes place, a staff member needs to take action — either restarting the coaching (likely a new matching attempt or a manual state update) or escalating further. No automated flow is defined for this yet. A future plan should cover what states/events/actions are available to staff after `CLARIFICATION_CALL_SCHEDULED`.
- **Automation: nudge staff if no booking arrives within N days** — matching attempt stays in `AWAITING_INTRO_CALL_FEEDBACK_FROM_PARTICIPANT` indefinitely if the participant never books; not automated, staff reviews manually.
- **Email fallbacks for new Slack notifications** — currently failures are only logged. Proper email fallbacks can be added in a follow-up if needed.
- **Remove `CLARIFICATION_WITH_PARTICIPANT_NEEDED` state and its associated handlers/Slack functions** — `send_escalation_info_slack`, `send_clarification_need_info_to_coach_slack` are now superseded. Safe to retire once confirmed no active records exist in that state.
