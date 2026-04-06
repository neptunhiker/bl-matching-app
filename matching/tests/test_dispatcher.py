"""
Tests for the automation gate in matching/handlers/dispatcher.py (Phase 1).

Strategy: patch every handler registered in dispatch_event so no real
notifications are attempted, then assert whether each handler was called
or suppressed based on automation_enabled.
"""
import pytest
from unittest.mock import patch, DEFAULT

from matching.models import MatchingAttempt, MatchingEvent
from matching.handlers.dispatcher import dispatch_event


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ALL_HANDLER_PATHS = [
    "matching.handlers.notification_handlers.handle_matching_started_or_resumed_event",
    "matching.handlers.notification_handlers.handle_rtq_sent_event",
    "matching.handlers.notification_handlers.handle_rtc_reminder_sent_to_coach_event",
    "matching.handlers.notification_handlers.handle_matching_request_accepted_event",
    "matching.handlers.notification_handlers.handle_matching_request_declined_event",
    "matching.handlers.notification_handlers.handle_intro_call_sent_to_coach_event",
    "matching.handlers.notification_handlers.handle_intro_call_info_sent_to_participant_event",
    "matching.handlers.notification_handlers.handle_intro_call_feedback_received_from_coach_event",
    "matching.handlers.notification_handlers.handle_intro_call_feedback_requested_from_participant_event",
    "matching.handlers.notification_handlers.handle_coaching_can_start_feedback_received_from_participant_event",
    "matching.handlers.notification_handlers.handle_coaching_start_info_sent_out_to_coach_event",
    "matching.handlers.notification_handlers.handle_coaching_start_info_sent_out_to_participant_event",
    "matching.handlers.notification_handlers.handle_clarification_needed_feedback_received_from_participant_event",
    "matching.handlers.notification_handlers.handle_escalation_notification_sent_to_staff_event",
    "matching.handlers.notification_handlers.handle_clarification_need_info_to_coach_event",
    "matching.handlers.notification_handlers.handle_all_rtcs_declined_event",
    "matching.handlers.notification_handlers.handle_rtc_timed_out_event",
]

# Every event type that has a registered handler in the dispatcher.
ALL_HANDLED_EVENT_TYPES = [
    MatchingEvent.EventType.STARTED,
    MatchingEvent.EventType.RESUMED,
    MatchingEvent.EventType.RTC_SENT_TO_COACH,
    MatchingEvent.EventType.RTC_REMINDER_SENT_TO_COACH,
    MatchingEvent.EventType.RTC_ACCEPTED,
    MatchingEvent.EventType.RTC_DECLINED,
    MatchingEvent.EventType.INTRO_CALL_REQUEST_SENT_TO_COACH,
    MatchingEvent.EventType.INTRO_CALL_INFO_SENT_TO_PARTICIPANT,
    MatchingEvent.EventType.INTRO_CALL_FEEDBACK_RECEIVED_FROM_COACH,
    MatchingEvent.EventType.INTRO_CALL_FEEDBACK_REQUESTED_FROM_PARTICIPANT,
    MatchingEvent.EventType.COACHING_CAN_START_FEEDBACK_RECEIVED_FROM_PARTICIPANT,
    MatchingEvent.EventType.COACHING_START_INFO_SENT_TO_COACH,
    MatchingEvent.EventType.COACHING_START_INFO_SENT_TO_PARTICIPANT,
    MatchingEvent.EventType.CLARIFICATION_NEEEDED_FEEDBACK_RECEIVED_FROM_PARTICIPANT,
    MatchingEvent.EventType.ESCALATION_NOTIFICATION_SENT_TO_STAFF,
    MatchingEvent.EventType.INFORMATION_ABOUT_CLARIFICATION_SENT_TO_COACH,
    MatchingEvent.EventType.ALL_RTCS_DECLINED,
    MatchingEvent.EventType.RTC_TIMED_OUT,
]


def _make_event(event_type, automation_enabled):
    """Build a minimal mock MatchingEvent without hitting the DB."""
    from unittest.mock import MagicMock
    matching_attempt = MagicMock(spec=MatchingAttempt)
    matching_attempt.automation_enabled = automation_enabled
    matching_attempt.id = "test-attempt-id"

    event = MagicMock(spec=MatchingEvent)
    event.event_type = event_type
    event.matching_attempt = matching_attempt
    event.matching_attempt_id = "test-attempt-id"
    return event


_HANDLER_PATCH_KWARGS = {p.split(".")[-1]: DEFAULT for p in ALL_HANDLER_PATHS}


# ---------------------------------------------------------------------------
# Gate: all events suppressed when automation is OFF
# ---------------------------------------------------------------------------

class TestAutomationGate:

    @pytest.mark.parametrize("event_type", ALL_HANDLED_EVENT_TYPES)
    def test_no_handler_called_when_automation_disabled(self, event_type):
        """No handler should ever be called when automation is off."""
        event = _make_event(event_type, automation_enabled=False)

        with patch.multiple("matching.handlers.notification_handlers",
                            **_HANDLER_PATCH_KWARGS) as mocks:
            dispatch_event(event)
            for mock in mocks.values():
                mock.assert_not_called()

    @pytest.mark.parametrize("event_type", ALL_HANDLED_EVENT_TYPES)
    def test_handler_called_when_automation_enabled(self, event_type):
        """The correct handler should be called when automation is on."""
        event = _make_event(event_type, automation_enabled=True)

        with patch.multiple("matching.handlers.notification_handlers",
                            **_HANDLER_PATCH_KWARGS) as mocks:
            dispatch_event(event)
            called = [name for name, mock in mocks.items() if mock.called]
            assert called, (
                f"Expected a handler to be called for event_type={event_type!r} "
                f"with automation enabled, but none were."
            )
