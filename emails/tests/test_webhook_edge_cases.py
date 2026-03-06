"""
Phase 5 — Edge case tests for the Brevo webhook endpoint.

Covers: missing/unknown tags, unknown event types, extra unknown payload fields,
and verifying the view always returns 200 to prevent Brevo from retrying.
"""
import json
import uuid

import pytest

from emails.models import EmailLog
from .conftest import TS_EVENT, WEBHOOK_PATH, TEST_SECRET, build_payload


# ── helper ───────────────────────────────────────────────────────────────────

def post_payload(client, payload: dict):
    return client.post(
        f"{WEBHOOK_PATH}?secret={TEST_SECRET}",
        data=json.dumps(payload),
        content_type="application/json",
    )


# ── Phase 5 tests ─────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestEdgeCases:

    @pytest.fixture(autouse=True)
    def _auth(self, auth_settings):
        pass

    # ── tag / correlation edge cases ──────────────────────────────────────────

    def test_no_tags_in_payload_returns_200_without_db_change(self, client, email_log):
        """
        Brevo sends a payload with no tags — we can't correlate to any log entry.
        Must return 200 (so Brevo stops retrying) and leave the DB untouched.
        """
        payload = {
            "event": "delivered",
            "email": "example@domain.com",
            "ts_event": TS_EVENT,
            # no "tags" key at all
        }
        response = post_payload(client, payload)
        assert response.status_code == 200
        email_log.refresh_from_db()
        assert email_log.status == EmailLog.Status.SENT  # unchanged default

    def test_empty_tags_list_returns_200_without_db_change(self, client, email_log):
        """tags key present but empty list — same behaviour as no tags."""
        payload = {
            "event": "delivered",
            "email": "example@domain.com",
            "ts_event": TS_EVENT,
            "tags": [],
        }
        response = post_payload(client, payload)
        assert response.status_code == 200
        email_log.refresh_from_db()
        assert email_log.status == EmailLog.Status.SENT

    def test_unknown_log_id_in_tags_returns_200_without_crash(self, client):
        """
        Tag contains a valid UUID that doesn't match any EmailLog in the DB.
        Must return 200 and not raise an exception (Brevo must not keep retrying).
        """
        nonexistent_id = str(uuid.uuid4())
        response = post_payload(client, {
            "event": "delivered",
            "email": "example@domain.com",
            "ts_event": TS_EVENT,
            "tags": [nonexistent_id],
        })
        assert response.status_code == 200

    def test_invalid_uuid_in_tags_returns_200_without_crash(self, client):
        """Tag value is not a valid UUID — must not crash the view."""
        response = post_payload(client, {
            "event": "delivered",
            "email": "example@domain.com",
            "ts_event": TS_EVENT,
            "tags": ["not-a-uuid-at-all"],
        })
        assert response.status_code == 200

    # ── unknown / unmapped event types ────────────────────────────────────────

    def test_unmapped_event_returns_200_without_db_change(self, client, email_log):
        """
        An event string not in BREVO_EVENT_MAP (e.g. a future Brevo event we
        don't handle yet) must be acknowledged silently without touching the DB.
        """
        response = post_payload(client, {
            "event": "some_future_event",
            "email": "example@domain.com",
            "ts_event": TS_EVENT,
            "tags": [str(email_log.id)],
        })
        assert response.status_code == 200
        email_log.refresh_from_db()
        assert email_log.status == EmailLog.Status.SENT  # unchanged

    def test_missing_event_field_returns_200_without_crash(self, client, email_log):
        """Payload with no 'event' key — get(event) returns None, must not crash."""
        response = post_payload(client, {
            "email": "example@domain.com",
            "ts_event": TS_EVENT,
            "tags": [str(email_log.id)],
        })
        assert response.status_code == 200

    # ── extra / unknown payload fields ────────────────────────────────────────

    def test_extra_fields_in_payload_do_not_cause_errors(self, client, email_log):
        """
        Brevo may add new fields in the future (or send fields like reason,
        user_agent, device_used, contact_id, mirror_link). The view must tolerate
        any extra fields without crashing.
        """
        response = post_payload(client, {
            "event": "delivered",
            "email": "example@domain.com",
            "ts_event": TS_EVENT,
            "tags": [str(email_log.id)],
            # Fields present in various Brevo payloads
            "reason": "some bounce reason",
            "user_agent": "Mozilla/5.0 ...",
            "device_used": "MOBILE",
            "contact_id": 42,
            "mirror_link": "https://app-smtp.brevo.com/log/preview/xyz",
            "ts_epoch": 1604933623,
            "some_future_field": "some_future_value",
        })
        assert response.status_code == 200
        email_log.refresh_from_db()
        assert email_log.status == EmailLog.Status.DELIVERED

    # ── idempotency ───────────────────────────────────────────────────────────

    def test_duplicate_delivered_event_is_idempotent(self, client, email_log):
        """
        Brevo may send the same webhook event more than once (retry on timeout).
        A second identical 'delivered' event must not crash and the final state
        must still be correct.
        """
        for _ in range(2):
            response = post_payload(client, {
                "event": "delivered",
                "email": "example@domain.com",
                "ts_event": TS_EVENT,
                "tags": [str(email_log.id)],
            })
            assert response.status_code == 200

        email_log.refresh_from_db()
        assert email_log.status == EmailLog.Status.DELIVERED
