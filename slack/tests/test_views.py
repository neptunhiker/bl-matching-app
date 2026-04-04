import pytest
from django.urls import reverse

from accounts.models import User
from slack.models import SlackLog


@pytest.fixture
def slack_log(db, plain_user, matching_attempt):
    return SlackLog.objects.create(
        to=plain_user,
        subject="Test subject",
        message="Test message",
        matching_attempt=matching_attempt,
    )


@pytest.mark.django_db
class TestSlackLogDetailView:

    def test_logged_out_redirects_to_login(self, client, slack_log):
        url = reverse("slack:slack_log_detail", kwargs={"pk": slack_log.pk})
        response = client.get(url)
        assert response.status_code == 302
        assert response.url.startswith("/accounts/login/")

    def test_plain_user_forbidden(self, client, slack_log, plain_user):
        client.force_login(plain_user)
        url = reverse("slack:slack_log_detail", kwargs={"pk": slack_log.pk})
        assert client.get(url).status_code == 403

    def test_staff_user_has_access(self, client, slack_log, staff_user):
        client.force_login(staff_user)
        url = reverse("slack:slack_log_detail", kwargs={"pk": slack_log.pk})
        assert client.get(url).status_code == 200

    def test_superuser_has_access(self, client, slack_log, superuser):
        client.force_login(superuser)
        url = reverse("slack:slack_log_detail", kwargs={"pk": slack_log.pk})
        assert client.get(url).status_code == 200
