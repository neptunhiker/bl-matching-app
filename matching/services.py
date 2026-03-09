from matching.models import MatchingAttempt, MatchingAttemptEvent

def create_matching_attempt(participant, created_by=None):
    attempt = MatchingAttempt.objects.create(
        participant=participant,
        created_by=created_by,
    )

    MatchingAttemptEvent.objects.create(
        matching_attempt=attempt,
        event_type=MatchingAttemptEvent.EventType.CREATED,
        actor=created_by,
    )

    return attempt