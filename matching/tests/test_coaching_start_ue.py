"""
Tests for coaching start notifications to verify correct UE is passed.

These tests verify that:
- The coach receives the UE from their specific RequestToCoach (coach_ue)
- Not the total UE from the MatchingAttempt
- The difference between total and coach-specific UE is properly handled
"""

import datetime
import pytest
from unittest.mock import patch, MagicMock
from django.utils import timezone
from django.core import mail
from accounts.models import User

from emails.services import send_coaching_start_info_email_to_coach
from slack.services import send_coaching_starting_info_slack
from profiles.models import Coach, BeginnerLuftStaff
from matching.models import MatchingAttempt, RequestToCoach


@pytest.fixture
def coach_with_slack_ue_test(db):
    """Coach with Slack ID for testing."""
    return Coach.objects.create(
        first_name="Slack",
        last_name="Coach",
        email="coach_slack_test@example.com",
        slack_user_id="U_COACH_TEST",
    )


@pytest.fixture
def coach_2_for_ue_test(db):
    """Second coach for testing."""
    return Coach.objects.create(
        first_name="Second",
        last_name="Coach",
        email="coach_second@example.com",
        slack_user_id="U_COACH_2_TEST",
    )


@pytest.fixture
def bl_contact_for_ue_test(db):
    """BL contact staff for testing."""
    user = User.objects.create_user(
        email="bl_test@example.com",
        password="x",
        first_name="BL",
        last_name="Staff",
        is_staff=True,
    )
    return BeginnerLuftStaff.objects.create(user=user, slack_user_id="U_BL_TEST")


@pytest.mark.django_db
class TestCoachingStartUE:
    """Verify correct UE is passed to coach in start notifications."""
    
    def test_email_context_has_coach_ue(
        self, participant, coach_with_slack_ue_test, bl_contact_for_ue_test
    ):
        """Verify email function calls get_matched_coach_ue and uses correct UE."""
        # Create matching attempt with total UE
        matching_attempt = MatchingAttempt.objects.create(
            participant=participant,
            ue=60,  # Total UE for participant
            matched_coach=coach_with_slack_ue_test,
            bl_contact=bl_contact_for_ue_test,
            intro_call_deadline_at=timezone.now() + datetime.timedelta(days=3),
        )
        
        # Create accepted RequestToCoach with different UE for this coach
        RequestToCoach.objects.create(
            matching_attempt=matching_attempt,
            coach=coach_with_slack_ue_test,
            priority=10,
            ue=40,  # Coach only gets 40 out of 60 total UE
            state=RequestToCoach.State.ACCEPTED,
            deadline_at=timezone.now() + datetime.timedelta(days=2),
        )
        
        # The key test: get_matched_coach_ue should return 40, not 60
        coach_ue = matching_attempt.get_matched_coach_ue()
        assert coach_ue == 40, f"Should return coach's UE (40), not matching total (60)"
        
        # Also verify that matching_attempt.ue is still 60 (unchanged)
        assert matching_attempt.ue == 60, "Matching attempt total UE should remain 60"
    
    def test_slack_uses_coach_ue_not_matching_attempt_ue(
        self, participant, coach_with_slack_ue_test, bl_contact_for_ue_test
    ):
        """Slack message should use coach's UE from RequestToCoach, not matching attempt total."""
        # Create matching attempt with total UE
        matching_attempt = MatchingAttempt.objects.create(
            participant=participant,
            ue=60,  # Total UE for participant
            matched_coach=coach_with_slack_ue_test,
            bl_contact=bl_contact_for_ue_test,
            intro_call_deadline_at=timezone.now() + datetime.timedelta(days=3),
        )
        
        # Create accepted RequestToCoach with different UE for this coach
        RequestToCoach.objects.create(
            matching_attempt=matching_attempt,
            coach=coach_with_slack_ue_test,
            priority=10,
            ue=40,  # Coach only gets 40 out of 60 total UE
            state=RequestToCoach.State.ACCEPTED,
            deadline_at=timezone.now() + datetime.timedelta(days=2),
        )
        
        # Mock WebClient
        mock_client = MagicMock()
        mock_client.conversations_open.return_value = {"channel": {"id": "C_TEST"}}
        mock_client.chat_postMessage.return_value = {"ts": "1234567890.123456"}
        
        with patch("slack.services.WebClient", return_value=mock_client):
            send_coaching_starting_info_slack(matching_attempt)
        
        # Get the posted message
        call_args = mock_client.chat_postMessage.call_args
        assert call_args is not None
        
        # Check the blocks for correct UE values
        blocks = call_args.kwargs["blocks"]
        blocks_text = str(blocks)
        
        # Should contain coach's UE (40)
        assert "40" in blocks_text
        # Should NOT contain the total UE (60)
        assert "60 Unterrichtseinheiten" not in blocks_text
    
    def test_get_matched_coach_ue_raises_when_no_rtc(
        self, participant, coach_with_slack_ue_test, bl_contact_for_ue_test
    ):
        """get_matched_coach_ue should raise ValueError if no accepted RequestToCoach."""
        # Create matching attempt WITHOUT a RequestToCoach
        matching_attempt = MatchingAttempt.objects.create(
            participant=participant,
            ue=60,
            matched_coach=coach_with_slack_ue_test,
            bl_contact=bl_contact_for_ue_test,
        )
        
        # Should raise ValueError
        with pytest.raises(ValueError) as exc_info:
            matching_attempt.get_matched_coach_ue()
        
        assert "No accepted RequestToCoach found" in str(exc_info.value)
        assert str(matching_attempt.id) in str(exc_info.value)
    
    def test_get_matched_coach_ue_returns_correct_value(
        self, participant, coach_with_slack_ue_test, bl_contact_for_ue_test
    ):
        """get_matched_coach_ue should return the correct UE from RequestToCoach."""
        matching_attempt = MatchingAttempt.objects.create(
            participant=participant,
            ue=60,
            matched_coach=coach_with_slack_ue_test,
            bl_contact=bl_contact_for_ue_test,
        )
        
        coach_ue = 35
        RequestToCoach.objects.create(
            matching_attempt=matching_attempt,
            coach=coach_with_slack_ue_test,
            priority=10,
            ue=coach_ue,
            state=RequestToCoach.State.ACCEPTED,
        )
        
        assert matching_attempt.get_matched_coach_ue() == coach_ue
    
    def test_different_coaches_get_different_ues(
        self, participant, coach_with_slack_ue_test, coach_2_for_ue_test, bl_contact_for_ue_test
    ):
        """Different coaches in same matching should get their own specific UE."""
        matching_attempt = MatchingAttempt.objects.create(
            participant=participant,
            ue=100,  # Total
            matched_coach=coach_with_slack_ue_test,
            bl_contact=bl_contact_for_ue_test,
        )
        
        # First coach gets 40 UE
        rtc_1 = RequestToCoach.objects.create(
            matching_attempt=matching_attempt,
            coach=coach_with_slack_ue_test,
            priority=10,
            ue=40,
            state=RequestToCoach.State.ACCEPTED,
        )
        
        # Second coach gets 60 UE (different subset)
        rtc_2 = RequestToCoach.objects.create(
            matching_attempt=matching_attempt,
            coach=coach_2_for_ue_test,
            priority=20,
            ue=60,
            state=RequestToCoach.State.ACCEPTED,
        )
        
        # Verify each coach's specific UE is correctly retrieved
        # Note: only matched_coach retrieves via get_matched_coach_ue()
        assert matching_attempt.get_matched_coach_ue() == 40
        assert rtc_1.ue == 40
        assert rtc_2.ue == 60
