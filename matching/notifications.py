import logging
from typing import Dict, Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from django.db import transaction


from emails.services import send_email
from .locks import _get_locked_request_to_coach
from .models import RequestToCoach, RequestToCoachEvent, MatchingAttempt
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
    event_type: str,
    email_trigger: str = "automated",
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
            email_trigger=email_trigger,
        )   
    )
    
    RequestToCoachEvent.objects.create(
        request=rtc,
        event_type=event_type,
        triggered_by=email_trigger,
    )
    
@transaction.atomic
def send_first_coach_request_email(rtc: RequestToCoach, email_trigger: str = "automated") -> RequestToCoach:
    """Send the first coach request email and update status accordingly."""
    
    rtc = _get_locked_request_to_coach(rtc)
    
    if rtc.first_sent_at:
        raise ValidationError(f"First request email has already been sent on {rtc.first_sent_at}. Please send a reminder email instead.")
    
    if not rtc.can_send_request():
        raise ValidationError(f"Maximum number of request emails already sent ({rtc.requests_sent} of {rtc.max_number_of_requests}).")
    
    now = timezone.now()  
    
    if rtc.deadline_at is None:
        rtc.deadline_at = add_business_hours(
            now,
            getattr(settings, 'COACH_REQUEST_DEFAULT_DEADLINE_HOURS', 48),
        )

    _send_request_email(rtc, 
                        subject=f"Matching-Anfrage für {rtc.matching_attempt.participant.first_name} {rtc.matching_attempt.participant.last_name}", 
                        template_name='emails/match_request_to_coach.html',
                        email_trigger=email_trigger,
                        event_type=RequestToCoachEvent.EventType.REQUEST_SENT,
    )
    
    # update time stamps and message counters only if email sending succeeded
    rtc.first_sent_at = now
    rtc.last_sent_at = now
    rtc.requests_sent += 1
    rtc.save()
    
    rtc = rtc.transition_to(RequestToCoach.Status.AWAITING_REPLY)
    if not rtc.matching_attempt.is_active:
        ma = rtc.matching_attempt.transition_to(MatchingAttempt.Status.MATCHING_ACTIVE)
    
    return rtc
    
@transaction.atomic
def send_reminder_coach_request_email(rtc: RequestToCoach, email_trigger: str = "automated") -> RequestToCoach:
    """Send a reminder email to the coach and update status accordingly."""
    
    rtc = _get_locked_request_to_coach(rtc)
    
    if not rtc.can_send_reminder():
        raise ValidationError(f"Cannot send reminder email for RequestToCoach {rtc.id} in its current state. Status: {rtc.get_status_display()}, Deadline passed: {rtc.is_deadline_passed()}, Requests sent: {rtc.requests_sent}.")
    
    now = timezone.now()

    _send_request_email(rtc, 
                        subject=f"Reminder: Matching-Anfrage für {rtc.matching_attempt.participant.first_name} {rtc.matching_attempt.participant.last_name}", 
                        template_name='emails/reminder_match_request_to_coach.html',
                        email_trigger=email_trigger,
                        event_type=RequestToCoachEvent.EventType.REMINDER_SENT,
    )
    
    rtc.last_sent_at = now
    rtc.requests_sent += 1
    rtc.save()
    
    # The RTC is now in the same state as it was when the first email was sent, so we don't transition it again. The only difference is the updated timestamps and request count.
        
    return rtc

@transaction.atomic
def send_connecting_email(request_to_coach: RequestToCoach, email_trigger: str = "automated"):
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