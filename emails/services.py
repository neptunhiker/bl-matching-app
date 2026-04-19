import logging
import re
from typing import Dict, Any


from anymail.message import AnymailMessage

from django.db import transaction
from django.conf import settings
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from matching.locks import _get_locked_request_to_coach, _get_locked_matching_attempt

from matching.tokens import generate_accept_and_decline_token, generate_intro_call_feedback_url, generate_participant_response_urls
from matching.utils import get_urgency_message, get_intro_call_extension_deadline
from .models import EmailLog


logger = logging.getLogger(__name__)


def send_email(
    to: str,
    subject: str,
    template_name: str,
    context: dict,
    sent_by: str,
    triggered_by: str,
    request_to_coach=None,
    matching_attempt=None,
) -> EmailLog:
    """
    Render an HTML email template, send it, and log the result.

    Args:
        to:               Recipient email address.
        subject:          Email subject line.
        template_name:    Path to the HTML template (relative to templates/).
        context:          Template context dict.
        sent_by:          Who/what is sending this email (e.g. "User:123" or "System")
        triggered_by:     Who/what triggered this email (e.g. "system" or "staff")
        request_to_coach: RequestToCoach instance this email relates to (optional).
        matching_attempt instance this email relates to (optional).

    Returns:
        EmailLog instance with status 'sent' or 'failed'.
    """
    html_body = render_to_string(template_name, context)
    # Plain-text fallback: strip tags naively (good enough for transactional mail)
    plain_body = ' '.join(html_body.split())  # collapses whitespace

    # Normalize recipient address: tests sometimes pass markdown-style
    # links like "[name](mailto:recipient@example.com)" or
    # "Name <recipient@example.com>". Extract a plain email address so
    # anymail/django don't choke on unexpected formats.
    def _extract_email(value: str) -> str:
        if not isinstance(value, str):
            return value
        # Markdown mailto link: [text](mailto:email)
        m = re.search(r"\[.*?\]\(mailto:(.*?)\)", value)
        if m:
            return m.group(1)
        # Angle-bracket form: Name <email@example.com>
        m = re.search(r"<([^>]+)>", value)
        if m:
            return m.group(1)
        return value.strip()

    to_addr = _extract_email(to)

    # Save first so we have a UUID to tag the outgoing message with.
    # Brevo echoes X-Mailin-Tag back in webhook payloads, letting us look up
    # this log entry when the delivery/bounce event arrives.
    log = EmailLog(
        to=to_addr,
        subject=subject,
        html_body=html_body,
        sent_by=sent_by,
        request_to_coach=request_to_coach,
        matching_attempt=matching_attempt,
        email_trigger=triggered_by,
    )
    log.save()

    logger.debug(
        "send_email: backend=%s to=%s subject=%r log_id=%s",
        settings.EMAIL_BACKEND,
        to,
        subject,
        log.id,
    )

    try:
        bcc = [settings.EMAIL_BCC] if getattr(settings, 'EMAIL_BCC', None) else []
        msg = AnymailMessage(subject=subject, body=plain_body, to=[to_addr], bcc=bcc)
        msg.attach_alternative(html_body, 'text/html')
        # Tag with log UUID so Brevo webhooks can reference this log entry.
        msg.tags = [str(log.id)]
        result = msg.send()
        logger.info(
            "send_email: msg.send() returned %s for log_id=%s (to=%s)",
            result,
            log.id,
            to,
        )
        log.status = EmailLog.Status.SENT
    except Exception as exc:  # noqa: BLE001
        logger.exception("send_email: FAILED for log_id=%s (to=%s): %s", log.id, to, exc)
        log.status = EmailLog.Status.FAILED
        log.error_message = str(exc)

    log.save(update_fields=['status', 'error_message'])
    return log




def _build_email_context(
    rtc,
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
        "coaching_target": participant.coaching_target,
        "background_information": participant.background_information,
        "deadline": rtc.deadline_at,
        "start_date": rtc.matching_attempt.participant.start_date.strftime("%d.%m.%Y"),
    }
    
def _send_request_email(
        rtc,
        subject: str,
        template_name: str,
        triggered_by: str="system",
    ):
    accept_url, decline_url = generate_accept_and_decline_token(rtc)

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
    

def send_first_coach_request_email(rtc):
    """Send the first coach request email and update status accordingly."""
    
    rtc = _get_locked_request_to_coach(rtc)
    
    _send_request_email(rtc, 
                        subject=f"Matching-Anfrage für {rtc.matching_attempt.participant.first_name} {rtc.matching_attempt.participant.last_name}", 
                        template_name='emails/match_request_to_coach.html',
    )        
    
    return rtc
    
@transaction.atomic
def send_reminder_coach_request_email(rtc):
    """Send a reminder email to the coach and update status accordingly."""

    
    rtc = _get_locked_request_to_coach(rtc)

    _send_request_email(rtc, 
                        subject=f"Reminder: Matching-Anfrage für {rtc.matching_attempt.participant.first_name} {rtc.matching_attempt.participant.last_name}", 
                        template_name='emails/reminder_match_request_to_coach.html',
    )
        
    return rtc


    
@transaction.atomic
def send_intro_call_request_email(matching_attempt):
    """Send an email to the coach to set up an intro call with the participant, and update status accordingly."""
    
    matching_attempt = _get_locked_matching_attempt(matching_attempt)
    
    participant = matching_attempt.participant
    
    intro_call_feedback_url = generate_intro_call_feedback_url(matching_attempt)
    
    deadline_for_intro_call = matching_attempt.intro_call_deadline_at
    
    coach = matching_attempt.matched_coach
    context = {
        "recipient_name": coach.first_name,
        "participant_name": participant.first_name,
        "participant": participant,
        "participant_email": participant.email,
        "learn_more_url": settings.SITE_URL.rstrip("/") + reverse("participant_detail", kwargs={"pk": participant.pk}),
        "urgency_message": get_urgency_message(participant, start_date=participant.start_date),
        "intro_call_feedback_url": intro_call_feedback_url,
        "deadline_for_intro_call": deadline_for_intro_call,
        "author": getattr(settings, "SYSTEM_EMAIL_NAME", "BeginnerLuft Roboti"),
    }
    
    transaction.on_commit(
        lambda: send_email(
            to=coach.user.email,
            subject=f"Vereinbare ein Kennenlerngespräch mit {participant.first_name}",
            template_name='emails/intro_call_request_to_coach.html',
            context=context,
            matching_attempt=matching_attempt,
            sent_by=context["author"],
            triggered_by="system"
            )
    )
        
    return matching_attempt


@transaction.atomic
def send_intro_call_info_email_to_participant(matching_attempt, triggered_by: str="system", triggered_by_user: User = None):
    """Send an email to the participant with information about the matched coach and next steps for the intro call."""
    
    matching_attempt = _get_locked_matching_attempt(matching_attempt)
    
    participant = matching_attempt.participant
    
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

@transaction.atomic
def send_feedback_request_email_after_intro_call_to_participant(matching_attempt, triggered_by: str="system"):
    """Send an email to the participant to request feedback about the intro call after receiving positive feedback from the coach."""
    
    matching_attempt = _get_locked_matching_attempt(matching_attempt)
    
    participant = matching_attempt.participant
    
    coach = matching_attempt.matched_coach
    start_coaching_url, calendly_url = generate_participant_response_urls(matching_attempt)
    
    context = {
        "recipient_name": participant.first_name,
        "coach": coach,
        "bl_contact": matching_attempt.bl_contact,
        "coach_email": coach.user.email,
        "participant_first_name": participant.first_name,
        "start_coaching_url": start_coaching_url,
        "calendly_url": calendly_url,
        "author": getattr(settings, "SYSTEM_EMAIL_NAME", "BeginnerLuft Roboti"),
    }
    
    transaction.on_commit(
        lambda: send_email(
            to=participant.email,
            subject=f"Bereit für deinen Coach-Start mit {coach}?",
            template_name='emails/intro_call_feedback_request_to_participant.html',
            context=context,
            matching_attempt=matching_attempt,
            sent_by=context["author"],
            triggered_by=triggered_by
            )
    )
        
    return matching_attempt

@transaction.atomic
def send_coaching_start_info_email_to_coach(matching_attempt, triggered_by: str="system"):
    """Send an email to the coach to inform them about the official start of the coaching."""
    
    matching_attempt = _get_locked_matching_attempt(matching_attempt)
    
    participant = matching_attempt.participant
    start_date = participant.start_date.strftime("%d.%m.%Y")
    
    coach = matching_attempt.matched_coach
    context = {
        "recipient_name": coach.first_name,
        "participant_name": participant.first_name,
        "participant_email": participant.email,
        "start_date": start_date,
        "learn_more_url": settings.SITE_URL.rstrip("/") + reverse("participant_detail", kwargs={"pk": participant.pk}),
        "author": getattr(settings, "SYSTEM_EMAIL_NAME", "BeginnerLuft Roboti"),
    }
    
    transaction.on_commit(
        lambda: send_email(
            to=coach.user.email,
            subject=f"🤩 Dein Coaching mit {participant.first_name} kann starten",
            template_name='emails/info_coaching_start_to_coach.html',
            context=context,
            matching_attempt=matching_attempt,
            sent_by=context["author"],
            triggered_by=triggered_by
            )
    )
        
    return matching_attempt


@transaction.atomic
def send_coaching_start_info_email_to_participant(matching_attempt, triggered_by: str="system"):
    """Send an email to the participant to inform them about the official start of the coaching."""
    
    matching_attempt = _get_locked_matching_attempt(matching_attempt)
    
    participant = matching_attempt.participant
    start_date = participant.start_date.strftime("%d.%m.%Y")
    
    coach = matching_attempt.matched_coach
    
    context = {
        "recipient_name": participant.first_name,
        "coach_name": coach,
        "coach_first_name": coach.first_name,
        "coach_email": coach.user.email,
        "participant_first_name": participant.first_name,
        "start_date": start_date,
        "author": getattr(settings, "SYSTEM_EMAIL_NAME", "BeginnerLuft Roboti"),
    }
    
    transaction.on_commit(
        lambda: send_email(
            to=participant.email,
            subject=f"🤩 Dein Coaching mit Coach {coach.full_name} kann starten",
            template_name='emails/info_coaching_start_to_participant.html',
            context=context,
            matching_attempt=matching_attempt,
            sent_by=context["author"],
            triggered_by=triggered_by
            )
    )
        
    return matching_attempt

@transaction.atomic
def send_intro_call_feedback_request_email_to_participant(matching_attempt, triggered_by: str="system"):
    """Send an email to the participant to request feedback about the intro call after receiving feedback from the coach."""
    
    matching_attempt = _get_locked_matching_attempt(matching_attempt)
    
    participant = matching_attempt.participant
    
    coach = matching_attempt.matched_coach
    intro_call_feedback_url = generate_intro_call_feedback_url(matching_attempt)
    
    context = {
        "recipient_name": participant.first_name,
        "coach_name": coach,
        "coach_first_name": coach.first_name,
        "coach_email": coach.user.email,
        "participant_first_name": participant.first_name,
        "intro_call_feedback_url": intro_call_feedback_url,
        "author": getattr(settings, "SYSTEM_EMAIL_NAME", "BeginnerLuft Roboti"),
    }
    
    transaction.on_commit(
        lambda: send_email(
            to=participant.email,
            subject=f"Wie war dein Kennenlerngespräch mit {coach.first_name}?",
            template_name='emails/intro_call_feedback_request_to_participant.html',
            context=context,
            matching_attempt=matching_attempt,
            sent_by=context["author"],
            triggered_by=triggered_by
            )
    )
        
    return matching_attempt

@transaction.atomic
def send_clarification_call_booked_info_to_coach_email(matching_attempt, triggered_by: str = "system"):
    """Email to the coach when the participant has booked a Calendly clarification (Check In) call."""

    matching_attempt = _get_locked_matching_attempt(matching_attempt)

    participant = matching_attempt.participant
    coach = matching_attempt.matched_coach

    context = {
        "recipient_name": coach.first_name,
        "coach_name": coach,
        "coach_first_name": coach.first_name,
        "participant": participant,
        "author": getattr(settings, "SYSTEM_EMAIL_NAME", "BeginnerLuft Roboti"),
    }

    transaction.on_commit(
        lambda: send_email(
            to=coach.user.email,
            subject=f"ℹ️ Kurzes Update: {participant.first_name} hat ein Klärungsgespräch gebucht",
            template_name="emails/clarification_call_booked_info_to_coach.html",
            context=context,
            matching_attempt=matching_attempt,
            sent_by=context["author"],
            triggered_by=triggered_by,
        )
    )

    return matching_attempt


@transaction.atomic
def send_escalation_info_email_to_staff(matching_attempt, triggered_by: str = "system"):
    """Fallback email to the BL contact when the escalation Slack notification could not be delivered."""

    matching_attempt = _get_locked_matching_attempt(matching_attempt)

    participant = matching_attempt.participant
    coach = matching_attempt.matched_coach
    bl_contact = matching_attempt.bl_contact

    url_participant = settings.SITE_URL.rstrip("/") + reverse(
        "participant_detail", kwargs={"pk": participant.pk}
    )

    context = {
        "participant": participant,
        "coach": coach,
        "url_participant": url_participant,
        "author": getattr(settings, "SYSTEM_EMAIL_NAME", "BeginnerLuft Roboti"),
    }

    transaction.on_commit(
        lambda: send_email(
            to=bl_contact.user.email,
            subject=f"⚠️ Klärungsbedarf bei {participant.first_name}",
            template_name="emails/escalation_notification_to_staff.html",
            context=context,
            matching_attempt=matching_attempt,
            sent_by=context["author"],
            triggered_by=triggered_by,
        )
    )

    return matching_attempt