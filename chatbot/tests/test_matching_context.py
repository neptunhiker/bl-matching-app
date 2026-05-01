import datetime
import pytest
from django.utils import timezone

from matching.models import MatchingAttempt, RequestToCoach
from profiles.models import Coach, Participant
from chatbot.matching_context import build_matching_context


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def participant(db):
    return Participant.objects.create(
        first_name="Max",
        last_name="Mustermann",
        email="max@example.com",
        city="Berlin",
        start_date=datetime.date(2026, 9, 1),
    )


@pytest.fixture
def matching_attempt(db, participant):
    return MatchingAttempt.objects.create(participant=participant, ue=10)


@pytest.fixture
def coach(db):
    return Coach.objects.create(
        first_name="Carl",
        last_name="Coach",
        email="carl@example.com",
    )


# ---------------------------------------------------------------------------
# Group 4 — build_matching_context()
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestBuildMatchingContext:

    def test_overdue_deadline_flagged(self, matching_attempt):
        """A deadline in the past must be marked ÜBERSCHRITTEN."""
        past = timezone.now() - datetime.timedelta(days=1)
        matching_attempt.intro_call_deadline_at = past
        matching_attempt.save()

        result = build_matching_context(matching_attempt)

        assert "ÜBERSCHRITTEN" in result

    def test_future_deadline_not_flagged(self, matching_attempt):
        """A deadline in the future must not be marked ÜBERSCHRITTEN."""
        future = timezone.now() + datetime.timedelta(days=3)
        matching_attempt.intro_call_deadline_at = future
        matching_attempt.save()

        result = build_matching_context(matching_attempt)

        assert "ÜBERSCHRITTEN" not in result

    def test_no_rtcs_renders_empty_queue_message(self, matching_attempt):
        """A matching with no RTCs must not crash and must say so clearly."""
        result = build_matching_context(matching_attempt)

        assert "Keine Coach-Anfragen vorhanden" in result

    def test_datetimes_rendered_in_berlin_local_time(self, matching_attempt):
        """Datetimes must be shown in Europe/Berlin time, not UTC.

        16:00 UTC in summer (CEST) = 18:00 Berlin.
        """
        utc_dt = datetime.datetime(2026, 5, 1, 16, 0, 0, tzinfo=datetime.timezone.utc)
        matching_attempt.intro_call_deadline_at = utc_dt
        matching_attempt.save()

        result = build_matching_context(matching_attempt)

        assert "18:00" in result
        assert "16:00" not in result
