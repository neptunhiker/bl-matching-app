import pytest

from matching.models import CoachActionToken, MatchingAttempt, MatchingAttemptEvent, RequestToCoach, MatchingAttemptTransition, RequestToCoachTransition, RequestToCoachEvent

from matching import services

class TestIntegration:
    @pytest.mark.django_db
    def test_full_matching_flow(self, participant, coach, coach_2, coach_3, staff_user):
        
        # CREATE MATCHING ATTEMPT
        ma = services.create_matching_attempt(
            participant=participant,
            created_by=staff_user,
        )
        
        # status assertions
        assert ma.status == MatchingAttempt.Status.IN_PREPARATION
        
        # field assertions
        assert ma.participant == participant
        assert ma.created_by == staff_user
        
        # event assertions
        assert MatchingAttemptEvent.objects.filter(matching_attempt=ma, event_type=MatchingAttemptEvent.EventType.CREATED).exists()
        
        # ADD COACH REQUEST NUMBER 1
        rtc1 = services.create_request_to_coach(
            matching_attempt=ma,
            coach=coach,
            priority=10,
            triggered_by=RequestToCoachEvent.TriggeredBy.STAFF,
            triggered_by_user=staff_user,
        )
        
        # status assertions 
        assert ma.status == MatchingAttempt.Status.IN_PREPARATION
        assert rtc1.status == RequestToCoach.Status.IN_PREPARATION
        
        # field assertions
        assert rtc1.matching_attempt == ma
        assert rtc1.coach == coach
        assert rtc1.priority == 10

        # event assertions
        event1 = RequestToCoachEvent.objects.filter(request=rtc1, event_type=RequestToCoachEvent.EventType.CREATED).first()
        assert event1 is not None
        assert event1.triggered_by == RequestToCoachEvent.TriggeredBy.STAFF
        assert event1.triggered_by_user == staff_user
        
        # transition assertions
        assert MatchingAttemptTransition.objects.all().count() == 0
        assert RequestToCoachTransition.objects.all().count() == 0
        
        # ADD COACH REQUEST NUMBER 2
        rtc2 = services.create_request_to_coach(
            matching_attempt=ma,
            coach=coach_2,
            priority=20,
            triggered_by=RequestToCoachEvent.TriggeredBy.STAFF,
            triggered_by_user=staff_user,
        )
        
        # status assertions
        assert ma.status == MatchingAttempt.Status.IN_PREPARATION
        assert rtc2.status == RequestToCoach.Status.IN_PREPARATION
        
        # field assertions
        assert rtc2.matching_attempt == ma
        assert rtc2.coach == coach_2
        assert rtc2.priority == 20

        # event assertions
        event2 = RequestToCoachEvent.objects.filter(request=rtc2, event_type=RequestToCoachEvent.EventType.CREATED).first()
        assert event2 is not None
        assert event2.triggered_by == RequestToCoachEvent.TriggeredBy.STAFF
        assert event2.triggered_by_user == staff_user
        
        # transition assertions
        assert MatchingAttemptTransition.objects.all().count() == 0
        assert RequestToCoachTransition.objects.all().count() == 0

        
        # ADD COACH REQUEST NUMBER 3
        rtc3 = services.create_request_to_coach(
            matching_attempt=ma,
            coach=coach_3,
            priority=30,
            triggered_by=RequestToCoachEvent.TriggeredBy.STAFF,
            triggered_by_user=staff_user,
        )
        
        # status assertions
        assert ma.status == MatchingAttempt.Status.IN_PREPARATION
        assert rtc3.status == RequestToCoach.Status.IN_PREPARATION
        
        # field assertions
        assert rtc3.matching_attempt == ma
        assert rtc3.coach == coach_3
        assert rtc3.priority == 30
        
        # event assertions
        event3 = RequestToCoachEvent.objects.filter(request=rtc3, event_type=RequestToCoachEvent.EventType.CREATED).first()
        assert event3 is not None
        assert event3.triggered_by == RequestToCoachEvent.TriggeredBy.STAFF
        assert event3.triggered_by_user == staff_user
        
        # transition assertions
        assert MatchingAttemptTransition.objects.all().count() == 0
        assert RequestToCoachTransition.objects.all().count() == 0
        
        # START MATCHING ATTEMPT
        ma = ma.start_matching(triggered_by_user=staff_user)
        
        # status assertions
        assert ma.status == MatchingAttempt.Status.READY_FOR_MATCHING
        assert rtc1.status == RequestToCoach.Status.IN_PREPARATION
        assert rtc2.status == RequestToCoach.Status.IN_PREPARATION
        assert rtc3.status == RequestToCoach.Status.IN_PREPARATION
        
        # event assertions
        event4 = MatchingAttemptEvent.objects.filter(matching_attempt=ma, event_type=MatchingAttemptEvent.EventType.STARTED).first()
        assert event4 is not None
        assert event4.triggered_by == MatchingAttemptEvent.TriggeredBy.STAFF
        assert event4.triggered_by_user == staff_user
        
        # transition assertions
        ma_tr_1 = MatchingAttemptTransition.objects.filter(matching_attempt=ma).first()
        assert ma_tr_1 is not None
        assert ma_tr_1.from_status == MatchingAttempt.Status.IN_PREPARATION
        assert ma_tr_1.to_status == MatchingAttempt.Status.READY_FOR_MATCHING
        assert MatchingAttemptTransition.objects.filter(matching_attempt=ma).count() == 1
        
        assert RequestToCoachTransition.objects.all().count() == 0
        
        # ENABLE AUTOMATION
        ma.enable_automation(triggered_by_user=staff_user)
        
        # status assertions
        assert ma.status == MatchingAttempt.Status.READY_FOR_MATCHING
        assert rtc1.status == RequestToCoach.Status.IN_PREPARATION
        assert rtc2.status == RequestToCoach.Status.IN_PREPARATION
        assert rtc3.status == RequestToCoach.Status.IN_PREPARATION
        
        # field assertions
        assert ma.automation_enabled == True
        
        # event assertions
        event5 = MatchingAttemptEvent.objects.filter(matching_attempt=ma, event_type=MatchingAttemptEvent.EventType.AUTOMATION_ENABLED).first()
        assert event5 is not None
        
        # transition assertions
        assert MatchingAttemptTransition.objects.filter(matching_attempt=ma).count() == 1
        assert RequestToCoachTransition.objects.all().count() == 0
        
        # SEND FIRST COACH REQUEST
        rtc1.send_request(triggered_by="system")
        ma.refresh_from_db()
        rtc1.refresh_from_db()
        
        # status assertions
        assert ma.status == MatchingAttempt.Status.MATCHING_ONGOING
        assert rtc1.status == RequestToCoach.Status.AWAITING_REPLY
        assert rtc2.status == RequestToCoach.Status.IN_PREPARATION
        assert rtc3.status == RequestToCoach.Status.IN_PREPARATION
        
        # field assertions
        assert rtc1.first_sent_at is not None
        assert rtc1.last_sent_at is not None
        
        # event assertions
        event6 = RequestToCoachEvent.objects.filter(request=rtc1, event_type=RequestToCoachEvent.EventType.REQUEST_SENT).first()
        assert event6 is not None
        assert event6.triggered_by == RequestToCoachEvent.TriggeredBy.SYSTEM
        assert event6.triggered_by_user is None
        
        # transition assertions
        assert MatchingAttemptTransition.objects.filter(matching_attempt=ma).count() == 2
        assert RequestToCoachTransition.objects.filter(request=rtc1).count() == 1
        
        # send reminder for coach request number 1
        
        # deadlines passes
        
        # send coach request to coach number 2
        
        # coch number 2 accepts
        
        