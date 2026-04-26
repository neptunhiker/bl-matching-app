"""
Integration tests for the matching flow — full signal chain.

Strategy: real DB operations, real signals, real dispatcher, real handlers.
All Slack and email *send* functions are patched at the handler module boundary
so that no external calls are made, but every event creation, state transition,
and routing decision executes normally.

Patch target: matching.handlers.notification_handlers
(functions are imported there at module level, so that is where they must be
replaced — patching at the source slack/emails modules would have no effect.)
"""
import pytest
from unittest.mock import DEFAULT, patch
from django.db import transaction
from django.utils import timezone

from matching.models import (
    MatchingAttempt,
    MatchingEvent,
    RequestToCoach,
    TriggeredByOptions,
)
from matching import services
from profiles.models import Coach, BeginnerLuftStaff
from accounts.models import User


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_HANDLER_MODULE = "matching.handlers.notification_handlers"

# Every external send function imported by notification_handlers.
# Patching all of them up front lets each test assert on exactly the ones
# it expects and confirm the rest were never called.
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
]


# ---------------------------------------------------------------------------
# Shared fixtures for integration tests
# ---------------------------------------------------------------------------

@pytest.fixture
def notifications():
    """Patch every send function in notification_handlers for one test.

    Yields a dict of  function_name → MagicMock  so tests can assert
    call counts and arguments.
    """
    with patch.multiple(
        _HANDLER_MODULE,
        **{name: DEFAULT for name in _ALL_SEND_FUNCS},
    ) as mocks:
        yield mocks


@pytest.fixture
def slack_coach(db):
    """A coach who prefers Slack communication and has a Slack user ID."""
    return Coach.objects.create(
        first_name="Slack",
        last_name="Coach",
        email="slack_coach_integration@example.com",
        preferred_communication_channel=Coach.CommunicationChannel.SLACK,
        slack_user_id="U_COACH_S1",
        status=Coach.Status.AVAILABLE,
    )


@pytest.fixture
def email_coach(db):
    """A coach who prefers Email communication."""
    return Coach.objects.create(
        first_name="Email",
        last_name="Coach",
        email="email_coach_integration@example.com",
        preferred_communication_channel=Coach.CommunicationChannel.EMAIL,
        status=Coach.Status.AVAILABLE,
    )


@pytest.fixture
def bl_contact_user(db):
    return User.objects.create_user(
        email="bl_contact_integration@example.com",
        password="testpass",
        first_name="BL",
        last_name="Contact",
        is_staff=True,
    )


@pytest.fixture
def bl_contact(db, bl_contact_user):
    return BeginnerLuftStaff.objects.create(
        user=bl_contact_user,
        slack_user_id="U_BL_S1",
    )


def _make_attempt_with_rtc(participant, coach, bl_contact, priority=1, ue=48):
    """Helper: create a matching attempt with automation on and one queued RTC."""
    ma = MatchingAttempt.objects.create(
        participant=participant,
        ue=ue,
        automation_enabled=True,
        bl_contact=bl_contact,
    )
    rtc = RequestToCoach.objects.create(
        matching_attempt=ma,
        coach=coach,
        priority=priority,
        ue=ue,
    )
    return ma, rtc


def _fresh(model_class, pk):
    """Fetch a fresh instance from the DB, bypassing any in-memory FSM state."""
    return model_class.objects.get(pk=pk)


def _event_types(matching_attempt):
    """Return the ordered list of event types created for a matching attempt."""
    return list(
        MatchingEvent.objects
        .filter(matching_attempt=matching_attempt)
        .order_by("created_at")
        .values_list("event_type", flat=True)
    )


# ---------------------------------------------------------------------------
# S1 — Full happy path (Slack coach)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_s1_full_happy_path_slack_coach(
    participant, staff_user, slack_coach, bl_contact, notifications
):
    """
    S1: Full happy path with a Slack-preferring coach.

    Phase 1  — Staff starts matching → first RTC sent to coach via Slack
    Phase 2  — Coach accepts on time → intro-call request to coach (Slack)
                                     + intro-call info to participant (email)
    Phase 3  — Coach confirms intro call → participant feedback requested (email)
    Phase 4  — Participant confirms coaching can start
                → coaching-start info to participant (email)
                + coaching-start info to coach (Slack)

    Expected total send calls: 6
    Expected final state:       MATCHING_COMPLETED
    """
    ma, rtc = _make_attempt_with_rtc(participant, slack_coach, bl_contact)

    # ── Phase 1: Staff starts matching ──────────────────────────────────────
    with transaction.atomic():
        ma.start_matching()
        ma.save()
        services.trigger_start_matching(ma, staff_user)

    ma = _fresh(MatchingAttempt, ma.pk)
    rtc = _fresh(RequestToCoach, rtc.pk)

    assert ma.state == MatchingAttempt.State.AWAITING_RTC_REPLY, \
        "Phase 1: attempt should be AWAITING_RTC_REPLY"
    assert rtc.state == RequestToCoach.State.AWAITING_REPLY, \
        "Phase 1: RTC should be AWAITING_REPLY after send"
    assert rtc.deadline_at is not None, \
        "Phase 1: deadline should be set after send_first_request()"

    notifications["send_first_coach_request_slack"].assert_called_once()
    notifications["send_first_coach_request_email"].assert_not_called()

    # ── Phase 2: Coach accepts on time ──────────────────────────────────────
    services.accept_or_decline_request_to_coach(
        rtc=rtc,
        accept=True,
        response_time=timezone.now(),
        responded_by_user=None,
    )

    ma = _fresh(MatchingAttempt, ma.pk)
    rtc = _fresh(RequestToCoach, rtc.pk)

    assert ma.state == MatchingAttempt.State.AWAITING_INTRO_CALL_FEEDBACK_FROM_COACH, \
        "Phase 2: attempt should be AWAITING_INTRO_CALL_FEEDBACK_FROM_COACH"
    assert ma.matched_coach_id == slack_coach.pk, \
        "Phase 2: matched_coach should be set"
    assert rtc.state == RequestToCoach.State.ACCEPTED, \
        "Phase 2: RTC should be ACCEPTED"

    notifications["send_intro_call_request_slack"].assert_called_once()
    notifications["send_intro_call_info_email_to_participant"].assert_called_once()
    notifications["send_intro_call_request_email"].assert_not_called()

    # ── Phase 3: Coach confirms intro call happened ──────────────────────────
    services.create_matching_event(
        matching_attempt=ma,
        event_type=MatchingEvent.EventType.INTRO_CALL_FEEDBACK_RECEIVED_FROM_COACH,
        triggered_by=TriggeredByOptions.COACH,
        triggered_by_user=None,
    )

    ma = _fresh(MatchingAttempt, ma.pk)

    assert ma.state == MatchingAttempt.State.AWAITING_INTRO_CALL_FEEDBACK_FROM_PARTICIPANT, \
        "Phase 3: attempt should be AWAITING_INTRO_CALL_FEEDBACK_FROM_PARTICIPANT"

    notifications["send_feedback_request_email_after_intro_call_to_participant"].assert_called_once()

    # ── Phase 4: Participant confirms coaching can start ─────────────────────
    services.continue_matching_after_participant_responded_to_intro_call_feedback(
        matching_attempt=ma,
        coaching_can_start=True,
        response_time=timezone.now(),
        responded_by_participant=participant,
    )

    ma = _fresh(MatchingAttempt, ma.pk)

    assert ma.state == MatchingAttempt.State.MATCHING_COMPLETED, \
        "Phase 4: attempt should be MATCHING_COMPLETED"

    notifications["send_coaching_start_info_email_to_participant"].assert_called_once()
    notifications["send_coaching_starting_info_slack"].assert_called_once()
    notifications["send_coaching_start_info_email_to_coach"].assert_not_called()

    # ── No unexpected sends ──────────────────────────────────────────────────
    for name in [
        "send_reminder_coach_request_slack",
        "send_reminder_coach_request_email",
        "send_escalation_info_slack",
        "send_escalation_info_email_to_staff",
        "send_all_rtcs_declined_info_slack",
        "send_clarification_call_booked_info_to_staff_slack",
        "send_clarification_call_booked_info_to_coach_slack",
        "send_clarification_call_booked_info_to_coach_email",
    ]:
        notifications[name].assert_not_called(), f"{name} should not have been called in S1"

    # ── Total call count ─────────────────────────────────────────────────────
    total_calls = sum(m.call_count for m in notifications.values())
    assert total_calls == 6, f"Expected exactly 6 notification calls, got {total_calls}"

    # ── Event audit trail ────────────────────────────────────────────────────
    event_types = _event_types(ma)
    assert MatchingEvent.EventType.STARTED in event_types
    assert MatchingEvent.EventType.RTC_SENT_TO_COACH in event_types
    assert MatchingEvent.EventType.RTC_ACCEPTED in event_types
    assert MatchingEvent.EventType.INTRO_CALL_REQUEST_SENT_TO_COACH in event_types
    assert MatchingEvent.EventType.INTRO_CALL_INFO_SENT_TO_PARTICIPANT in event_types
    assert MatchingEvent.EventType.INTRO_CALL_FEEDBACK_RECEIVED_FROM_COACH in event_types
    assert MatchingEvent.EventType.INTRO_CALL_FEEDBACK_REQUESTED_FROM_PARTICIPANT in event_types
    assert MatchingEvent.EventType.COACHING_CAN_START_FEEDBACK_RECEIVED_FROM_PARTICIPANT in event_types
    assert MatchingEvent.EventType.COACHING_START_INFO_SENT_TO_PARTICIPANT in event_types
    assert MatchingEvent.EventType.COACHING_START_INFO_SENT_TO_COACH in event_types
    assert len(event_types) == 10, \
        f"Expected exactly 10 events in S1, got {len(event_types)}: {event_types}"


# ---------------------------------------------------------------------------
# S1 variant — Full happy path (Email coach)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_s1_full_happy_path_email_coach(
    participant, staff_user, email_coach, bl_contact, notifications
):
    """
    S1 (Email variant): same flow but coach prefers Email.

    Phase 1  → send_first_coach_request_email (not Slack)
    Phase 2  → send_intro_call_request_email (not Slack)
    Phase 4  → send_coaching_start_info_email_to_coach (not Slack)
    """
    ma, rtc = _make_attempt_with_rtc(participant, email_coach, bl_contact)

    # Phase 1
    with transaction.atomic():
        ma.start_matching()
        ma.save()
        services.trigger_start_matching(ma, staff_user)

    notifications["send_first_coach_request_email"].assert_called_once()
    notifications["send_first_coach_request_slack"].assert_not_called()

    # Phase 2
    rtc = _fresh(RequestToCoach, rtc.pk)
    services.accept_or_decline_request_to_coach(
        rtc=rtc,
        accept=True,
        response_time=timezone.now(),
        responded_by_user=None,
    )

    notifications["send_intro_call_request_email"].assert_called_once()
    notifications["send_intro_call_request_slack"].assert_not_called()
    notifications["send_intro_call_info_email_to_participant"].assert_called_once()

    # Phase 3
    ma = _fresh(MatchingAttempt, ma.pk)
    services.create_matching_event(
        matching_attempt=ma,
        event_type=MatchingEvent.EventType.INTRO_CALL_FEEDBACK_RECEIVED_FROM_COACH,
        triggered_by=TriggeredByOptions.COACH,
        triggered_by_user=None,
    )

    notifications["send_feedback_request_email_after_intro_call_to_participant"].assert_called_once()

    # Phase 4
    ma = _fresh(MatchingAttempt, ma.pk)
    services.continue_matching_after_participant_responded_to_intro_call_feedback(
        matching_attempt=ma,
        coaching_can_start=True,
        response_time=timezone.now(),
        responded_by_participant=participant,
    )

    notifications["send_coaching_start_info_email_to_coach"].assert_called_once()
    notifications["send_coaching_starting_info_slack"].assert_not_called()
    notifications["send_coaching_start_info_email_to_participant"].assert_called_once()

    ma = _fresh(MatchingAttempt, ma.pk)
    assert ma.state == MatchingAttempt.State.MATCHING_COMPLETED

    total_calls = sum(m.call_count for m in notifications.values())
    assert total_calls == 6, f"Expected 6 notification calls for email coach, got {total_calls}"


# ---------------------------------------------------------------------------
# S1 — Automation gate blocks the entire chain mid-flow
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_s1_automation_disabled_before_start_blocks_all_sends(
    participant, staff_user, slack_coach, bl_contact, notifications
):
    """
    If automation_enabled is False, trigger_start_matching raises before any
    event is created and no notifications are sent.
    """
    from django.core.exceptions import ValidationError

    ma, _ = _make_attempt_with_rtc(participant, slack_coach, bl_contact)
    ma.automation_enabled = False
    ma.save()

    with transaction.atomic():
        ma.start_matching()
        ma.save()

        with pytest.raises(ValidationError):
            services.trigger_start_matching(ma, staff_user)

    for mock in notifications.values():
        mock.assert_not_called()


@pytest.mark.django_db
def test_s1_automation_disabled_after_rtc_sent_blocks_accept_chain(
    participant, staff_user, slack_coach, bl_contact, notifications
):
    """
    If automation is disabled between Phase 1 (RTC sent) and Phase 2
    (coach accepts), the RTC_ACCEPTED event is saved but the dispatcher gate
    must block all downstream handlers — no intro-call notifications go out.
    """
    ma, rtc = _make_attempt_with_rtc(participant, slack_coach, bl_contact)

    # Phase 1 — automation on, RTC goes out
    with transaction.atomic():
        ma.start_matching()
        ma.save()
        services.trigger_start_matching(ma, staff_user)

    notifications["send_first_coach_request_slack"].assert_called_once()

    # Staff disables automation before the coach responds
    ma = _fresh(MatchingAttempt, ma.pk)
    ma.disable_automation(triggered_by_user=staff_user)

    # Phase 2 — coach accepts, but automation is now off
    rtc = _fresh(RequestToCoach, rtc.pk)
    services.accept_or_decline_request_to_coach(
        rtc=rtc,
        accept=True,
        response_time=timezone.now(),
        responded_by_user=None,
    )

    # Gate must suppress intro-call notifications
    notifications["send_intro_call_request_slack"].assert_not_called()
    notifications["send_intro_call_info_email_to_participant"].assert_not_called()

    # Only the initial coach-request send should have fired
    total_calls = sum(m.call_count for m in notifications.values())
    assert total_calls == 1, \
        f"Expected exactly 1 notification call (Phase 1 only), got {total_calls}"
