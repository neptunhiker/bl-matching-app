from django.db import transaction

from accounts.models import User

from matching.models import MatchingAttempt, MatchingAttemptEvent, RequestToCoach, RequestToCoachEvent
from profiles.models import Participant, Coach


def create_matching_attempt(participant: Participant, created_by: User):
    attempt = MatchingAttempt.objects.create(
        participant=participant,
        created_by=created_by,
    )

    MatchingAttemptEvent.objects.create(
        matching_attempt=attempt,
        event_type=MatchingAttemptEvent.EventType.CREATED,
        triggered_by=MatchingAttemptEvent.TriggeredBy.STAFF,
        triggered_by_user=created_by,
    )

    return attempt
  
def create_request_to_coach(matching_attempt: MatchingAttempt, coach: Coach, priority: int, triggered_by: str, triggered_by_user: User = None):
    
    if triggered_by not in [RequestToCoachEvent.TriggeredBy.SYSTEM, RequestToCoachEvent.TriggeredBy.STAFF]:
        raise ValueError("Invalid value for triggered_by. Must be either 'system' or 'staff'.")
    
    if triggered_by == RequestToCoachEvent.TriggeredBy.STAFF and not triggered_by_user:
        raise ValueError("triggered_by_user must be provided when triggered_by is 'staff'.")
    
    rtc = RequestToCoach.objects.create(
        matching_attempt=matching_attempt,
        coach=coach,
        priority=priority,
    )

    RequestToCoachEvent.objects.create(
        request=rtc,
        event_type=RequestToCoachEvent.EventType.CREATED,
        triggered_by=triggered_by,
        triggered_by_user=triggered_by_user,
    )

    return rtc