# Fix: Token-Based Links Remain Valid After Matching Cancellation

## Problem

When a matching is cancelled (`MatchingAttempt.state == CANCELLED`), all outstanding
token-based action links sent to coaches and participants continue to function — or return
misleading error messages — rather than showing a clear "this matching has been cancelled"
response.

Three public views are affected:

| View | URL name | Token type | Observed symptom |
|------|----------|------------|-----------------|
| `CoachRespondView` | `coach_respond` | `CoachActionToken` (ACCEPT / DECLINE) | Coach can still accept/decline a cancelled RtC |
| `ConfirmIntroCallView` | `confirm_intro_call` | `CoachActionToken` (CONFIRM_INTRO_CALL) | Returns "request was already answered" — factually wrong |
| `ParticipantRespondView` | `participant_respond` | `ParticipantActionToken` (START_COACHING) | Participant can still trigger coaching-start on a cancelled matching |

### Root cause

Each view guards against re-use by checking a small set of **terminal states**, but none of
them include `CANCELLED` as a distinct, explicitly-handled case:

- `CoachRespondView.TERMINAL_STATES` = `{ACCEPTED, REJECTED}` — `CANCELLED` RtC state is missing; the parent `MatchingAttempt` state is never checked.
- `ConfirmIntroCallView.TERMINAL_STATES` = `{MATCHING_COMPLETED}` — `CANCELLED` is in `MatchingAttempt.TERMINAL_STATES` but the view falls through to the generic `response_already_used.html` with wrong copy.
- `ParticipantRespondView.TERMINAL_STATES` = `{MATCHING_COMPLETED}` — `CANCELLED` is not in the set at all, so the token is fully processed.

---

## Implementation Plan

### Phase 1 — Create a dedicated "Matching cancelled" template

- [ ] Create `matching/templates/matching/response_matching_cancelled.html`
  - Extend `base.html`
  - Show a clear, friendly message: "Dieses Matching wurde abgebrochen" ("This matching has been cancelled")
  - Include a brief explanation that the link is no longer valid because the matching process was stopped
  - Do **not** show a retry action or any form — this is a dead-end page
  - Match the visual style of `response_invalid_token.html` and `response_already_used.html` (centered card, icon, neutral tone)

---

### Phase 2 — Fix `CoachRespondView` (coach RtC accept / decline)

**File:** `matching/views.py` → `CoachRespondView.get()`

- [ ] After the `already_used` check (step 2) and before the existing RtC terminal-state check (step 3), add a new guard:

  ```python
  # ── 2b. Parent MatchingAttempt is cancelled ──────────────────────────────
  if rtc.matching_attempt.state == MatchingAttempt.State.CANCELLED:
      return render(request, 'matching/response_matching_cancelled.html', base_context)
  ```

  The queryset in `consume_token(...)` already selects `request_to_coach__matching_attempt`, so no extra DB hit is needed — just ensure `matching_attempt__state` is included in `select_related`.

- [ ] Update the `select_related` call to include `matching_attempt__state` access:
  ```python
  CoachActionToken.objects.select_related(
      'request_to_coach__matching_attempt__participant',
      'request_to_coach__coach',
  )
  ```
  *(Verify the current chain already covers `matching_attempt` — if so, no change needed.)*

---

### Phase 3 — Fix `ConfirmIntroCallView` (coach intro-call confirmation)

**File:** `matching/views.py` → `ConfirmIntroCallView.get()`

- [ ] Replace the single TERMINAL_STATES block (step 3) with two separate checks:

  ```python
  # ── 3a. Matching was cancelled ──────────────────────────────────────────
  if ma.state == MatchingAttempt.State.CANCELLED:
      return render(request, 'matching/response_matching_cancelled.html', base_context)

  # ── 3b. Matching already completed ─────────────────────────────────────
  if ma.state == MatchingAttempt.State.MATCHING_COMPLETED:
      return render(
          request,
          'matching/response_already_used.html',
          {**base_context, 'previous_state': ma.get_state_display()},
      )
  ```

- [ ] Remove the now-unused `TERMINAL_STATES` class attribute from `ConfirmIntroCallView` (or update it to only list `MATCHING_COMPLETED` and add a comment explaining the split).

---

### Phase 4 — Fix `ParticipantRespondView` (participant coaching-start acceptance)

**File:** `matching/views.py` → `ParticipantRespondView.get()`

- [ ] After the `already_used` check (step 2) and before the existing terminal-state check (step 3), add a new guard:

  ```python
  # ── 2b. Matching was cancelled ──────────────────────────────────────────
  if matching_attempt.state == MatchingAttempt.State.CANCELLED:
      return render(request, 'matching/response_matching_cancelled.html', base_context)
  ```

- [ ] Confirm that `base_context` at that point contains at least `coach` and `participant` (it does — these are set before the TERMINAL_STATES check).

---

### Phase 5 — Add tests

**File:** `matching/tests/test_views.py`

Add the following three test cases alongside the existing token-view tests:

- [ ] **`test_coach_respond_cancelled_matching`**
  - Set `matching_attempt.state = CANCELLED` (via `MatchingAttempt.objects.filter(...).update(...)`)
  - GET `coach_respond` with the accept token
  - Assert status 200 and template `matching/response_matching_cancelled.html`
  - Assert that `accept_or_decline_request_to_coach` was **not** called (use `monkeypatch`)

- [ ] **`test_confirm_intro_call_cancelled_matching`**
  - Set `matching_attempt.state = CANCELLED`
  - GET `confirm_intro_call` with the confirm token
  - Assert status 200 and template `matching/response_matching_cancelled.html`
  - Assert that no `INTRO_CALL_FEEDBACK_RECEIVED_FROM_COACH` event was created

- [ ] **`test_participant_respond_cancelled_matching`**
  - Set `matching_attempt.state = CANCELLED`
  - GET `participant_respond` with the start-coaching token
  - Assert status 200 and template `matching/response_matching_cancelled.html`
  - Assert that `continue_matching_after_participant_responded_to_intro_call_feedback` was **not** called

---

### Phase 6 — Manual re-test

Reference: [TestProcedure.md — Section 4.1 Cancel matching](TestProcedure.md#41-cancel-matching)

- [ ] Cancel a matching while the coach's RtC accept link is still outstanding → verify the new cancelled page is shown
- [ ] Cancel a matching while the coach's intro-call confirm link is outstanding → verify the new cancelled page is shown (not "already answered")
- [ ] Cancel a matching while the participant's start-coaching link is outstanding → verify the new cancelled page is shown
- [ ] Update section 4.1 in `TestProcedure.md` with re-test date and results
- [ ] Mark issue 1 in the summary as resolved

---

## Files to change

| File | Change |
|------|--------|
| `matching/templates/matching/response_matching_cancelled.html` | **Create** — new template |
| `matching/views.py` | **Edit** — `CoachRespondView`, `ConfirmIntroCallView`, `ParticipantRespondView` |
| `matching/tests/test_views.py` | **Edit** — add 3 new test functions |
| `docs/TestProcedure.md` | **Edit** — update section 4.1 after manual re-test |

## Acceptance criteria

1. A GET on any token URL belonging to a cancelled matching returns HTTP 200 with `response_matching_cancelled.html`.
2. No state transitions or events are triggered for cancelled-matching tokens.
3. All three new tests pass (`pytest matching/tests/test_views.py`).
4. Existing token-view tests still pass (no regression).
5. Manual re-test of section 4.1 passes with all three sub-scenarios confirmed.
