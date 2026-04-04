import hashlib
import hmac
import json
import time
from unittest.mock import patch

import pytest
from django.urls import reverse

from bookings.models import CalendlyBooking

class TestBookingsDetailView:
    @pytest.mark.django_db
    def test_booking_detail_redirects_anonymous_to_login(self, client, calendly_booking):
        url = reverse("calendly_booking_detail", args=[calendly_booking.id])

        response = client.get(url)

        assert response.status_code == 302
        assert reverse("login") in response.url
        assert f"next={url}" in response.url
        
    @pytest.mark.django_db
    def test_booking_detail_forbidden_for_logged_in_non_staff(self, client, coach_user_1, calendly_booking):
        client.force_login(coach_user_1)

        response = client.get(reverse("calendly_booking_detail", args=[calendly_booking.id]))

        assert response.status_code == 403
        
    @pytest.mark.django_db
    def test_booking_detail_accessible_for_logged_in_staff(self, client, staff_user, calendly_booking):
        client.force_login(staff_user)

        response = client.get(reverse("calendly_booking_detail", args=[calendly_booking.id]))

        assert response.status_code == 200
        
    @pytest.mark.django_db
    def test_booking_detail_accessible_for_logged_in_superuser(self, client, superuser, calendly_booking):
        client.force_login(superuser)

        response = client.get(reverse("calendly_booking_detail", args=[calendly_booking.id]))

        assert response.status_code == 200

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


# ---------------------------------------------------------------------------
# Helpers for calendly_webhook tests
# ---------------------------------------------------------------------------

TEST_SIGNING_KEY = "test-calendly-signing-key-for-pytest"

_INVITEE_URI = "https://api.calendly.com/scheduled_events/XXXXX/invitees/abc-123"
_EVENT_URI = "https://api.calendly.com/scheduled_events/XXXXX"


def _make_signature(body: bytes, key: str = TEST_SIGNING_KEY, ts: int | None = None) -> str:
    """Return a valid Calendly-Webhook-Signature header value for *body*."""
    if ts is None:
        ts = int(time.time())
    message = f"{ts}.{body.decode('utf-8')}".encode("utf-8")
    digest = hmac.new(key.encode("utf-8"), msg=message, digestmod=hashlib.sha256).hexdigest()
    return f"t={ts},v1={digest}"


def _created_payload(invitee_uri=_INVITEE_URI):
    return {
        "event": "invitee.created",
        "payload": {
            "uri": invitee_uri,
            "name": "Ada Lovelace",
            "email": "ada@example.com",
            "status": "active",
            "timezone": "Europe/Berlin",
            "questions_and_answers": [],
            "scheduled_event": {
                "uri": _EVENT_URI,
                "name": "Coaching Kickoff",
                "status": "active",
                "start_time": "2024-03-01T10:00:00.000000Z",
                "end_time": "2024-03-01T11:00:00.000000Z",
            },
        },
    }


def _canceled_payload(invitee_uri=_INVITEE_URI):
    payload = _created_payload(invitee_uri)
    payload["event"] = "invitee.canceled"
    payload["payload"]["status"] = "canceled"
    payload["payload"]["scheduled_event"]["status"] = "canceled"
    return payload


@pytest.mark.django_db
class TestCalendlyWebhook:
    """Tests for the calendly_webhook view."""

    @pytest.fixture(autouse=True)
    def _set_signing_key(self, settings):
        settings.CALENDLY_SIGNING_KEY = TEST_SIGNING_KEY

    def _url(self):
        return reverse("calendly_webhook")

    def _post(self, client, payload, *, signing_key=TEST_SIGNING_KEY, ts=None, signature=None):
        """POST *payload* with a valid (or custom) Calendly signature header."""
        body = json.dumps(payload).encode("utf-8")
        sig = signature if signature is not None else _make_signature(body, key=signing_key, ts=ts)
        return client.post(
            self._url(),
            data=body,
            content_type="application/json",
            HTTP_CALENDLY_WEBHOOK_SIGNATURE=sig,
        )

    # --- Method & parsing guard-rails ---

    def test_get_request_returns_405(self, client):
        response = client.get(self._url())

        assert response.status_code == 405

    def test_invalid_json_returns_400(self, client):
        body = b"not valid json {{{"
        sig = _make_signature(body)
        response = client.post(
            self._url(),
            data=body,
            content_type="application/json",
            HTTP_CALENDLY_WEBHOOK_SIGNATURE=sig,
        )

        assert response.status_code == 400

    def test_created_with_empty_invitee_uri_returns_400(self, client):
        payload = {
            "event": "invitee.created",
            "payload": {"uri": "", "scheduled_event": {}},
        }

        response = self._post(client, payload)

        assert response.status_code == 400

    def test_canceled_with_missing_invitee_uri_returns_400(self, client):
        payload = {
            "event": "invitee.canceled",
            "payload": {},
        }

        response = self._post(client, payload)

        assert response.status_code == 400

    # --- invitee.created happy paths ---

    def test_created_event_creates_booking(self, client):
        response = self._post(client, _created_payload())

        assert response.status_code == 200
        assert CalendlyBooking.objects.count() == 1
        booking = CalendlyBooking.objects.get()
        assert booking.calendly_invitee_uri == _INVITEE_URI
        assert booking.status == "active"
        assert booking.invitee_email == "ada@example.com"

    def test_created_event_is_idempotent_on_redelivery(self, client):
        self._post(client, _created_payload())
        self._post(client, _created_payload())  # duplicate delivery

        assert CalendlyBooking.objects.count() == 1

    def test_created_event_returns_500_on_db_error(self, client):
        target = "bookings.views.CalendlyBooking.objects.update_or_create"
        with patch(target, side_effect=Exception("DB error")):
            response = self._post(client, _created_payload())

        assert response.status_code == 500

    # --- invitee.canceled happy paths ---

    def test_canceled_event_upserts_booking_with_canceled_status(self, client):
        response = self._post(client, _canceled_payload())

        assert response.status_code == 200
        booking = CalendlyBooking.objects.get(calendly_invitee_uri=_INVITEE_URI)
        assert booking.status == "canceled"

    def test_canceled_after_created_updates_status_to_canceled(self, client):
        self._post(client, _created_payload())
        assert CalendlyBooking.objects.get().status == "active"

        self._post(client, _canceled_payload())

        assert CalendlyBooking.objects.count() == 1
        assert CalendlyBooking.objects.get().status == "canceled"

    def test_canceled_event_returns_500_on_db_error(self, client):
        target = "bookings.views.CalendlyBooking.objects.update_or_create"
        with patch(target, side_effect=Exception("DB error")):
            response = self._post(client, _canceled_payload())

        assert response.status_code == 500

    # --- Unhandled events ---

    def test_unhandled_event_type_returns_200_without_db_write(self, client):
        payload = {
            "event": "routing_form_submission.created",
            "payload": {"uri": _INVITEE_URI},
        }

        response = self._post(client, payload)

        assert response.status_code == 200
        assert CalendlyBooking.objects.count() == 0

    # --- Signature / authentication guard-rails ---

    def test_missing_signature_header_returns_403(self, client):
        body = json.dumps(_created_payload()).encode("utf-8")
        response = client.post(
            self._url(),
            data=body,
            content_type="application/json",
            # No HTTP_CALENDLY_WEBHOOK_SIGNATURE header.
        )

        assert response.status_code == 403

    def test_wrong_signature_returns_403(self, client):
        response = self._post(client, _created_payload(), signature="t=9999,v1=badhexvalue")

        assert response.status_code == 403
        assert CalendlyBooking.objects.count() == 0

    def test_stale_timestamp_returns_403(self, client):
        stale_ts = int(time.time()) - 600  # 10 minutes ago — beyond the 5-minute window
        response = self._post(client, _created_payload(), ts=stale_ts)

        assert response.status_code == 403
        assert CalendlyBooking.objects.count() == 0

    def test_unconfigured_signing_key_returns_403(self, client, settings):
        settings.CALENDLY_SIGNING_KEY = ""

        response = self._post(client, _created_payload())

        assert response.status_code == 403
        assert CalendlyBooking.objects.count() == 0

    def test_valid_signature_with_wrong_key_returns_403(self, client):
        # Signature computed with a different key than what's in settings.
        response = self._post(client, _created_payload(), signing_key="some-other-key")

        assert response.status_code == 403
        assert CalendlyBooking.objects.count() == 0

