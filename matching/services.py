import datetime
import logging 

from django.db import transaction, IntegrityError
from django.core.exceptions import ValidationError

from accounts.models import User

from profiles.models import Participant, Coach

logger = logging.getLogger(__name__)

def create_matching_attempt(participant, ue, bl_contact, created_by):
    from matching.models import MatchingAttempt, MatchingEvent, TriggeredByOptions
    from matching.services import create_matching_event
    from profiles.models import Participant

    with transaction.atomic():

        # 🔒 lock the participant row (guarantees serialization)
        Participant.objects.select_for_update().get(pk=participant.pk)

        existing = MatchingAttempt.objects.filter(
            participant=participant,
            state__in=MatchingAttempt.ACTIVESTATES,
        ).first()

        if existing:
            raise ValidationError(existing)  

        attempt = MatchingAttempt.objects.create(
            participant=participant,
            ue=ue,
            bl_contact=bl_contact,
            created_by=created_by,
        )

        create_matching_event(
            matching_attempt=attempt,
            event_type=MatchingEvent.EventType.CREATED,
            triggered_by=TriggeredByOptions.STAFF,
            triggered_by_user=created_by,
        )

    return attempt
  
def create_request_to_coach(matching_attempt, coach: Coach, priority: int, ue: int, triggered_by: str, triggered_by_user: User = None):
    
    from matching.models import RequestToCoach, MatchingEvent
    
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
        )
        
        create_matching_event(
            matching_attempt=matching_attempt,
            event_type=MatchingEvent.EventType.RTC_CREATED,
            triggered_by=triggered_by,
            triggered_by_user=triggered_by_user,
            payload={
                "rtc_id": str(rtc.id),
                "coach_id": str(coach.id),
                "priority": priority,
                "ue": ue,
            }
        )
    except IntegrityError as exc:
        # Re-raise as ValidationError for callers that expect validation-style errors
        raise ValidationError("Could not create RequestToCoach: integrity error") from exc

    return rtc

def create_matching_event(
    matching_attempt,
    event_type,
    triggered_by,
    triggered_by_user=None,
    payload=None,
    request_to_coach=None,
):
    """
    Create a MatchingEvent with strict domain validation.

    Args:
        matching_attempt: MatchingAttempt instance
        event_type: MatchingEvent.EventType (enum value)
        triggered_by: MatchingEvent.TriggeredBy (enum value)
        triggered_by_user: Optional User instance (required for STAFF/COACH)
        payload: Optional dict with additional context

    Returns:
        MatchingEvent instance
    """

    payload = payload or {}
    from matching.models import MatchingEvent, TriggeredByOptions

    # --- Validate event_type ---
    if event_type not in MatchingEvent.EventType.values:
        raise ValueError(f"Invalid event_type: {event_type}")

    # --- Validate triggered_by + user consistency ---
    if triggered_by == TriggeredByOptions.COACH:
        if not triggered_by_user:
            raise ValueError("Coach events require triggered_by_user")

    elif triggered_by == TriggeredByOptions.STAFF:
        if not triggered_by_user:
            raise ValueError("Staff events require triggered_by_user")
        if not (triggered_by_user.is_staff or triggered_by_user.is_superuser):
            raise ValueError("triggered_by_user must be staff or superuser")

    elif triggered_by == TriggeredByOptions.SYSTEM:
        if triggered_by_user:
            raise ValueError("System events must not include triggered_by_user")
        
    elif triggered_by == TriggeredByOptions.PARTICIPANT:
        if not payload.get("participant"):
            raise ValueError("Events triggered by a participant must include 'participant' in payload")

    else:
        print({triggered_by== TriggeredByOptions.STAFF})
        raise ValueError(f"Invalid triggered_by: {triggered_by}")

    # --- Create event ---
    event = MatchingEvent.objects.create(
        matching_attempt=matching_attempt,
        event_type=event_type,
        triggered_by=triggered_by,
        triggered_by_user=triggered_by_user,
        payload=payload,
        request_to_coach=request_to_coach,
    )
    
    logger.info(f"Created MatchingEvent: {event_type}, triggered by {triggered_by}, (user: {triggered_by_user}) with payload: {payload}")

    return event

def trigger_start_matching(matching_attempt, triggered_by_user):
    
    from matching.models import MatchingEvent, TriggeredByOptions
    
    if not matching_attempt.automation_enabled:
        raise ValidationError("Automation must be enabled to start matching.")
    
    create_matching_event(
        matching_attempt=matching_attempt,
        event_type=MatchingEvent.EventType.STARTED,
        triggered_by=TriggeredByOptions.STAFF,
        triggered_by_user=triggered_by_user,
    )
    
def trigger_resume_matching(matching_attempt, triggered_by_user):
    
    from matching.models import MatchingEvent, TriggeredByOptions
    
    if not matching_attempt.automation_enabled:
        raise ValidationError("Automation must be enabled to start matching.")
    
    create_matching_event(
        matching_attempt=matching_attempt,
        event_type=MatchingEvent.EventType.RESUMED,
        triggered_by=TriggeredByOptions.STAFF,
        triggered_by_user=triggered_by_user,
    )


def accept_or_decline_request_to_coach(rtc, accept: bool, response_time: datetime.datetime, responded_by_user: User):
    from matching.models import MatchingEvent, TriggeredByOptions
    from matching.services import create_matching_event
        
    if response_time > rtc.deadline_at:
        on_time = False
    else:
        on_time = True
        
    if on_time:
    
        with transaction.atomic():
                
            if accept:
                event_type = MatchingEvent.EventType.RTC_ACCEPTED
                rtc.accept(on_time=on_time)
                rtc.save()  # Ensure RTC state change is saved before event is created
                rtc.matching_attempt.matched_coach = rtc.coach
                rtc.matching_attempt.save(update_fields=["matched_coach"])
            else:
                event_type = MatchingEvent.EventType.RTC_DECLINED
                rtc.reject()
                rtc.save()  # Ensure RTC state change is saved before event is created

            create_matching_event(
                matching_attempt=rtc.matching_attempt,
                event_type=event_type,
                triggered_by=TriggeredByOptions.COACH,
                triggered_by_user=responded_by_user,
                payload={
                    "rtc_id": str(rtc.id),
                    "coach_id": str(rtc.coach_id) if rtc.coach_id is not None else None,
                    "response_time": response_time.isoformat(),
                    "on_time": on_time,
                    "deadline_at": rtc.deadline_at.isoformat(),
                    "accept": accept,
                }
            )
    else:
        create_matching_event(
            matching_attempt=rtc.matching_attempt,
            event_type=MatchingEvent.EventType.RESPONDED_LATE_TO_RTC,
            triggered_by=TriggeredByOptions.COACH,
            triggered_by_user=responded_by_user,
            payload={
                "rtc_id": str(rtc.id),
                "coach_id": str(rtc.coach_id) if rtc.coach_id is not None else None,
                "response_time": response_time.isoformat(),
                "on_time": on_time,
                "deadline_at": rtc.deadline_at.isoformat(),
                "accept": accept,
            }
        )

def continue_matching_after_rtc_accepted(matching_attempt):
    from matching.models import MatchingEvent, TriggeredByOptions

    create_matching_event(
        matching_attempt=matching_attempt,
        event_type=MatchingEvent.EventType.INTRO_CALL_REQUEST_SENT_TO_COACH,
        triggered_by=TriggeredByOptions.SYSTEM,
        triggered_by_user=None,
    )
    
    create_matching_event(
        matching_attempt=matching_attempt,
        event_type=MatchingEvent.EventType.INTRO_CALL_INFO_SENT_TO_PARTICIPANT,
        triggered_by=TriggeredByOptions.SYSTEM,
        triggered_by_user=None,
    )
    
def continue_matching_after_intro_call_feedback_from_coach(matching_attempt):
    from matching.models import MatchingEvent, TriggeredByOptions

    create_matching_event(
        matching_attempt=matching_attempt,
        event_type=MatchingEvent.EventType.INTRO_CALL_FEEDBACK_REQUESTED_FROM_PARTICIPANT,
        triggered_by=TriggeredByOptions.SYSTEM,
        triggered_by_user=None,
    )
    
def continue_matching_after_participant_responded_to_intro_call_feedback(matching_attempt, coaching_can_start: bool, response_time: datetime.datetime, responded_by_participant: Participant):
    from matching.models import MatchingEvent, TriggeredByOptions

    participant = responded_by_participant
    
    if coaching_can_start:
        
        create_matching_event(
            matching_attempt=matching_attempt,
            event_type=MatchingEvent.EventType.COACHING_CAN_START_FEEDBACK_RECEIVED_FROM_PARTICIPANT,
            triggered_by=TriggeredByOptions.PARTICIPANT,
            payload={
                "response_time": response_time.isoformat(),
                "coaching_can_start": coaching_can_start,
                "participant": participant.full_name,
            }
        )
    else:
        create_matching_event(
            matching_attempt=matching_attempt,
            event_type=MatchingEvent.EventType.CLARIFICATION_NEEEDED_FEEDBACK_RECEIVED_FROM_PARTICIPANT,
            triggered_by=TriggeredByOptions.PARTICIPANT,
            payload={
                "response_time": response_time.isoformat(),
                "coaching_can_start": coaching_can_start,
                "participant": participant.full_name,
            }
        )
        

        
def send_out_official_coaching_start_notification(matching_attempt):
    from matching.models import MatchingEvent, TriggeredByOptions

    create_matching_event(
        matching_attempt=matching_attempt,
        event_type=MatchingEvent.EventType.COACHING_START_INFO_SENT_TO_PARTICIPANT,
        triggered_by=TriggeredByOptions.SYSTEM,
        triggered_by_user=None,
    )
    
    create_matching_event(
        matching_attempt=matching_attempt,
        event_type=MatchingEvent.EventType.COACHING_START_INFO_SENT_TO_COACH,
        triggered_by=TriggeredByOptions.SYSTEM,
        triggered_by_user=None,
    )
    

def send_clarification_needed_notifications(matching_attempt):
    from matching.models import MatchingEvent, TriggeredByOptions

    create_matching_event(
        matching_attempt=matching_attempt,
        event_type=MatchingEvent.EventType.ESCALATION_NOTIFICATION_SENT_TO_STAFF,
        triggered_by=TriggeredByOptions.SYSTEM,
        triggered_by_user=None,
    )
    
    create_matching_event(
        matching_attempt=matching_attempt,
        event_type=MatchingEvent.EventType.INFORMATION_ABOUT_CLARIFICATION_SENT_TO_COACH,
        triggered_by=TriggeredByOptions.SYSTEM,
        triggered_by_user=None,
    )
    
    
def cancel_matching(matching_attempt, triggered_by_user: User):
    
    from matching.models import MatchingEvent, TriggeredByOptions

    with transaction.atomic():
        matching_attempt.disable_automation(triggered_by_user)
        matching_attempt.cancel_matching()
        matching_attempt.save()
        
        create_matching_event(
            matching_attempt=matching_attempt,
            event_type=MatchingEvent.EventType.CANCELLED,
            triggered_by=TriggeredByOptions.STAFF,
            triggered_by_user=triggered_by_user,
        )
    
def manually_match_participant_to_coach(matching_attempt, coach: Coach, triggered_by_user: User):
    from matching.models import MatchingEvent, TriggeredByOptions

    with transaction.atomic():
        matching_attempt.disable_automation(triggered_by_user)
        matching_attempt.manually_match_with_coach(coach)
        matching_attempt.save()
        
        create_matching_event(
            matching_attempt=matching_attempt,
            event_type=MatchingEvent.EventType.MANUALLY_MATCHED_TO_COACH,
            triggered_by=TriggeredByOptions.STAFF,
            triggered_by_user=triggered_by_user,
            payload={
                "coach_id": str(coach.id),
                "Notiz": f"Coach {coach} manuell zugeordnet. Alle Automatisierungsschritte übersprungen.",
            }
        )
    
    
