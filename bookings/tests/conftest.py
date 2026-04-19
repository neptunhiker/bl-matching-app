import datetime
import pytest

from bookings.models import CalendlyBooking


@pytest.fixture
def matching_attempt_for_check_in(db):
    """A MatchingAttempt in AWAITING_INTRO_CALL_FEEDBACK_FROM_PARTICIPANT with participant email ada@example.com."""
    from accounts.models import User
    from profiles.models import Participant, Coach
    from matching.models import MatchingAttempt

    coach_user = User.objects.create_user(
        email="check_in_coach@example.com",
        password="testpass123",
        first_name="Check",
        last_name="InCoach",
    )
    participant = Participant.objects.create(
        first_name="Ada",
        last_name="Lovelace",
        email="ada@example.com",
        city="Berlin",
        start_date=datetime.date(2026, 6, 1),
    )
    coach = Coach.objects.create(user=coach_user, city="Berlin")
    ma = MatchingAttempt.objects.create(
        participant=participant,
        ue=48,
        matched_coach=coach,
    )
    MatchingAttempt.objects.filter(pk=ma.pk).update(
        state=MatchingAttempt.State.AWAITING_INTRO_CALL_FEEDBACK_FROM_PARTICIPANT,
    )
    return MatchingAttempt.objects.get(pk=ma.pk)


@pytest.fixture
def calendly_booking(db):
    return CalendlyBooking.objects.create(
        calendly_invitee_uri="https://api.calendly.com/scheduled_events/XXXXX/invitees/abc-123",
        status="active",
        invitee_email="RZBjY@example.com",
        invitee_first_name="Max",
        invitee_last_name="Mustermann",
        invitee_name="Max Mustermann",
        start_time=datetime.datetime(2024, 6, 1, 15, 0),
        end_time=datetime.datetime(2024, 6, 1, 15, 30),
        timezone="Europe/Berlin",
        event_name="BeginnerLuft Erstgespräch",
        calendly_event_uri="https://api.calendly.com/scheduled_events/XXXXX",
        calendly_event_uuid="XXXXX",
    )
