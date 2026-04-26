from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from matching.models import RequestToCoach, MatchingAttempt

def _get_locked_request_to_coach(rtc: "RequestToCoach") -> "RequestToCoach":
    from matching.models import RequestToCoach
    return (
        RequestToCoach.objects
        .select_for_update()
        .select_related(
            "coach",
            "matching_attempt",
            "matching_attempt__participant",
        )
        .get(pk=rtc.pk)
    )
        
def _get_locked_matching_attempt(ma: "MatchingAttempt") -> "MatchingAttempt":
    from matching.models import MatchingAttempt
    return (
        MatchingAttempt.objects
        .select_for_update()
        .select_related(
            "participant",
        )
        .get(pk=ma.pk)
    )
