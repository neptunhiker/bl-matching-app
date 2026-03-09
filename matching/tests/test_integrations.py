import pytest

from matching.models import CoachActionToken, MatchingAttempt, MatchingAttemptEvent, RequestToCoach, MatchingAttemptTransition, RequestToCoachTransition, RequestToCoachEvent

from matching import services

class TestIntegration:
    @pytest.mark.django_db
    def test_full_matching_flow(self, participant, coach, coach_user, staff_user):
        
        # create matching attempt
        ma = services.create_matching_attempt(
            participant=participant,
            created_by=staff_user,
        )
        
        assert ma.status == MatchingAttempt.Status.IN_PREPARATION
        assert ma.participant == participant
        assert ma.created_by == staff_user
        
        assert MatchingAttemptEvent.objects.filter(matching_attempt=ma, event_type=MatchingAttemptEvent.EventType.CREATED).exists()
        
        # add coach request number 1
        
        # add coach request number 2
        
        # add coach request number 3
        
        # start matching attempt
        
        # enable automation
        
        # send first coach request
        
        # send reminder for coach request number 1
        
        # deadlines passes
        
        # send coach request to coach number 2
        
        # coch number 2 accepts
        
        