import pytest
from unittest.mock import patch

from django.urls import reverse

from profiles.models import Coach


PREVIEW_URL = reverse("get_coaches")  # url name still "get_coaches" per existing route
CONFIRM_URL = reverse("coach_import_confirm")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

API_RESPONSE = [
    {
        "first_name": "Anna",
        "last_name": "Neu",
        "email": "anna.neu@example.com",
        "preferred_communication_channel": "slack",
        "slack_user_id": "U_ANNA",
        "status": "available",
        "status_notes": "Tolle Coachin",
        "maximum_capacity": 3,
    },
    {"first_name": "Chris", "last_name": "Coach", "email": "coach@example.com"},  # existing via coach_1
]


@pytest.mark.django_db
class TestCoachImportPreviewView:

    def test_anonymous_redirects_to_login(self, client):
        response = client.get(PREVIEW_URL)
        assert response.status_code == 302
        assert response.url.startswith("/accounts/login/")

    def test_plain_user_forbidden(self, client, plain_user):
        client.force_login(plain_user)
        response = client.get(PREVIEW_URL)
        assert response.status_code == 403

    def test_staff_can_access_preview(self, client, staff_user, coach_1):
        client.force_login(staff_user)
        with patch("profiles.views._fetch_coaches_from_api", return_value=API_RESPONSE):
            response = client.get(PREVIEW_URL)
        assert response.status_code == 200
        assert "profiles/coach_import_preview.html" in [t.name for t in response.templates]

    def test_new_and_duplicate_split_is_correct(self, client, staff_user, coach_1):
        """coach_1 has email 'coach@example.com' — matches the second API entry."""
        client.force_login(staff_user)
        with patch("profiles.views._fetch_coaches_from_api", return_value=API_RESPONSE):
            response = client.get(PREVIEW_URL)
        ctx = response.context
        assert len(ctx["new_coaches"]) == 1
        assert ctx["new_coaches"][0]["email"] == "anna.neu@example.com"
        assert len(ctx["duplicate_coaches"]) == 1
        assert ctx["duplicate_coaches"][0]["email"] == "coach@example.com"

    def test_all_new_when_no_existing_coaches(self, client, staff_user):
        client.force_login(staff_user)
        with patch("profiles.views._fetch_coaches_from_api", return_value=API_RESPONSE):
            response = client.get(PREVIEW_URL)
        ctx = response.context
        assert len(ctx["new_coaches"]) == 2
        assert ctx["duplicate_coaches"] == []

    def test_api_error_renders_error_message(self, client, staff_user):
        import requests as req_module
        client.force_login(staff_user)
        with patch("profiles.views._fetch_coaches_from_api", side_effect=req_module.RequestException("timeout")):
            response = client.get(PREVIEW_URL)
        assert response.status_code == 200
        assert response.context["api_error"] is not None
        assert "timeout" in response.context["api_error"]

    def test_api_key_missing_renders_error_message(self, client, staff_user):
        client.force_login(staff_user)
        with patch("profiles.views._fetch_coaches_from_api", side_effect=ValueError("COACHING_HUB_API_KEY is not configured.")):
            response = client.get(PREVIEW_URL)
        assert response.status_code == 200
        assert response.context["api_error"] is not None


@pytest.mark.django_db
class TestCoachImportConfirmView:

    def test_anonymous_redirects_to_login(self, client):
        response = client.post(CONFIRM_URL, {"coach_emails": ["anna.neu@example.com"]})
        assert response.status_code == 302
        assert response.url.startswith("/accounts/login/")

    def test_plain_user_forbidden(self, client, plain_user):
        client.force_login(plain_user)
        response = client.post(CONFIRM_URL, {"coach_emails": ["anna.neu@example.com"]})
        assert response.status_code == 403

    def test_creates_only_new_coaches(self, client, staff_user, coach_1):
        """Only anna.neu@example.com should be created; coach_1's email is skipped."""
        client.force_login(staff_user)
        with patch("profiles.views._fetch_coaches_from_api", return_value=API_RESPONSE):
            response = client.post(
                CONFIRM_URL,
                {"coach_emails": ["anna.neu@example.com", "coach@example.com"]},
            )
        assert response.status_code == 302
        assert response.url == reverse("coach_list")
        assert Coach.objects.filter(email="anna.neu@example.com").exists()
        # coach_1 still only appears once
        assert Coach.objects.filter(email="coach@example.com").count() == 1

    def test_new_coach_gets_api_status(self, client, staff_user):
        """Status comes from the API value, not hardcoded ONBOARDING."""
        client.force_login(staff_user)
        with patch("profiles.views._fetch_coaches_from_api", return_value=API_RESPONSE):
            client.post(CONFIRM_URL, {"coach_emails": ["anna.neu@example.com"]})
        coach = Coach.objects.get(email="anna.neu@example.com")
        assert coach.status == Coach.Status.AVAILABLE

    def test_new_coach_fields_are_saved(self, client, staff_user):
        """All additional fields from the API are persisted correctly."""
        client.force_login(staff_user)
        with patch("profiles.views._fetch_coaches_from_api", return_value=API_RESPONSE):
            client.post(CONFIRM_URL, {"coach_emails": ["anna.neu@example.com"]})
        coach = Coach.objects.get(email="anna.neu@example.com")
        assert coach.preferred_communication_channel == Coach.CommunicationChannel.SLACK
        assert coach.slack_user_id == "U_ANNA"
        assert coach.status_notes == "Tolle Coachin"
        assert coach.maximum_capacity == 3

    def test_invalid_api_status_falls_back_to_onboarding(self, client, staff_user):
        """Unknown status values from the API fall back to ONBOARDING."""
        bad_response = [{
            "first_name": "Bad", "last_name": "Status",
            "email": "bad.status@example.com",
            "status": "nicht_existierend",
        }]
        client.force_login(staff_user)
        with patch("profiles.views._fetch_coaches_from_api", return_value=bad_response):
            client.post(CONFIRM_URL, {"coach_emails": ["bad.status@example.com"]})
        coach = Coach.objects.get(email="bad.status@example.com")
        assert coach.status == Coach.Status.ONBOARDING

    def test_idempotent_double_submit(self, client, staff_user):
        """Posting the same emails twice must not create duplicates."""
        client.force_login(staff_user)
        payload = {"coach_emails": ["anna.neu@example.com"]}
        with patch("profiles.views._fetch_coaches_from_api", return_value=API_RESPONSE):
            client.post(CONFIRM_URL, payload)
            client.post(CONFIRM_URL, payload)
        assert Coach.objects.filter(email="anna.neu@example.com").count() == 1

    def test_empty_submission_redirects_with_info_message(self, client, staff_user):
        client.force_login(staff_user)
        response = client.post(CONFIRM_URL, {})
        assert response.status_code == 302
        assert response.url == reverse("coach_list")

    def test_api_error_on_confirm_redirects_with_error_message(self, client, staff_user):
        import requests as req_module
        client.force_login(staff_user)
        with patch("profiles.views._fetch_coaches_from_api", side_effect=req_module.RequestException("fail")):
            response = client.post(CONFIRM_URL, {"coach_emails": ["anna.neu@example.com"]})
        assert response.status_code == 302
        assert response.url == reverse("coach_list")
        # No coach should have been created
        assert not Coach.objects.filter(email="anna.neu@example.com").exists()

    def test_get_request_redirects_to_preview(self, client, staff_user):
        client.force_login(staff_user)
        response = client.get(CONFIRM_URL)
        assert response.status_code == 302
        assert response.url == reverse("get_coaches")
