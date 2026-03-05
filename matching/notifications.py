import logging

from emails.services import send_email
from .models import RequestToCoach

logger = logging.getLogger(__name__)



def send_first_coach_request_email(request_to_coach: RequestToCoach):
    author = "BeginnerLuft Roboti"
    subject = f"Matching-Anfrage für {request_to_coach.matching_attempt.participant}"
    recipient = request_to_coach.coach.user.email
    template_name = 'emails/match_request_to_coach.html'

    return send_email(
        to=recipient,
        subject=subject,
        template_name=template_name,
        context={
            'recipient_name': request_to_coach.coach.first_name,
            'participant_name': request_to_coach.matching_attempt.participant.first_name,
            'author': author,
        },
        request_to_coach=request_to_coach,
    )
    
def send_reminder_coach_request_email(request_to_coach: RequestToCoach):
    author = "BeginnerLuft Roboti"
    subject = f"Reminder: Matching-Anfrage für {request_to_coach.matching_attempt.participant}"
    recipient = request_to_coach.coach.user.email
    template_name = 'emails/reminder_match_request_to_coach.html'

    return send_email(
        to=recipient,
        subject=subject,
        template_name=template_name,
        context={
            'recipient_name': request_to_coach.coach.first_name,
            'participant_name': request_to_coach.matching_attempt.participant.first_name,
            'author': author,
        },
        request_to_coach=request_to_coach,
    )


def send_connecting_email(request_to_coach: RequestToCoach):
    """Send match-confirmed emails to both the coach and the participant."""
    logger.info(
        "send_connecting_email called for RequestToCoach pk=%s (coach=%s, participant=%s)",
        request_to_coach.pk,
        request_to_coach.coach,
        request_to_coach.matching_attempt.participant,
    )
    author = "BeginnerLuft Roboti"
    coach = request_to_coach.coach
    participant = request_to_coach.matching_attempt.participant

    # Collect participant's preferred coaching formats
    formats = []
    if participant.coaching_format_online:
        formats.append("Online")
    if participant.coaching_format_presence:
        formats.append("Präsenz")
    if participant.coaching_format_hybrid:
        formats.append("Hybrid")

    # --- Email to coach ---
    logger.debug("send_connecting_email: sending to coach %s (%s)", coach, coach.email)
    send_email(
        to=coach.email,
        subject=f"Dein Matching mit {participant} ist bestätigt!",
        template_name='emails/connecting_email.html',
        context={
            'recipient_name': coach.first_name,
            'partner_name': str(participant),
            'partner_email': participant.email,
            'partner_city': participant.city,
            'coaching_formats': formats,
            'is_coach': True,
            'author': author,
        },
        request_to_coach=request_to_coach,
    )

    # --- Email to participant ---
    logger.debug("send_connecting_email: sending to participant %s (%s)", participant, participant.email)
    send_email(
        to=participant.email,
        subject=f"Dein Matching mit {coach.full_name} ist bestätigt!",
        template_name='emails/connecting_email.html',
        context={
            'recipient_name': participant.first_name,
            'partner_name': coach.full_name,
            'partner_email': coach.email,
            'is_coach': False,
            'author': author,
        },
        matching_attempt=request_to_coach.matching_attempt,
    )