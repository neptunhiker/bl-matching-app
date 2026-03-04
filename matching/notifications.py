from emails.services import send_email
from .models import RequestToCoach



def send_first_coach_request_email(request_to_coach: RequestToCoach):
    author = "BeginnerLuft Roboti"
    subject = f"Matching-Anfrage für {request_to_coach.matching_attempt.participant}"
    recipient = request_to_coach.coach.email
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
    )