"""Unit tests for the clarification-call service functions.

Covers:
  - record_clarification_call_booked()
  - record_clarification_call_canceled()
"""
import pytest
from unittest.mock import patch

from matching.models import MatchingAttempt, MatchingEvent, ClarificationCallBooking

# ── shared constants ──────────────────────────────────────────────────────────

_INVITEE_URI_1 = "https://api.calendly.com/scheduled_events/AAA/invitees/inv-1"
_INVITEE_URI_2 = "https://api.calendly.com/scheduled_events/AAA/invitees/inv-2"
_EVENT_URI     = "https://api.calendly.com/scheduled_events/AAA"
_START_TIME    = "2026-05-10T10:00:00.000000Z"
_PARTICIPANT_EMAIL = "peter_participant@example.com"  # matches matching/tests/conftest.py


# ── helpers ───────────────────────────────────────────────────────────────────

def _invitee(uri=_INVITEE_URI_1, email=_PARTICIPANT_EMAIL, qna=None):
    return {
        "uri": uri,
        "email": email,
        "name": "Peter Participant",
        "questions_and_answers": qna or [],
    }


def _scheduled_event(uri=_EVENT_URI, start_time=_START_TIME):
    return {"uri": uri, "name": "Check In", "start_time": start_time}


def _set_state(matching_attempt, state):
    """Bypass FSMField(protected=True) by using .update() directly."""
    MatchingAttempt.objects.filter(pk=matching_attempt.pk).update(state=state)
    return MatchingAttempt.objects.get(pk=matching_attempt.pk)


# ── record_clarification_call_booked ─────────────────────────────────────────

@pytest.mark.django_db
class TestRecordClarificationCallBooked:

    @pytest.fixture(autouse=True)
    def _no_dispatch(self):
        """Prevent the dispatcher from firing Slack/email handlers in unit tests."""
        with patch("matching.handlers.dispatcher.dispatch_event"):
            yield

    def _book(self, ma_id=None, email=_PARTICIPANT_EMAIL, uri=_INVITEE_URI_1, qna=None):
        from matching.services import record_clarification_call_booked
        record_clarification_call_booked(
            matching_attempt_id=ma_id,
            invitee_email=email,
            invitee_data=_invitee(uri=uri, email=email, qna=qna),
            scheduled_event=_scheduled_event(),
            raw_payload={},
        )

    def test_creates_booking_record(self, matching_attempt_with_coach):
        ma = _set_state(
            matching_attempt_with_coach,
            MatchingAttempt.State.AWAITING_INTRO_CALL_FEEDBACK_FROM_PARTICIPANT,
        )
        self._book(ma_id=str(ma.id))

        assert ClarificationCallBooking.objects.count() == 1
        b = ClarificationCallBooking.objects.get()
        assert b.matching_attempt == ma
        assert b.calendly_invitee_uri == _INVITEE_URI_1
        assert b.status == "active"

    def test_parses_qna_category_and_description(self, matching_attempt_with_coach):
        ma = _set_state(
            matching_attempt_with_coach,
            MatchingAttempt.State.AWAITING_INTRO_CALL_FEEDBACK_FROM_PARTICIPANT,
        )
        qna = [
            {"question": "Was ist dein Anliegen für diesen Termin?", "answer": "Organisatorisches"},
            {"question": "Bitte beschreibe dein Anliegen kurz: ", "answer": "Ich hätte gerne einen anderen Termin."},
        ]
        self._book(ma_id=str(ma.id), qna=qna)

        b = ClarificationCallBooking.objects.get()
        assert b.clarification_category == "Organisatorisches"
        assert "anderen Termin" in b.clarification_description

    def test_description_label_without_trailing_space(self, matching_attempt_with_coach):
        """Both label variants (with and without trailing space) are accepted."""
        ma = _set_state(
            matching_attempt_with_coach,
            MatchingAttempt.State.AWAITING_INTRO_CALL_FEEDBACK_FROM_PARTICIPANT,
        )
        qna = [{"question": "Bitte beschreibe dein Anliegen kurz:", "answer": "Short label answer"}]
        self._book(ma_id=str(ma.id), qna=qna)

        assert ClarificationCallBooking.objects.get().clarification_description == "Short label answer"

    def test_creates_clarification_call_booked_event(self, matching_attempt_with_coach):
        ma = _set_state(
            matching_attempt_with_coach,
            MatchingAttempt.State.AWAITING_INTRO_CALL_FEEDBACK_FROM_PARTICIPANT,
        )
        self._book(ma_id=str(ma.id))

        assert MatchingEvent.objects.filter(
            matching_attempt=ma,
            event_type=MatchingEvent.EventType.CLARIFICATION_CALL_BOOKED,
        ).exists()

    def test_transitions_state_to_clarification_call_scheduled(self, matching_attempt_with_coach):
        ma = _set_state(
            matching_attempt_with_coach,
            MatchingAttempt.State.AWAITING_INTRO_CALL_FEEDBACK_FROM_PARTICIPANT,
        )
        self._book(ma_id=str(ma.id))

        fresh = MatchingAttempt.objects.get(pk=ma.pk)
        assert fresh.state == MatchingAttempt.State.CLARIFICATION_CALL_SCHEDULED

    def test_idempotent_on_redelivery(self, matching_attempt_with_coach):
        """Same invitee_uri delivered twice → only one record, no duplicate."""
        ma = _set_state(
            matching_attempt_with_coach,
            MatchingAttempt.State.AWAITING_INTRO_CALL_FEEDBACK_FROM_PARTICIPANT,
        )
        self._book(ma_id=str(ma.id))
        self._book(ma_id=str(ma.id))  # re-delivery

        assert ClarificationCallBooking.objects.count() == 1

    def test_rebook_with_different_uri_creates_second_record(self, matching_attempt_with_coach):
        """New booking (different invitee_uri after cancellation) creates a second record."""
        ma = _set_state(
            matching_attempt_with_coach,
            MatchingAttempt.State.AWAITING_INTRO_CALL_FEEDBACK_FROM_PARTICIPANT,
        )
        self._book(ma_id=str(ma.id), uri=_INVITEE_URI_1)
        self._book(ma_id=str(ma.id), uri=_INVITEE_URI_2)

        assert ClarificationCallBooking.objects.count() == 2

    def test_does_not_retransition_when_already_scheduled(self, matching_attempt_with_coach):
        """No FSM error when rebooking without canceling first (state already CLARIFICATION_CALL_SCHEDULED)."""
        ma = _set_state(
            matching_attempt_with_coach,
            MatchingAttempt.State.AWAITING_INTRO_CALL_FEEDBACK_FROM_PARTICIPANT,
        )
        self._book(ma_id=str(ma.id), uri=_INVITEE_URI_1)  # → CLARIFICATION_CALL_SCHEDULED
        self._book(ma_id=str(ma.id), uri=_INVITEE_URI_2)  # rebook — should not raise

        fresh = MatchingAttempt.objects.get(pk=ma.pk)
        assert fresh.state == MatchingAttempt.State.CLARIFICATION_CALL_SCHEDULED

    def test_resolves_by_email_when_no_utm_id(self, matching_attempt_with_coach):
        """When matching_attempt_id is None, resolve via participant email fallback."""
        ma = _set_state(
            matching_attempt_with_coach,
            MatchingAttempt.State.AWAITING_INTRO_CALL_FEEDBACK_FROM_PARTICIPANT,
        )
        self._book(ma_id=None, email=_PARTICIPANT_EMAIL)

        assert ClarificationCallBooking.objects.filter(matching_attempt=ma).count() == 1

    def test_graceful_when_id_not_found(self):
        """Unknown matching_attempt_id → warning logged, no exception, no record created."""
        from matching.services import record_clarification_call_booked
        record_clarification_call_booked(
            matching_attempt_id="00000000-0000-0000-0000-000000000000",
            invitee_email="nobody@example.com",
            invitee_data=_invitee(email="nobody@example.com"),
            scheduled_event=_scheduled_event(),
            raw_payload={},
        )

        assert ClarificationCallBooking.objects.count() == 0


# ── record_clarification_call_canceled ───────────────────────────────────────

@pytest.mark.django_db
class TestRecordClarificationCallCanceled:

    @pytest.fixture(autouse=True)
    def _no_dispatch(self):
        with patch("matching.handlers.dispatcher.dispatch_event"):
            yield

    # ── helpers ──

    def _book(self, ma, uri=_INVITEE_URI_1):
        from matching.services import record_clarification_call_booked
        record_clarification_call_booked(
            matching_attempt_id=str(ma.id),
            invitee_email=_PARTICIPANT_EMAIL,
            invitee_data=_invitee(uri=uri),
            scheduled_event=_scheduled_event(),
            raw_payload={},
        )

    def _cancel(self, ma, uri=_INVITEE_URI_1):
        from matching.services import record_clarification_call_canceled
        record_clarification_call_canceled(
            matching_attempt_id=str(ma.id),
            invitee_email=_PARTICIPANT_EMAIL,
            invitee_data=_invitee(uri=uri),
            raw_payload={},
        )

    def _setup(self, ma):
        return _set_state(ma, MatchingAttempt.State.AWAITING_INTRO_CALL_FEEDBACK_FROM_PARTICIPANT)

    # ── tests ──

    def test_marks_booking_canceled(self, matching_attempt_with_coach):
        ma = self._setup(matching_attempt_with_coach)
        self._book(ma)
        self._cancel(ma)

        assert ClarificationCallBooking.objects.get(calendly_invitee_uri=_INVITEE_URI_1).status == "canceled"

    def test_only_correct_booking_is_canceled(self, matching_attempt_with_coach):
        """Canceling one booking leaves other bookings for the same attempt unaffected."""
        ma = self._setup(matching_attempt_with_coach)
        self._book(ma, uri=_INVITEE_URI_1)
        self._book(ma, uri=_INVITEE_URI_2)
        self._cancel(ma, uri=_INVITEE_URI_1)

        assert ClarificationCallBooking.objects.get(calendly_invitee_uri=_INVITEE_URI_1).status == "canceled"
        assert ClarificationCallBooking.objects.get(calendly_invitee_uri=_INVITEE_URI_2).status == "active"

    def test_creates_canceled_event(self, matching_attempt_with_coach):
        ma = self._setup(matching_attempt_with_coach)
        self._book(ma)
        self._cancel(ma)

        assert MatchingEvent.objects.filter(
            matching_attempt=ma,
            event_type=MatchingEvent.EventType.CLARIFICATION_CALL_CANCELED,
        ).exists()

    def test_reverts_state_to_awaiting(self, matching_attempt_with_coach):
        """After cancellation the state goes back to AWAITING_INTRO_CALL_FEEDBACK_FROM_PARTICIPANT."""
        ma = self._setup(matching_attempt_with_coach)
        self._book(ma)
        self._cancel(ma)

        fresh = MatchingAttempt.objects.get(pk=ma.pk)
        assert fresh.state == MatchingAttempt.State.AWAITING_INTRO_CALL_FEEDBACK_FROM_PARTICIPANT

    def test_graceful_when_id_not_found(self):
        """Unknown matching_attempt_id → no exception, nothing mutated."""
        from matching.services import record_clarification_call_canceled
        record_clarification_call_canceled(
            matching_attempt_id="00000000-0000-0000-0000-000000000000",
            invitee_email="nobody@example.com",
            invitee_data=_invitee(email="nobody@example.com"),
            raw_payload={},
        )
