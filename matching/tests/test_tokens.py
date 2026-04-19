"""Unit tests for generate_participant_response_urls()."""
import pytest
from urllib.parse import urlparse, parse_qs

from matching.models import ParticipantActionToken


@pytest.mark.django_db
class TestGenerateParticipantResponseUrls:

    @pytest.fixture(autouse=True)
    def _settings(self, settings):
        settings.SITE_URL = "https://test.example.com"
        settings.CALENDLY_CHECKIN_URL = "https://calendly.com/beginnerluft/check-in"

    def _generate(self, ma):
        from matching.tokens import generate_participant_response_urls
        return generate_participant_response_urls(ma)

    def test_returns_two_urls(self, matching_attempt_with_coach):
        start_url, calendly_url = self._generate(matching_attempt_with_coach)

        assert start_url
        assert calendly_url

    def test_creates_exactly_one_token(self, matching_attempt_with_coach):
        self._generate(matching_attempt_with_coach)

        tokens = ParticipantActionToken.objects.filter(
            matching_attempt=matching_attempt_with_coach
        )
        assert tokens.count() == 1

    def test_token_action_is_start_coaching(self, matching_attempt_with_coach):
        self._generate(matching_attempt_with_coach)

        token = ParticipantActionToken.objects.get()
        assert token.action == ParticipantActionToken.Action.START_COACHING

    def test_no_clarification_needed_token_created(self, matching_attempt_with_coach):
        """CLARIFICATION_NEEDED has been removed from ParticipantActionToken.Action entirely."""
        self._generate(matching_attempt_with_coach)

        assert ParticipantActionToken.objects.count() == 1

    def test_start_coaching_url_contains_token_value(self, matching_attempt_with_coach):
        start_url, _ = self._generate(matching_attempt_with_coach)

        token = ParticipantActionToken.objects.get()
        assert token.token in start_url

    def test_start_coaching_url_uses_site_url(self, matching_attempt_with_coach):
        start_url, _ = self._generate(matching_attempt_with_coach)

        assert start_url.startswith("https://test.example.com")

    def test_calendly_url_has_correct_utm_campaign(self, matching_attempt_with_coach):
        _, calendly_url = self._generate(matching_attempt_with_coach)

        qs = parse_qs(urlparse(calendly_url).query)
        assert qs["utm_campaign"] == [f"matching-{matching_attempt_with_coach.id}"]

    def test_calendly_url_has_participant_email(self, matching_attempt_with_coach):
        _, calendly_url = self._generate(matching_attempt_with_coach)

        participant = matching_attempt_with_coach.participant
        qs = parse_qs(urlparse(calendly_url).query)
        assert qs["email"] == [participant.email]

    def test_calendly_url_has_participant_name(self, matching_attempt_with_coach):
        _, calendly_url = self._generate(matching_attempt_with_coach)

        participant = matching_attempt_with_coach.participant
        expected_name = f"{participant.first_name} {participant.last_name}".strip()
        qs = parse_qs(urlparse(calendly_url).query)
        assert qs["name"] == [expected_name]

    def test_calendly_url_base_uses_setting(self, matching_attempt_with_coach):
        _, calendly_url = self._generate(matching_attempt_with_coach)

        assert calendly_url.startswith("https://calendly.com/beginnerluft/check-in")
