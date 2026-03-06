"""
Phase 3 — Delivery lifecycle event tests for the Brevo webhook endpoint.

Each test sends a real-shaped Brevo payload (matching the structure from the
Brevo docs / temp_webhook_payload_examples.py) and asserts the correct
EmailLog.status and timestamp fields are set.

Security checks are bypassed via the `auth_settings` fixture so these tests
focus purely on delivery logic.
"""
from datetime import datetime, timezone as dt_timezone

import pytest

from emails.models import EmailLog
from .conftest import TS_EVENT, WEBHOOK_PATH, TEST_SECRET, build_payload


# ── helper ───────────────────────────────────────────────────────────────────

def post_event(client, log_id, event, **extra):
    """POST a Brevo-shaped payload for `event` and return the response."""
    return client.post(
        f"{WEBHOOK_PATH}?secret={TEST_SECRET}",
        data=build_payload(event, log_id, **extra),
        content_type="application/json",
    )


# ── Phase 3 tests ─────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestDeliveryEvents:
    """All delivery lifecycle events mapped in BREVO_EVENT_MAP."""

    @pytest.fixture(autouse=True)
    def _auth(self, auth_settings):
        pass  # enables both settings overrides for every test in this class

    def test_request_event_sets_status_sent(self, client, email_log):
        """
        Brevo fires 'request' when it accepts the message for sending.
        Matches the `sent` payload from the examples file.
        """
        response = post_event(client, email_log.id, "request",
                              ts_epoch=1604933654,
                              mirror_link="https://app-smtp.brevo.com/log/preview/abc",
                              contact_id=8)
        assert response.status_code == 200
        email_log.refresh_from_db()
        assert email_log.status == EmailLog.Status.SENT

    def test_delivered_sets_status_and_delivered_at_from_ts_event(self, client, email_log):
        """
        'delivered' must update status and set delivered_at from ts_event.
        Matches the `delivered` payload from the examples file.
        """
        response = post_event(client, email_log.id, "delivered")
        assert response.status_code == 200
        email_log.refresh_from_db()
        assert email_log.status == EmailLog.Status.DELIVERED
        expected_dt = datetime.fromtimestamp(TS_EVENT, tz=dt_timezone.utc)
        assert email_log.delivered_at == expected_dt

    def test_delivered_without_ts_event_falls_back_to_now(self, client, email_log):
        """
        If Brevo omits ts_event (shouldn't happen but must not crash),
        delivered_at should be set to approximately now rather than left as None.
        """
        payload_without_ts = build_payload("delivered", email_log.id)
        import json
        data = json.loads(payload_without_ts)
        del data["ts_event"]
        response = client.post(
            f"{WEBHOOK_PATH}?secret={TEST_SECRET}",
            data=json.dumps(data),
            content_type="application/json",
        )
        assert response.status_code == 200
        email_log.refresh_from_db()
        assert email_log.status == EmailLog.Status.DELIVERED
        assert email_log.delivered_at is not None

    def test_deferred_sets_status_deferred(self, client, email_log):
        """Brevo fires 'deferred' when delivery is temporarily delayed."""
        response = post_event(client, email_log.id, "deferred")
        assert response.status_code == 200
        email_log.refresh_from_db()
        assert email_log.status == EmailLog.Status.DEFERRED

    def test_soft_bounce_sets_status(self, client, email_log):
        """
        'soft_bounce' includes a 'reason' field — must not crash.
        Matches the `soft_bounce` payload from the examples file.
        """
        response = post_event(client, email_log.id, "soft_bounce",
                              reason="server is down")
        assert response.status_code == 200
        email_log.refresh_from_db()
        assert email_log.status == EmailLog.Status.SOFT_BOUNCED

    def test_hard_bounce_sets_status(self, client, email_log):
        """
        'hard_bounce' includes both 'reason' and 'ts_epoch' — must not crash.
        Matches the `hard_bounce` payload from the examples file.
        """
        response = post_event(client, email_log.id, "hard_bounce",
                              reason="server is down",
                              ts_epoch=1604933653)
        assert response.status_code == 200
        email_log.refresh_from_db()
        assert email_log.status == EmailLog.Status.HARD_BOUNCED

    def test_blocked_sets_status(self, client, email_log):
        """
        Matches the `blocked` payload from the examples file.
        """
        response = post_event(client, email_log.id, "blocked",
                              ts_epoch=1604933623)
        assert response.status_code == 200
        email_log.refresh_from_db()
        assert email_log.status == EmailLog.Status.BLOCKED

    def test_invalid_email_sets_status(self, client, email_log):
        """
        Matches the `invalid_email` payload from the examples file.
        """
        response = post_event(client, email_log.id, "invalid_email",
                              ts_epoch=1604933623)
        assert response.status_code == 200
        email_log.refresh_from_db()
        assert email_log.status == EmailLog.Status.INVALID

    def test_spam_sets_status(self, client, email_log):
        """
        The spam payload in the examples file is minimal (no subject/template_id).
        Ensure the view handles a sparse payload without crashing.
        """
        # Build a minimal spam payload matching the examples file exactly
        import json
        payload = json.dumps({
            "event": "spam",
            "email": "example@domain.com",
            "id": "xxxxx",
            "date": "2020-10-09 00:00:00",
            "ts": 1604933619,
            "message-id": "201798300811.5787683@relay.domain.com",
            "ts_event": TS_EVENT,
            "X-Mailin-custom": "some_custom_header",
            "tags": [str(email_log.id)],
        })
        response = client.post(
            f"{WEBHOOK_PATH}?secret={TEST_SECRET}",
            data=payload,
            content_type="application/json",
        )
        assert response.status_code == 200
        email_log.refresh_from_db()
        assert email_log.status == EmailLog.Status.SPAM

    def test_delivery_events_do_not_set_opened_at(self, client, email_log):
        """
        None of the delivery events should ever set opened_at — that is
        exclusively for human open events.
        """
        for event in ("request", "delivered", "deferred",
                      "soft_bounce", "hard_bounce", "blocked",
                      "invalid_email", "spam"):
            log = EmailLog.objects.create(
                to="example@domain.com",
                subject="Test",
                html_body="<p>x</p>",
            )
            post_event(client, log.id, event)
            log.refresh_from_db()
            assert log.opened_at is None, (
                f"opened_at should not be set for event '{event}'"
            )
