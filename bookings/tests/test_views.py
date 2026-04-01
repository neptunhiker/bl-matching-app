import pytest
from django.urls import reverse

class TestBookingsListView:
    @pytest.mark.django_db
    def test_bookings_list_redirects_anonymous_to_login(self, client):
        url = reverse("calendly_bookings_list")

        response = client.get(url)

        assert response.status_code == 302
        assert reverse("login") in response.url
        assert f"next={url}" in response.url

    @pytest.mark.django_db
    def test_bookings_list_forbidden_for_logged_in_non_staff(self, client, coach_user_1):
        client.force_login(coach_user_1)

        response = client.get(reverse("calendly_bookings_list"))

        assert response.status_code == 403

    @pytest.mark.django_db
    def test_bookings_list_accessible_for_logged_in_staff(self, client, staff_user):
        client.force_login(staff_user)

        response = client.get(reverse("calendly_bookings_list"))

        assert response.status_code == 200

    @pytest.mark.django_db
    def test_bookings_list_accessible_for_logged_in_superuser(self, client, superuser):
        # Ensure superuser satisfies staff gate even if fixture creation differs.
        if not superuser.is_staff:
            superuser.is_staff = True
            superuser.save(update_fields=["is_staff"])

        client.force_login(superuser)

        response = client.get(reverse("calendly_bookings_list"))

        assert response.status_code == 200

    @pytest.mark.django_db
    def test_bookings_list_redirects_inactive_staff_to_login(self, client, staff_user):
        staff_user.is_active = False
        staff_user.save(update_fields=["is_active"])
        client.force_login(staff_user)

        url = reverse("calendly_bookings_list")
        response = client.get(url)

        assert response.status_code == 302
        assert reverse("login") in response.url
        assert f"next={url}" in response.url
