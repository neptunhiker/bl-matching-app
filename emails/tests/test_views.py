import pytest
from django.urls import reverse


@pytest.mark.django_db
class TestEmailLogDetailView:

    def test_logged_out_redirects_to_login(self, client, email_log):
        url = reverse('emails:email_log_detail', kwargs={'pk': email_log.pk})
        response = client.get(url)
        assert response.status_code == 302
        assert response.url.startswith('/accounts/login/')

    def test_plain_user_forbidden(self, client, email_log):
        from accounts.models import User
        user = User.objects.create_user(email='plain@example.com', password='pw')
        client.force_login(user)
        url = reverse('emails:email_log_detail', kwargs={'pk': email_log.pk})
        assert client.get(url).status_code == 403

    def test_staff_user_has_access(self, client, email_log):
        from accounts.models import User
        staff = User.objects.create_user(email='staff@example.com', password='pw', is_staff=True)
        client.force_login(staff)
        url = reverse('emails:email_log_detail', kwargs={'pk': email_log.pk})
        assert client.get(url).status_code == 200

    def test_superuser_has_access(self, client, email_log):
        from accounts.models import User
        superuser = User.objects.create_user(email='su@example.com', password='pw', is_superuser=True)
        client.force_login(superuser)
        url = reverse('emails:email_log_detail', kwargs={'pk': email_log.pk})
        assert client.get(url).status_code == 200
