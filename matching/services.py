import datetime

from django.db import transaction, IntegrityError
from django.core.exceptions import ValidationError

from accounts.models import User

from matching.models import MatchingAttempt, MatchingAttemptEvent, RequestToCoach, RequestToCoachEvent
from profiles.models import Participant, Coach


def create_matching_attempt(participant: Participant, ue: int, start_date: datetime.date, background_information: str, coaching_target: str, created_by: User):
    attempt = MatchingAttempt.objects.create(
        participant=participant,
        ue=ue,
        start_date=start_date,
        background_information=background_information,
        coaching_target=coaching_target,
        created_by=created_by,
    )

    MatchingAttemptEvent.objects.create(
        matching_attempt=attempt,
        event_type=MatchingAttemptEvent.EventType.CREATED,
        triggered_by=MatchingAttemptEvent.TriggeredBy.STAFF,
        triggered_by_user=created_by,
    )

    return attempt
  
def create_request_to_coach(matching_attempt: MatchingAttempt, coach: Coach, priority: int, ue: int, triggered_by: str, triggered_by_user: User = None, max_number_of_requests: int = 3):
    
    if triggered_by not in [RequestToCoachEvent.TriggeredBy.SYSTEM, RequestToCoachEvent.TriggeredBy.STAFF]:
        raise ValueError("Invalid value for triggered_by. Must be either 'system' or 'staff'.")
    
    if triggered_by == RequestToCoachEvent.TriggeredBy.STAFF and not triggered_by_user:
        raise ValueError("triggered_by_user must be provided when triggered_by is 'staff'.")
    
    # Basic server-side validation to avoid races and provide clearer errors
    if priority is None or int(priority) < 1:
        raise ValidationError("priority must be an integer >= 1")
    
    if ue is None or int(ue) < 1:
        raise ValidationError("ue (Unterrichtseinheiten) must be an integer >= 1")

    if matching_attempt.coach_requests.filter(priority=priority).exists():
        raise ValidationError("priority already exists for this matching attempt")

    try:
        rtc = RequestToCoach.objects.create(
            matching_attempt=matching_attempt,
            coach=coach,
            priority=priority,
            ue=ue,
            max_number_of_requests=max_number_of_requests,
        )
    except IntegrityError as exc:
        # Re-raise as ValidationError for callers that expect validation-style errors
        raise ValidationError("Could not create RequestToCoach: integrity error") from exc

    RequestToCoachEvent.objects.create(
        request=rtc,
        event_type=RequestToCoachEvent.EventType.CREATED,
        triggered_by=triggered_by,
        triggered_by_user=triggered_by_user,
    )

    return rtc