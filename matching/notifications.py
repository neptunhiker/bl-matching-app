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
from .locks import _get_locked_request_to_coach
from .models import RequestToCoach, RequestToCoachEvent, MatchingAttempt, MatchingAttemptEvent
from .tokens import generate_coach_action_tokens
from .utils import add_business_hours

logger = logging.getLogger(__name__)





def _build_email_context(
    rtc: RequestToCoach,
    accept_url: str,
    decline_url: str
) -> Dict[str, Any]:
    return {
        "recipient_name": rtc.coach.first_name,
        "participant_name": rtc.matching_attempt.participant.first_name,
        "author": getattr(settings, "SYSTEM_EMAIL_NAME", "BeginnerLuft Roboti"),
        "accept_url": accept_url,
        "decline_url": decline_url,
        "learn_more_url": settings.SITE_URL.rstrip("/") + reverse("landing"),
        "deadline": rtc.deadline_at,
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
def send_reminder_coach_request_email(rtc: RequestToCoach, email_trigger: str = EmailLog.EmailTrigger.AUTOMATED) -> RequestToCoach:
    """Send a reminder email to the coach and update status accordingly."""
    
    rtc = _get_locked_request_to_coach(rtc)
    
    if not rtc.can_send_reminder():
        raise ValidationError(f"Cannot send reminder email for RequestToCoach {rtc.id} in its current state. Status: {rtc.get_status_display()}, Deadline passed: {rtc.is_deadline_passed()}, Requests sent: {rtc.requests_sent}.")
    
    now = timezone.now()

    _send_request_email(rtc, 
                        subject=f"Reminder: Matching-Anfrage für {rtc.matching_attempt.participant.first_name} {rtc.matching_attempt.participant.last_name}", 
                        template_name='emails/reminder_match_request_to_coach.html',
                        triggered_by=email_trigger,
    )
    
    rtc.last_sent_at = now
    rtc.requests_sent += 1
    rtc.save()
    
    # The RTC is now in the same state as it was when the first email was sent, so we don't transition it again. The only difference is the updated timestamps and request count.
        
    return rtc

@transaction.atomic
def send_connecting_email(request_to_coach: RequestToCoach, email_trigger: str = EmailLog.EmailTrigger.AUTOMATED):
    """Send match-confirmed emails to both the coach and the participant."""
    pass
    
    # logger.info(
    #     "send_connecting_email called for RequestToCoach pk=%s (coach=%s, participant=%s)",
    #     request_to_coach.pk,
    #     request_to_coach.coach,
    #     request_to_coach.matching_attempt.participant,
    # )
    # author = "BeginnerLuft Roboti"
    # coach = request_to_coach.coach
    # participant = request_to_coach.matching_attempt.participant

    # # Collect participant's preferred coaching formats
    # formats = []
    # if participant.coaching_format_online:
    #     formats.append("Online")
    # if participant.coaching_format_presence:
    #     formats.append("Präsenz")
    # if participant.coaching_format_hybrid:
    #     formats.append("Hybrid")

    # # --- Email to coach ---
    # logger.debug("send_connecting_email: sending to coach %s (%s)", coach, coach.email)
    # send_email(
    #     to=coach.email,
    #     subject=f"Dein Matching mit {participant} ist bestätigt!",
    #     template_name='emails/connecting_email.html',
    #     email_trigger=email_trigger,
    #     sent_by="to be defined",
    #     context={
    #         'recipient_name': coach.first_name,
    #         'partner_name': str(participant),
    #         'partner_email': participant.email,
    #         'partner_city': participant.city,
    #         'coaching_formats': formats,
    #         'is_coach': True,
    #         'author': author,
    #     },
    #     request_to_coach=request_to_coach,
    # )

    # # --- Email to participant ---
    # logger.debug("send_connecting_email: sending to participant %s (%s)", participant, participant.email)
    # send_email(
    #     to=participant.email,
    #     subject=f"Dein Matching mit {coach.full_name} ist bestätigt!",
    #     template_name='emails/connecting_email.html',
    #     context={
    #         'recipient_name': participant.first_name,
    #         'partner_name': coach.full_name,
    #         'partner_email': coach.email,
    #         'is_coach': False,
    #         'author': author,
    #     },
    #     matching_attempt=request_to_coach.matching_attempt,
    # )