import logging

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

from accounts.models import User
from profiles.models import Coach
from emails.services import send_first_coach_request_email, send_reminder_coach_request_email, send_intro_call_request_email, send_intro_call_info_email_to_participant, send_coaching_start_info_email_to_coach, send_coaching_start_info_email_to_participant
from slack.services import send_first_coach_request_slack, send_reminder_coach_request_slack, send_intro_call_request_slack, send_coaching_starting_info_slack

from .models import RequestToCoach, RequestToCoachEvent, MatchingAttempt


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
        
        request_to_coach.send_reminder(triggered_by=triggered_by, triggered_by_user=triggered_by_user)
    
        
    elif coach.preferred_communication_channel == Coach.CommunicationChannel.EMAIL:
        send_reminder_coach_request_email(request_to_coach, triggered_by=triggered_by, triggered_by_user=triggered_by_user)
    else:
        raise ValueError(f"Unsupported communication channel for coach {coach}: {coach.preferred_communication_channel}")
    
def send_intro_call_request_notification(matching_attempt: MatchingAttempt, triggered_by: str="system", triggered_by_user: User = None):

    coach = matching_attempt.matched_coach

    if coach.preferred_communication_channel == Coach.CommunicationChannel.SLACK:
        send_intro_call_request_slack(matching_attempt, triggered_by=triggered_by, triggered_by_user=triggered_by_user)
        
    elif coach.preferred_communication_channel == Coach.CommunicationChannel.EMAIL:
        send_intro_call_request_email(matching_attempt)
    else:
        raise ValueError(f"Unsupported communication channel for coach {coach}: {coach.preferred_communication_channel}")
    
    # Inform participant
    send_intro_call_info_email_to_participant(matching_attempt, triggered_by=triggered_by, triggered_by_user=triggered_by_user)
    
def send_coaching_start_info_notification(matching_attempt: MatchingAttempt, triggered_by: str="system", triggered_by_user: User = None):

    coach = matching_attempt.matched_coach

    if coach.preferred_communication_channel == Coach.CommunicationChannel.SLACK:
        send_coaching_starting_info_slack(matching_attempt, triggered_by=triggered_by, triggered_by_user=triggered_by_user)
        
    elif coach.preferred_communication_channel == Coach.CommunicationChannel.EMAIL:
        send_coaching_start_info_email_to_coach(matching_attempt, triggered_by=triggered_by, triggered_by_user=triggered_by_user)
    else:
        raise ValueError(f"Unsupported communication channel for coach {coach}: {coach.preferred_communication_channel}")
    
    # Inform participant
    send_coaching_start_info_email_to_participant(matching_attempt, triggered_by=triggered_by, triggered_by_user=triggered_by_user)
