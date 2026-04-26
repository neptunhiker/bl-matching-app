import datetime

import pytest
from unittest.mock import MagicMock
from django.utils import timezone

from accounts.models import User
from profiles.models import Coach, BeginnerLuftStaff
from matching.models import MatchingAttempt, RequestToCoach


@pytest.fixture
def coach_with_slack(db):
    return Coach.objects.create(
        first_name="Slack",
        last_name="Coach",
        email="coach_slack@example.com",
        slack_user_id="U_COACH",
    )


@pytest.fixture
def coach_no_slack(db):
    return Coach.objects.create(
        first_name="NoSlack",
        last_name="Coach",
        email="coach_noslack@example.com",
        slack_user_id="",
    )


@pytest.fixture
def bl_staff_user(db):
    return User.objects.create_user(
        email="bl@example.com",
        password="x",
        first_name="BL",
        last_name="Staff",
        is_staff=True,
    )


@pytest.fixture
def bl_contact(bl_staff_user):
    return BeginnerLuftStaff.objects.create(user=bl_staff_user, slack_user_id="U_BL")


@pytest.fixture
def bl_contact_no_slack(db):
    user = User.objects.create_user(
        email="bl_noslack@example.com",
        password="x",
        first_name="BLNoSlack",
        last_name="Staff",
        is_staff=True,
    )
    return BeginnerLuftStaff.objects.create(user=user, slack_user_id="")


@pytest.fixture
def rtc_with_slack(matching_attempt, coach_with_slack):
    return RequestToCoach.objects.create(
        matching_attempt=matching_attempt,
        coach=coach_with_slack,
        priority=10,
        ue=40,
        deadline_at=timezone.now() + datetime.timedelta(days=2),
    )


@pytest.fixture
def rtc_no_slack(matching_attempt, coach_no_slack):
    return RequestToCoach.objects.create(
        matching_attempt=matching_attempt,
        coach=coach_no_slack,
        priority=20,
        ue=40,
        deadline_at=timezone.now() + datetime.timedelta(days=2),
    )


@pytest.fixture
def matching_attempt_with_coach(participant, coach_with_slack, bl_contact):
    return MatchingAttempt.objects.create(
        participant=participant,
        ue=48,
        matched_coach=coach_with_slack,
        bl_contact=bl_contact,
        intro_call_deadline_at=timezone.now() + datetime.timedelta(days=3),
    )


@pytest.fixture
def matching_attempt_no_coach_slack(participant, coach_no_slack, bl_contact):
    return MatchingAttempt.objects.create(
        participant=participant,
        ue=48,
        matched_coach=coach_no_slack,
        bl_contact=bl_contact,
    )


@pytest.fixture
def matching_attempt_no_bl_slack(participant, coach_with_slack, bl_contact_no_slack):
    return MatchingAttempt.objects.create(
        participant=participant,
        ue=48,
        matched_coach=coach_with_slack,
        bl_contact=bl_contact_no_slack,
    )


@pytest.fixture
def mock_slack_client():
    """Pre-configured WebClient mock: opens DM → C12345, postMessage → ok."""
    client = MagicMock()
    client.conversations_open.return_value = {"channel": {"id": "C12345"}}
    client.chat_postMessage.return_value = {"ok": True}
    return client
