import pytest
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from matching.notifications import _build_email_context, _send_request_email, send_first_coach_request_email, send_reminder_coach_request_email
from matching.models import RequestToCoachEvent, RequestToCoach

@pytest.mark.django_db
def test_build_email_context_contains_expected_fields(rtc):

    context = _build_email_context(
        rtc,
        accept_url="accept-link",
        decline_url="decline-link",
    )

    assert context["recipient_name"] == rtc.coach.first_name
    assert context["participant_name"] == rtc.matching_attempt.participant.first_name
    assert context["accept_url"] == "accept-link"
    assert context["decline_url"] == "decline-link"
    assert context["deadline"] == rtc.deadline_at


    
    
@pytest.mark.django_db
def test_first_email_cannot_be_sent_twice(rtc):

    rtc.first_sent_at = timezone.now()
    rtc.save()

    with pytest.raises(ValidationError):
        send_first_coach_request_email(rtc)
        
@pytest.mark.django_db
def test_reminder_email_updates_counter(rtc):

    rtc.status = RequestToCoach.Status.AWAITING_REPLY
    rtc.first_sent_at = timezone.now()
    rtc.requests_sent = 1
    rtc.save()

    with patch("matching.notifications.send_email"):
        with patch("matching.notifications.generate_accept_and_decline_token", return_value=("a","b")):

            send_reminder_coach_request_email(rtc)

    rtc.refresh_from_db()

    assert rtc.requests_sent == 2
    assert rtc.last_sent_at is not None
    
@pytest.mark.django_db
def test_reminder_not_allowed_in_wrong_state(rtc):

    rtc.status = RequestToCoach.Status.IN_PREPARATION
    rtc.save()

    with pytest.raises(ValidationError):
        send_reminder_coach_request_email(rtc)
        
    rtc.status = RequestToCoach.Status.ACCEPTED_MATCHING
    rtc.save()

    with pytest.raises(ValidationError):
        send_reminder_coach_request_email(rtc)
