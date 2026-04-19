"""
Phase 10 tests: intro call deadline feature.

Covers:
  1. MatchingAttemptQuerySet.eligible_for_intro_call_reminder()
  2. MatchingAttemptQuerySet.eligible_for_intro_call_staff_escalation()
  3. `send_intro_call_reminder` management command
  4. `notify_staff_of_intro_call_timeout` management command
  5. send_intro_call_timeout_notification_to_staff_slack() Slack service
  6. accept_or_decline_request_to_coach() sets intro_call_deadline_at
"""
import datetime
from unittest.mock import MagicMock, patch, DEFAULT

import pytest
from django.core.management import call_command
from django.utils import timezone

from matching.models import MatchingAttempt, MatchingEvent, RequestToCoach, TriggeredByOptions
from profiles.models import Coach

_HANDLER_MODULE = "matching.handlers.notification_handlers"

# All send functions imported at notification_handlers module level – patch here
# to prevent real Slack/email calls during tests that trigger the dispatcher.
_ALL_SEND_FUNCS = [
    "send_first_coach_request_slack",
    "send_first_coach_request_email",
    "send_reminder_coach_request_slack",
    "send_reminder_coach_request_email",
    "send_intro_call_request_slack",
    "send_intro_call_request_email",
    "send_intro_call_info_email_to_participant",
    "send_feedback_request_email_after_intro_call_to_participant",
    "send_coaching_starting_info_slack",
    "send_coaching_start_info_email_to_coach",
    "send_coaching_start_info_email_to_participant",
    "send_escalation_info_slack",
    "send_escalation_info_email_to_staff",
    "send_all_rtcs_declined_info_slack",
    "send_clarification_call_booked_info_to_staff_slack",
    "send_clarification_call_booked_info_to_coach_slack",
    "send_clarification_call_booked_info_to_coach_email",
    "send_intro_call_reminder_slack",
    "send_intro_call_timeout_notification_to_staff_slack",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bypass_fsm(attempt, *, state, **extra):
    """Force state (and any extra fields) on a MatchingAttempt via UPDATE."""
    MatchingAttempt.objects.filter(pk=attempt.pk).update(state=state, **extra)


def _fresh(pk):
    """Return a fresh MatchingAttempt from the DB, bypassing FSM in-memory state."""
    return MatchingAttempt.objects.get(pk=pk)


def _create_event(attempt, event_type):
    return MatchingEvent.objects.create(
        matching_attempt=attempt,
        event_type=event_type,
        triggered_by=TriggeredByOptions.SYSTEM,
    )


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def slack_coach(db, coach_user):
    """A coach with Slack as preferred channel and a valid Slack user ID."""
    return Coach.objects.create(
        user=coach_user,
        city="Berlin",
        preferred_communication_channel=Coach.CommunicationChannel.SLACK,
        slack_user_id="U_COACH_TEST",
        status=Coach.Status.AVAILABLE,
    )


@pytest.fixture
def attempt_awaiting_intro_call(db, matching_attempt, slack_coach, bl_staff):
    """
    MatchingAttempt in AWAITING_INTRO_CALL_FEEDBACK_FROM_COACH, automation on,
    with matched_coach, an overdue deadline, and bl_contact set.
    """
    _bypass_fsm(
        matching_attempt,
        state=MatchingAttempt.State.AWAITING_INTRO_CALL_FEEDBACK_FROM_COACH,
        automation_enabled=True,
        matched_coach_id=slack_coach.pk,
        intro_call_deadline_at=timezone.now() - datetime.timedelta(hours=1),
        bl_contact_id=bl_staff.pk,
    )
    return _fresh(matching_attempt.pk)


# ---------------------------------------------------------------------------
# 1. eligible_for_intro_call_reminder()
# ---------------------------------------------------------------------------

class TestEligibleForIntroCallReminder:

    @pytest.mark.django_db
    def test_returns_attempt_when_deadline_past(self, attempt_awaiting_intro_call):
        qs = MatchingAttempt.objects.eligible_for_intro_call_reminder()
        assert attempt_awaiting_intro_call in qs

    @pytest.mark.django_db
    def test_not_returned_when_deadline_in_future(self, matching_attempt, slack_coach, bl_staff):
        _bypass_fsm(
            matching_attempt,
            state=MatchingAttempt.State.AWAITING_INTRO_CALL_FEEDBACK_FROM_COACH,
            automation_enabled=True,
            matched_coach_id=slack_coach.pk,
            intro_call_deadline_at=timezone.now() + datetime.timedelta(hours=2),
            bl_contact_id=bl_staff.pk,
        )
        attempt = _fresh(matching_attempt.pk)
        qs = MatchingAttempt.objects.eligible_for_intro_call_reminder()
        assert attempt not in qs

    @pytest.mark.django_db
    def test_not_returned_when_automation_disabled(self, matching_attempt, slack_coach, bl_staff):
        _bypass_fsm(
            matching_attempt,
            state=MatchingAttempt.State.AWAITING_INTRO_CALL_FEEDBACK_FROM_COACH,
            automation_enabled=False,
            matched_coach_id=slack_coach.pk,
            intro_call_deadline_at=timezone.now() - datetime.timedelta(hours=1),
            bl_contact_id=bl_staff.pk,
        )
        attempt = _fresh(matching_attempt.pk)
        qs = MatchingAttempt.objects.eligible_for_intro_call_reminder()
        assert attempt not in qs

    @pytest.mark.django_db
    def test_not_returned_after_reminder_event_exists(self, attempt_awaiting_intro_call):
        _create_event(
            attempt_awaiting_intro_call,
            MatchingEvent.EventType.INTRO_CALL_REMINDER_SENT_TO_COACH,
        )
        qs = MatchingAttempt.objects.eligible_for_intro_call_reminder()
        assert attempt_awaiting_intro_call not in qs

    @pytest.mark.django_db
    def test_not_returned_in_wrong_state(self, matching_attempt, slack_coach, bl_staff):
        _bypass_fsm(
            matching_attempt,
            state=MatchingAttempt.State.AWAITING_RTC_REPLY,
            automation_enabled=True,
            matched_coach_id=slack_coach.pk,
            intro_call_deadline_at=timezone.now() - datetime.timedelta(hours=1),
            bl_contact_id=bl_staff.pk,
        )
        attempt = _fresh(matching_attempt.pk)
        qs = MatchingAttempt.objects.eligible_for_intro_call_reminder()
        assert attempt not in qs


# ---------------------------------------------------------------------------
# 2. eligible_for_intro_call_staff_escalation()
# ---------------------------------------------------------------------------

class TestEligibleForIntroCallStaffEscalation:

    @pytest.mark.django_db
    def test_not_returned_without_prior_reminder_event(self, attempt_awaiting_intro_call):
        qs = MatchingAttempt.objects.eligible_for_intro_call_staff_escalation()
        assert attempt_awaiting_intro_call not in qs

    @pytest.mark.django_db
    def test_returned_after_reminder_event_and_deadline_passed(self, attempt_awaiting_intro_call):
        _create_event(
            attempt_awaiting_intro_call,
            MatchingEvent.EventType.INTRO_CALL_REMINDER_SENT_TO_COACH,
        )
        qs = MatchingAttempt.objects.eligible_for_intro_call_staff_escalation()
        assert attempt_awaiting_intro_call in qs

    @pytest.mark.django_db
    def test_not_returned_after_staff_notified_event(self, attempt_awaiting_intro_call):
        _create_event(
            attempt_awaiting_intro_call,
            MatchingEvent.EventType.INTRO_CALL_REMINDER_SENT_TO_COACH,
        )
        _create_event(
            attempt_awaiting_intro_call,
            MatchingEvent.EventType.INTRO_CALL_TIMED_OUT_STAFF_NOTIFIED,
        )
        qs = MatchingAttempt.objects.eligible_for_intro_call_staff_escalation()
        assert attempt_awaiting_intro_call not in qs

    @pytest.mark.django_db
    def test_not_returned_when_deadline_in_future(self, matching_attempt, slack_coach, bl_staff):
        _bypass_fsm(
            matching_attempt,
            state=MatchingAttempt.State.AWAITING_INTRO_CALL_FEEDBACK_FROM_COACH,
            automation_enabled=True,
            matched_coach_id=slack_coach.pk,
            intro_call_deadline_at=timezone.now() + datetime.timedelta(hours=2),
            bl_contact_id=bl_staff.pk,
        )
        attempt = _fresh(matching_attempt.pk)
        _create_event(attempt, MatchingEvent.EventType.INTRO_CALL_REMINDER_SENT_TO_COACH)
        qs = MatchingAttempt.objects.eligible_for_intro_call_staff_escalation()
        assert attempt not in qs

    @pytest.mark.django_db
    def test_not_returned_when_automation_disabled(self, matching_attempt, slack_coach, bl_staff):
        _bypass_fsm(
            matching_attempt,
            state=MatchingAttempt.State.AWAITING_INTRO_CALL_FEEDBACK_FROM_COACH,
            automation_enabled=False,
            matched_coach_id=slack_coach.pk,
            intro_call_deadline_at=timezone.now() - datetime.timedelta(hours=1),
            bl_contact_id=bl_staff.pk,
        )
        attempt = _fresh(matching_attempt.pk)
        _create_event(attempt, MatchingEvent.EventType.INTRO_CALL_REMINDER_SENT_TO_COACH)
        qs = MatchingAttempt.objects.eligible_for_intro_call_staff_escalation()
        assert attempt not in qs


# ---------------------------------------------------------------------------
# 3. send_intro_call_reminder management command
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestSendIntroCallReminderCommand:

    def test_creates_reminder_event(self, attempt_awaiting_intro_call):
        with patch(f"{_HANDLER_MODULE}.send_intro_call_reminder_slack"):
            call_command("send_intro_call_reminder", verbosity=0)

        assert MatchingEvent.objects.filter(
            matching_attempt=attempt_awaiting_intro_call,
            event_type=MatchingEvent.EventType.INTRO_CALL_REMINDER_SENT_TO_COACH,
        ).exists()

    def test_extends_deadline(self, attempt_awaiting_intro_call):
        original_deadline = attempt_awaiting_intro_call.intro_call_deadline_at

        with patch(f"{_HANDLER_MODULE}.send_intro_call_reminder_slack"):
            call_command("send_intro_call_reminder", verbosity=0)

        updated = _fresh(attempt_awaiting_intro_call.pk)
        assert updated.intro_call_deadline_at > original_deadline

    def test_already_reminded_attempt_is_skipped(self, attempt_awaiting_intro_call):
        _create_event(
            attempt_awaiting_intro_call,
            MatchingEvent.EventType.INTRO_CALL_REMINDER_SENT_TO_COACH,
        )

        with patch(f"{_HANDLER_MODULE}.send_intro_call_reminder_slack"):
            call_command("send_intro_call_reminder", verbosity=0)

        # Event count must stay at 1 — the command must not create a duplicate.
        count = MatchingEvent.objects.filter(
            matching_attempt=attempt_awaiting_intro_call,
            event_type=MatchingEvent.EventType.INTRO_CALL_REMINDER_SENT_TO_COACH,
        ).count()
        assert count == 1

    def test_max_per_run_processes_only_ten(self, slack_coach, bl_staff, db):
        """When 11 eligible attempts exist, only MAX_PER_RUN=10 are processed."""
        from profiles.models import Participant

        for i in range(11):
            p = Participant.objects.create(
                first_name=f"Rmd{i}",
                last_name="Test",
                email=f"rmd_participant_{i}@example.com",
                city="Berlin",
                start_date=datetime.date(2026, 1, 1),
            )
            ma = MatchingAttempt.objects.create(participant=p, ue=48)
            _bypass_fsm(
                ma,
                state=MatchingAttempt.State.AWAITING_INTRO_CALL_FEEDBACK_FROM_COACH,
                automation_enabled=True,
                matched_coach_id=slack_coach.pk,
                intro_call_deadline_at=timezone.now() - datetime.timedelta(hours=1),
                bl_contact_id=bl_staff.pk,
            )

        with patch(f"{_HANDLER_MODULE}.send_intro_call_reminder_slack"):
            call_command("send_intro_call_reminder", verbosity=0)

        processed = MatchingEvent.objects.filter(
            event_type=MatchingEvent.EventType.INTRO_CALL_REMINDER_SENT_TO_COACH,
        ).count()
        assert processed == 10


# ---------------------------------------------------------------------------
# 4. notify_staff_of_intro_call_timeout management command
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestNotifyStaffOfIntroCallTimeoutCommand:

    def test_creates_staff_notified_event(self, attempt_awaiting_intro_call):
        _create_event(
            attempt_awaiting_intro_call,
            MatchingEvent.EventType.INTRO_CALL_REMINDER_SENT_TO_COACH,
        )

        with patch(f"{_HANDLER_MODULE}.send_intro_call_timeout_notification_to_staff_slack"):
            call_command("notify_staff_of_intro_call_timeout", verbosity=0)

        assert MatchingEvent.objects.filter(
            matching_attempt=attempt_awaiting_intro_call,
            event_type=MatchingEvent.EventType.INTRO_CALL_TIMED_OUT_STAFF_NOTIFIED,
        ).exists()

    def test_not_processed_without_prior_reminder_event(self, attempt_awaiting_intro_call):
        with patch(f"{_HANDLER_MODULE}.send_intro_call_timeout_notification_to_staff_slack"):
            call_command("notify_staff_of_intro_call_timeout", verbosity=0)

        assert not MatchingEvent.objects.filter(
            matching_attempt=attempt_awaiting_intro_call,
            event_type=MatchingEvent.EventType.INTRO_CALL_TIMED_OUT_STAFF_NOTIFIED,
        ).exists()

    def test_already_notified_attempt_is_skipped(self, attempt_awaiting_intro_call):
        _create_event(
            attempt_awaiting_intro_call,
            MatchingEvent.EventType.INTRO_CALL_REMINDER_SENT_TO_COACH,
        )
        _create_event(
            attempt_awaiting_intro_call,
            MatchingEvent.EventType.INTRO_CALL_TIMED_OUT_STAFF_NOTIFIED,
        )

        with patch(f"{_HANDLER_MODULE}.send_intro_call_timeout_notification_to_staff_slack"):
            call_command("notify_staff_of_intro_call_timeout", verbosity=0)

        count = MatchingEvent.objects.filter(
            matching_attempt=attempt_awaiting_intro_call,
            event_type=MatchingEvent.EventType.INTRO_CALL_TIMED_OUT_STAFF_NOTIFIED,
        ).count()
        assert count == 1

    def test_max_per_run_processes_only_ten(self, slack_coach, bl_staff, db):
        """When 11 eligible attempts exist, only MAX_PER_RUN=10 are processed."""
        from profiles.models import Participant

        for i in range(11):
            p = Participant.objects.create(
                first_name=f"Staff{i}",
                last_name="Test",
                email=f"staff_notif_participant_{i}@example.com",
                city="Berlin",
                start_date=datetime.date(2026, 1, 1),
            )
            ma = MatchingAttempt.objects.create(participant=p, ue=48)
            _bypass_fsm(
                ma,
                state=MatchingAttempt.State.AWAITING_INTRO_CALL_FEEDBACK_FROM_COACH,
                automation_enabled=True,
                matched_coach_id=slack_coach.pk,
                intro_call_deadline_at=timezone.now() - datetime.timedelta(hours=1),
                bl_contact_id=bl_staff.pk,
            )
            _create_event(ma, MatchingEvent.EventType.INTRO_CALL_REMINDER_SENT_TO_COACH)

        with patch(f"{_HANDLER_MODULE}.send_intro_call_timeout_notification_to_staff_slack"):
            call_command("notify_staff_of_intro_call_timeout", verbosity=0)

        processed = MatchingEvent.objects.filter(
            event_type=MatchingEvent.EventType.INTRO_CALL_TIMED_OUT_STAFF_NOTIFIED,
        ).count()
        assert processed == 10


# ---------------------------------------------------------------------------
# 5. send_intro_call_timeout_notification_to_staff_slack() – Slack service
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_slack_client():
    client = MagicMock()
    client.conversations_open.return_value = {"channel": {"id": "C_BL_TEST"}}
    client.chat_postMessage.return_value = {"ok": True}
    return client


@pytest.mark.django_db
class TestSendIntroCallTimeoutNotificationToStaffSlack:
    """Unit tests for the Slack service function (WebClient patched out)."""

    def test_calls_chat_post_message(self, attempt_awaiting_intro_call, mock_slack_client):
        from slack.services import send_intro_call_timeout_notification_to_staff_slack

        with patch("slack.services.WebClient", return_value=mock_slack_client):
            send_intro_call_timeout_notification_to_staff_slack(attempt_awaiting_intro_call)

        mock_slack_client.chat_postMessage.assert_called_once()

    def test_sends_to_bl_contact_slack_channel(self, attempt_awaiting_intro_call, mock_slack_client):
        from slack.services import send_intro_call_timeout_notification_to_staff_slack

        with patch("slack.services.WebClient", return_value=mock_slack_client):
            send_intro_call_timeout_notification_to_staff_slack(attempt_awaiting_intro_call)

        _, kwargs = mock_slack_client.chat_postMessage.call_args
        # The DM channel is the one returned by conversations_open (C_BL_TEST)
        assert kwargs["channel"] == "C_BL_TEST"

    def test_opens_dm_with_bl_contact_slack_user_id(self, attempt_awaiting_intro_call, mock_slack_client):
        from slack.services import send_intro_call_timeout_notification_to_staff_slack

        bl_slack_id = attempt_awaiting_intro_call.bl_contact.slack_user_id

        with patch("slack.services.WebClient", return_value=mock_slack_client):
            send_intro_call_timeout_notification_to_staff_slack(attempt_awaiting_intro_call)

        mock_slack_client.conversations_open.assert_called_once_with(users=[bl_slack_id])

    def test_message_contains_coach_name(self, attempt_awaiting_intro_call, mock_slack_client):
        from slack.services import send_intro_call_timeout_notification_to_staff_slack

        with patch("slack.services.WebClient", return_value=mock_slack_client):
            send_intro_call_timeout_notification_to_staff_slack(attempt_awaiting_intro_call)

        _, kwargs = mock_slack_client.chat_postMessage.call_args
        blocks_text = " ".join(str(b) for b in kwargs["blocks"])
        coach = attempt_awaiting_intro_call.matched_coach
        assert coach.user.first_name in blocks_text

    def test_message_contains_participant_name(self, attempt_awaiting_intro_call, mock_slack_client):
        from slack.services import send_intro_call_timeout_notification_to_staff_slack

        with patch("slack.services.WebClient", return_value=mock_slack_client):
            send_intro_call_timeout_notification_to_staff_slack(attempt_awaiting_intro_call)

        _, kwargs = mock_slack_client.chat_postMessage.call_args
        blocks_text = " ".join(str(b) for b in kwargs["blocks"])
        assert attempt_awaiting_intro_call.participant.first_name in blocks_text

    def test_raises_when_bl_contact_has_no_slack_id(self, db, matching_attempt, slack_coach, mock_slack_client):
        from slack.services import send_intro_call_timeout_notification_to_staff_slack
        from profiles.models import BeginnerLuftStaff
        from accounts.models import User

        bl_user = User.objects.create_user(
            email="noslack_bl@example.com",
            password="x",
            is_staff=True,
        )
        bl_no_slack = BeginnerLuftStaff.objects.create(user=bl_user, slack_user_id="")
        _bypass_fsm(
            matching_attempt,
            state=MatchingAttempt.State.AWAITING_INTRO_CALL_FEEDBACK_FROM_COACH,
            automation_enabled=True,
            matched_coach_id=slack_coach.pk,
            intro_call_deadline_at=timezone.now() - datetime.timedelta(hours=1),
            bl_contact_id=bl_no_slack.pk,
        )
        attempt = _fresh(matching_attempt.pk)

        with pytest.raises(ValueError):
            send_intro_call_timeout_notification_to_staff_slack(attempt)

        mock_slack_client.chat_postMessage.assert_not_called()


# ---------------------------------------------------------------------------
# 6. accept_or_decline_request_to_coach() sets intro_call_deadline_at
# ---------------------------------------------------------------------------

@pytest.fixture
def rtc_awaiting_reply(db, matching_attempt, slack_coach):
    """
    MatchingAttempt in AWAITING_RTC_REPLY + one RequestToCoach in AWAITING_REPLY
    with a future deadline — ready for accept_or_decline_request_to_coach().
    """
    _bypass_fsm(
        matching_attempt,
        state=MatchingAttempt.State.AWAITING_RTC_REPLY,
        automation_enabled=True,
    )
    ma = _fresh(matching_attempt.pk)
    rtc = RequestToCoach.objects.create(
        matching_attempt=ma,
        coach=slack_coach,
        priority=1,
        ue=48,
        deadline_at=timezone.now() + datetime.timedelta(days=2),
    )
    RequestToCoach.objects.filter(pk=rtc.pk).update(
        state=RequestToCoach.State.AWAITING_REPLY,
    )
    return RequestToCoach.objects.get(pk=rtc.pk)


@pytest.mark.django_db
class TestAcceptOrDeclineSetsDeadline:

    def test_intro_call_deadline_set_after_on_time_acceptance(self, rtc_awaiting_reply):
        from matching import services

        with patch.multiple(_HANDLER_MODULE, **{fn: DEFAULT for fn in _ALL_SEND_FUNCS}):
            services.accept_or_decline_request_to_coach(
                rtc=rtc_awaiting_reply,
                accept=True,
                response_time=timezone.now(),
                responded_by_user=rtc_awaiting_reply.coach.user,
            )

        ma = _fresh(rtc_awaiting_reply.matching_attempt.pk)
        assert ma.intro_call_deadline_at is not None

    def test_intro_call_deadline_not_set_on_decline(self, rtc_awaiting_reply):
        from matching import services

        with patch.multiple(_HANDLER_MODULE, **{fn: DEFAULT for fn in _ALL_SEND_FUNCS}):
            services.accept_or_decline_request_to_coach(
                rtc=rtc_awaiting_reply,
                accept=False,
                response_time=timezone.now(),
                responded_by_user=rtc_awaiting_reply.coach.user,
            )

        ma = _fresh(rtc_awaiting_reply.matching_attempt.pk)
        assert ma.intro_call_deadline_at is None
