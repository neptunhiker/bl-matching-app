"""
Tests for notification_handlers routing of the INTRO_CALL_REMINDER_SENT_TO_COACH event.

Strategy: real DB, real handler function, all send functions patched at the
handler module boundary so no external calls are made.
"""
import pytest
from unittest.mock import patch, MagicMock

from matching.models import MatchingAttempt, MatchingEvent
from matching.handlers.notification_handlers import handle_intro_call_reminder_sent_to_coach_event
from profiles.models import Coach


_HANDLER_MODULE = "matching.handlers.notification_handlers"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def email_coach(db):
    """Coach who prefers email."""
    return Coach.objects.create(
        first_name="Email",
        last_name="Coach",
        email="email_coach@example.com",
        preferred_communication_channel=Coach.CommunicationChannel.EMAIL,
    )


@pytest.fixture
def slack_coach(db):
    """Coach who prefers Slack and has a Slack user ID."""
    return Coach.objects.create(
        first_name="Slack",
        last_name="Coach",
        email="slack_coach@example.com",
        preferred_communication_channel=Coach.CommunicationChannel.SLACK,
        slack_user_id="U_COACH_SLACK",
    )


def _make_reminder_event(matching_attempt):
    """Build a minimal mock MatchingEvent of the reminder type."""
    event = MagicMock(spec=MatchingEvent)
    event.event_type = MatchingEvent.EventType.INTRO_CALL_REMINDER_SENT_TO_COACH
    event.matching_attempt = matching_attempt
    return event


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_handler_routes_email_coach_to_email_service(participant, email_coach):
    """
    For an email-preference coach the handler must call the email service and
    must NOT call the Slack service.
    """
    ma = MatchingAttempt.objects.create(
        participant=participant,
        matched_coach=email_coach,
        ue=48,
    )
    event = _make_reminder_event(ma)

    with patch(f"{_HANDLER_MODULE}.send_intro_call_reminder_email_to_coach") as mock_email, \
         patch(f"{_HANDLER_MODULE}.send_intro_call_reminder_slack") as mock_slack:
        handle_intro_call_reminder_sent_to_coach_event(event)

    mock_email.assert_called_once_with(ma)
    mock_slack.assert_not_called()


@pytest.mark.django_db
def test_handler_routes_slack_coach_to_slack_service(participant, slack_coach):
    """
    For a Slack-preference coach the handler must call the Slack service and
    must NOT call the email service.
    """
    ma = MatchingAttempt.objects.create(
        participant=participant,
        matched_coach=slack_coach,
        ue=48,
    )
    event = _make_reminder_event(ma)

    with patch(f"{_HANDLER_MODULE}.send_intro_call_reminder_email_to_coach") as mock_email, \
         patch(f"{_HANDLER_MODULE}.send_intro_call_reminder_slack") as mock_slack:
        handle_intro_call_reminder_sent_to_coach_event(event)

    mock_slack.assert_called_once_with(ma)
    mock_email.assert_not_called()
