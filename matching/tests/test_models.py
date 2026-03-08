import pytest

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.utils import timezone

from matching.models import RequestToCoach, RequestToCoachTransition, RequestToCoachEvent, CoachActionToken


@pytest.mark.django_db
def test_valid_transition_updates_status_and_creates_transition(rtc):
    rtc.status = RequestToCoach.Status.IN_PREPARATION
    rtc.save()

    updated = rtc.transition_to(RequestToCoach.Status.AWAITING_REPLY)

    updated.refresh_from_db()

    assert updated.status == RequestToCoach.Status.AWAITING_REPLY

    transition = RequestToCoachTransition.objects.get(request=updated)

    assert transition.from_status == RequestToCoach.Status.IN_PREPARATION
    assert transition.to_status == RequestToCoach.Status.AWAITING_REPLY
    
@pytest.mark.django_db
def test_invalid_transition_raises_validation_error(rtc):
    rtc.status = RequestToCoach.Status.IN_PREPARATION
    rtc.save()

    with pytest.raises(ValidationError):
        rtc.transition_to(RequestToCoach.Status.ACCEPTED_ON_TIME)
        
        
@pytest.mark.django_db
def test_accept_before_deadline_sets_status_and_event(rtc):
    rtc.status = RequestToCoach.Status.AWAITING_REPLY
    rtc.deadline_at = timezone.now() + timezone.timedelta(hours=2)
    rtc.save()

    rtc.accept()

    rtc.refresh_from_db()

    assert rtc.status == RequestToCoach.Status.ACCEPTED_ON_TIME
    assert rtc.responded_at is not None

    event = RequestToCoachEvent.objects.get(request=rtc)
    assert event.event_type == RequestToCoachEvent.EventType.ACCEPTED
    
@pytest.mark.django_db
def test_accept_after_deadline_sets_late_status(rtc):
    rtc.status = RequestToCoach.Status.AWAITING_REPLY
    rtc.deadline_at = timezone.now() - timezone.timedelta(hours=1)
    rtc.save()

    rtc.accept()

    rtc.refresh_from_db()

    assert rtc.status == RequestToCoach.Status.ACCEPTED_LATE
    
@pytest.mark.django_db
def test_reject_before_deadline_sets_status_and_event(rtc):
    rtc.status = RequestToCoach.Status.AWAITING_REPLY
    rtc.deadline_at = timezone.now() + timezone.timedelta(hours=2)
    rtc.save()

    rtc.reject()

    rtc.refresh_from_db()

    assert rtc.status == RequestToCoach.Status.REJECTED_ON_TIME
    assert rtc.responded_at is not None

    event = RequestToCoachEvent.objects.get(request=rtc)
    assert event.event_type == RequestToCoachEvent.EventType.REJECTED
    
import pytest
from django.core.exceptions import ValidationError


@pytest.mark.django_db
def test_accept_not_allowed_if_not_awaiting_reply(rtc):
    rtc.status = RequestToCoach.Status.IN_PREPARATION
    rtc.save()

    with pytest.raises(ValidationError):
        rtc.accept()
        
        
@pytest.mark.django_db
def test_mark_responded_sets_timestamp_once(rtc):
    rtc.mark_responded()
    rtc.refresh_from_db()

    first_timestamp = rtc.responded_at
    assert first_timestamp is not None

    rtc.mark_responded()
    rtc.refresh_from_db()

    assert rtc.responded_at == first_timestamp
    
    
from django.utils import timezone


@pytest.mark.django_db
def test_deadline_passed_returns_true_if_past(rtc):
    rtc.deadline_at = timezone.now() - timezone.timedelta(hours=1)

    assert rtc.is_deadline_passed() is True
    
@pytest.mark.django_db
def test_deadline_passed_returns_false_if_future(rtc):
    rtc.deadline_at = timezone.now() + timezone.timedelta(hours=1)

    assert rtc.is_deadline_passed() is False
    
@pytest.mark.django_db
def test_can_send_request_respects_max_limit(rtc):
    rtc.requests_sent = 3
    rtc.max_number_of_requests = 3

    assert rtc.can_send_request() is False
    
@pytest.mark.django_db
def test_cannot_send_reminder_without_first_email(rtc):
    rtc.status = RequestToCoach.Status.AWAITING_REPLY
    rtc.requests_sent = 0
    rtc.first_sent_at = None

    assert rtc.can_send_reminder() is False
    
@pytest.mark.django_db
def test_cannot_send_reminder_after_deadline(rtc):
    rtc.status = RequestToCoach.Status.AWAITING_REPLY
    rtc.first_sent_at = timezone.now()
    rtc.deadline_at = timezone.now() - timezone.timedelta(hours=1)

    assert rtc.can_send_reminder() is False
    
    



@pytest.mark.django_db
def test_unique_coach_request_per_matching_attempt(matching_attempt, coach):

    RequestToCoach.objects.create(
        matching_attempt=matching_attempt,
        coach=coach,
    )

    with pytest.raises(IntegrityError):
        RequestToCoach.objects.create(
            matching_attempt=matching_attempt,
            coach=coach,
        )
        
@pytest.mark.django_db
def test_request_to_coach_str_contains_names(rtc):

    text = str(rtc)

    assert rtc.coach.first_name in text
    assert rtc.matching_attempt.participant.first_name in text
    
@pytest.mark.django_db
def test_token_must_be_unique(rtc):

    CoachActionToken.objects.create(
        token="test-token",
        request_to_coach=rtc,
        action=CoachActionToken.Action.ACCEPT,
    )

    with pytest.raises(IntegrityError):
        CoachActionToken.objects.create(
            token="test-token",
            request_to_coach=rtc,
            action=CoachActionToken.Action.DECLINE,
        )
        
@pytest.mark.django_db
def test_new_token_is_unused(rtc):

    token = CoachActionToken.objects.create(
        token="abc123",
        request_to_coach=rtc,
        action=CoachActionToken.Action.ACCEPT,
    )

    assert token.used_at is None
    
@pytest.mark.django_db
def test_token_action_is_stored_correctly(rtc):

    token = CoachActionToken.objects.create(
        token="xyz",
        request_to_coach=rtc,
        action=CoachActionToken.Action.DECLINE,
    )

    assert token.action == CoachActionToken.Action.DECLINE
    
@pytest.mark.django_db
def test_token_belongs_to_request(rtc):

    token = CoachActionToken.objects.create(
        token="abc",
        request_to_coach=rtc,
        action=CoachActionToken.Action.ACCEPT,
    )

    assert token.request_to_coach == rtc