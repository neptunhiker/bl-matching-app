import datetime
import pytest

from bookings.models import CalendlyBooking


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
