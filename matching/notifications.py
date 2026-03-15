import logging
from typing import Dict, Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from django.db import transaction

from accounts.models import User
from emails.services import send_email
from emails.models import EmailLog
from matching.utils import get_urgency_message
from profiles.models import Coach
from slack.services import send_first_coach_request_slack, send_reminder_coach_request_slack, send_intro_call_request_slack
from .locks import _get_locked_request_to_coach, _get_locked_matching_attempt
from .models import RequestToCoach, RequestToCoachEvent, MatchingAttempt
from .tokens import generate_coach_action_tokens

logger = logging.getLogger(__name__)


def send_first_request_notification(request_to_coach: RequestToCoach, triggered_by: str="system", triggered_by_user: User = None):

    coach = request_to_coach.coach

    if coach.preferred_communication_channel == Coach.CommunicationChannel.SLACK:
        send_first_coach_request_slack(request_to_coach, triggered_by=triggered_by, triggered_by_user=triggered_by_user)
        
    elif coach.preferred_communication_channel == Coach.CommunicationChannel.EMAIL:
        send_first_coach_request_email(request_to_coach, triggered_by=triggered_by, triggered_by_user=triggered_by_user)
    else:
        raise ValueError(f"Unsupported communication channel for coach {coach}: {coach.preferred_communication_channel}")
    
def send_reminder_request_notification(request_to_coach: RequestToCoach, triggered_by: str="system", triggered_by_user: User = None):

    coach = request_to_coach.coach

    if coach.preferred_communication_channel == Coach.CommunicationChannel.SLACK:
        logger.debug(f"Sending reminder coach request notification via Slack for RequestToCoach to coach {coach} (user: {coach.user})")
        send_reminder_coach_request_slack(request_to_coach, triggered_by=triggered_by, triggered_by_user=triggered_by_user)
        
    elif coach.preferred_communication_channel == Coach.CommunicationChannel.EMAIL:
        send_reminder_coach_request_email(request_to_coach, triggered_by=triggered_by, triggered_by_user=triggered_by_user)
    else:
        raise ValueError(f"Unsupported communication channel for coach {coach}: {coach.preferred_communication_channel}")
    
def send_intro_call_request_notification(matching_attempt: MatchingAttempt, triggered_by: str="system", triggered_by_user: User = None):

    coach = matching_attempt.matched_coach

    if coach.preferred_communication_channel == Coach.CommunicationChannel.SLACK:
        send_intro_call_request_slack(matching_attempt, triggered_by=triggered_by, triggered_by_user=triggered_by_user)
        
    elif coach.preferred_communication_channel == Coach.CommunicationChannel.EMAIL:
        send_intro_call_request_email(matching_attempt, triggered_by=triggered_by, triggered_by_user=triggered_by_user)
    else:
        raise ValueError(f"Unsupported communication channel for coach {coach}: {coach.preferred_communication_channel}")
    
    # Inform participant
    send_intro_call_info_email_to_participant(matching_attempt, triggered_by=triggered_by, triggered_by_user=triggered_by_user)


def _build_email_context(
    rtc: RequestToCoach,
    accept_url: str,
    decline_url: str
) -> Dict[str, Any]:
    participant = rtc.matching_attempt.participant
    return {
        "recipient_name": rtc.coach.first_name,
        "participant_name": participant.first_name,
        "ue": rtc.ue,
        "author": getattr(settings, "SYSTEM_EMAIL_NAME", "BeginnerLuft Roboti"),
        "accept_url": accept_url,
        "decline_url": decline_url,
        "learn_more_url": settings.SITE_URL.rstrip("/") + reverse("participant_detail", kwargs={"pk": participant.pk}),
        "deadline": rtc.deadline_at,
        "start_date": rtc.matching_attempt.participant.start_date.strftime("%d.%m.%Y"),
    }
    
def _send_request_email(
        rtc: RequestToCoach,
        subject: str,
        template_name: str,
        triggered_by: str,
    ):
    accept_url, decline_url = generate_coach_action_tokens(rtc)

    context = _build_email_context(rtc, accept_url, decline_url)

    transaction.on_commit(
        lambda: send_email(
            to=rtc.coach.user.email,
            subject=subject,
            template_name=template_name,
            context=context,
            request_to_coach=rtc,
            sent_by=context["author"],
            triggered_by=triggered_by
        )   
    )
    

def send_first_coach_request_email(rtc: RequestToCoach, triggered_by: str="system", triggered_by_user: User = None) -> RequestToCoach:
    """Send the first coach request email and update status accordingly."""
    
    if triggered_by not in [RequestToCoachEvent.TriggeredBy.SYSTEM, RequestToCoachEvent.TriggeredBy.STAFF]:
        raise ValueError("Invalid value for triggered_by. Must be either 'system' or 'staff'.")
    if triggered_by == RequestToCoachEvent.TriggeredBy.STAFF and not triggered_by_user:
        raise ValueError("triggered_by_user must be provided when triggered_by is 'staff'.")
    
    
    rtc = _get_locked_request_to_coach(rtc)
    rtc.send_request(triggered_by=triggered_by, triggered_by_user=triggered_by_user)
    
    _send_request_email(rtc, 
                        subject=f"Matching-Anfrage für {rtc.matching_attempt.participant.first_name} {rtc.matching_attempt.participant.last_name}", 
                        template_name='emails/match_request_to_coach.html',
                        triggered_by=triggered_by,
    )        
    
    return rtc
    
@transaction.atomic
def send_reminder_coach_request_email(rtc: RequestToCoach, triggered_by: str="system", triggered_by_user: User = None) -> RequestToCoach:
    """Send a reminder email to the coach and update status accordingly."""
    
    if triggered_by not in [RequestToCoachEvent.TriggeredBy.SYSTEM, RequestToCoachEvent.TriggeredBy.STAFF]:
        raise ValueError("Invalid value for triggered_by. Must be either 'system' or 'staff'.")
    if triggered_by == RequestToCoachEvent.TriggeredBy.STAFF and not triggered_by_user:
        raise ValueError("triggered_by_user must be provided when triggered_by is 'staff'.")
    
    rtc = _get_locked_request_to_coach(rtc)
    
    rtc.send_reminder(triggered_by=triggered_by, triggered_by_user=triggered_by_user)
    

    _send_request_email(rtc, 
                        subject=f"Reminder: Matching-Anfrage für {rtc.matching_attempt.participant.first_name} {rtc.matching_attempt.participant.last_name}", 
                        template_name='emails/reminder_match_request_to_coach.html',
                        triggered_by=triggered_by,
    )
        
    return rtc


    
@transaction.atomic
def send_intro_call_request_email(matching_attempt: MatchingAttempt, triggered_by: str="system", triggered_by_user: User = None) -> MatchingAttempt:
    """Send an email to the coach to set up an intro call with the participant, and update status accordingly."""
    
    if triggered_by not in [RequestToCoachEvent.TriggeredBy.SYSTEM, RequestToCoachEvent.TriggeredBy.STAFF]:
        raise ValueError("Invalid value for triggered_by. Must be either 'system' or 'staff'.")
    
    if triggered_by == RequestToCoachEvent.TriggeredBy.STAFF and not triggered_by_user:
        raise ValueError("triggered_by_user must be provided when triggered_by is 'staff'.")
    
    matching_attempt = _get_locked_matching_attempt(matching_attempt)
    
    participant = matching_attempt.participant
    
    matching_attempt.send_intro_call_request(triggered_by=triggered_by, triggered_by_user=triggered_by_user)
    
    coach = matching_attempt.matched_coach
    context = {
        "recipient_name": coach.first_name,
        "participant_name": participant.first_name,
        "participant_email": participant.email,
        "learn_more_url": settings.SITE_URL.rstrip("/") + reverse("participant_detail", kwargs={"pk": participant.pk}),
        "urgency_message": get_urgency_message(participant, start_date=participant.start_date),
        "author": getattr(settings, "SYSTEM_EMAIL_NAME", "BeginnerLuft Roboti"),
    }
    
    transaction.on_commit(
        lambda: send_email(
            to=coach.user.email,
            subject=f"Kennenlernengespräch ansetzen mit {participant.first_name}",
            template_name='emails/intro_call_request_to_coach.html',
            context=context,
            matching_attempt=matching_attempt,
            sent_by=context["author"],
            triggered_by=triggered_by
            )
    )
        
    return matching_attempt


@transaction.atomic
def send_intro_call_info_email_to_participant(matching_attempt: MatchingAttempt, triggered_by: str="system", triggered_by_user: User = None) -> MatchingAttempt:
    """Send an email to the participant with information about the matched coach and next steps for the intro call."""
    
    if triggered_by not in [RequestToCoachEvent.TriggeredBy.SYSTEM, RequestToCoachEvent.TriggeredBy.STAFF]:
        raise ValueError("Invalid value for triggered_by. Must be either 'system' or 'staff'.")
    
    if triggered_by == RequestToCoachEvent.TriggeredBy.STAFF and not triggered_by_user:
        raise ValueError("triggered_by_user must be provided when triggered_by is 'staff'.")
    
    matching_attempt = _get_locked_matching_attempt(matching_attempt)
    
    participant = matching_attempt.participant
    
    matching_attempt.send_intro_call_info_to_participant(triggered_by=triggered_by, triggered_by_user=triggered_by_user)
    
    coach = matching_attempt.matched_coach
    context = {
        "participant": participant,
        "coach": coach,
        "participant_email": participant.email,
        "author": getattr(settings, "SYSTEM_EMAIL_NAME", "BeginnerLuft Roboti"),
    }
    
    transaction.on_commit(
        lambda: send_email(
            to=participant.email,
            subject=f"Wir haben einen Coach für dich gefunden 🎉",
            template_name='emails/intro_call_info_to_participant.html',
            context=context,
            matching_attempt=matching_attempt,
            sent_by=context["author"],
            triggered_by=triggered_by
            )
    )
        
    return matching_attempt