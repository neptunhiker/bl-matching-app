"""
Phase 4 — Engagement event tests for the Brevo webhook endpoint.

Tests cover: opened, unique_opened, proxy_open, unique_proxy_open, click,
unsubscribed.

Key invariants:
- Only genuine human opens (opened, unique_opened) set opened_at.
- opened_at is written once — subsequent open events must not overwrite it.
- Proxy opens update status but must never touch opened_at.
"""
from datetime import datetime, timezone as dt_timezone

import pytest

from emails.models import EmailLog
from .conftest import TS_EVENT, WEBHOOK_PATH, TEST_SECRET, build_payload


# ── helper ───────────────────────────────────────────────────────────────────

def post_event(client, log_id, event, **extra):
    return client.post(
        f"{WEBHOOK_PATH}?secret={TEST_SECRET}",
        data=build_payload(event, log_id, **extra),
        content_type="application/json",
    )


# ── Phase 4 tests ─────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestEngagementEvents:

    @pytest.fixture(autouse=True)
    def _auth(self, auth_settings):
        pass

    # ── opened ────────────────────────────────────────────────────────────────

    def test_opened_sets_status_and_opened_at(self, client, email_log):
        """
        'opened' must update status to OPENED and set opened_at from ts_event.
        Matches the `opened` payload from the examples file (includes user_agent,
        device_used, mirror_link, contact_id).
        """
        response = post_event(
            client, email_log.id, "opened",
            user_agent="Mozilla/5.0 (Windows NT 5.1; rv:11.0) Gecko Firefox/11.0",
            device_used="DESKTOP",
            mirror_link="https://app-smtp.brevo.com/log/preview/abc",
            contact_id=8,
            ts_epoch=1604933623,
        )
        assert response.status_code == 200
        email_log.refresh_from_db()
        assert email_log.status == EmailLog.Status.OPENED
        expected_dt = datetime.fromtimestamp(TS_EVENT, tz=dt_timezone.utc)
        assert email_log.opened_at == expected_dt

    def test_opened_without_ts_event_falls_back_to_now(self, client, email_log):
        """If ts_event is missing, opened_at must still be set (not left None)."""
        import json
        data = json.loads(build_payload("opened", email_log.id))
        del data["ts_event"]
        response = client.post(
            f"{WEBHOOK_PATH}?secret={TEST_SECRET}",
            data=json.dumps(data),
            content_type="application/json",
        )
        assert response.status_code == 200
        email_log.refresh_from_db()
        assert email_log.opened_at is not None

    def test_second_opened_does_not_overwrite_opened_at(self, client, email_log):
        """
        First-wins rule: a second 'opened' event must not update opened_at.
        """
        # First open
        post_event(client, email_log.id, "opened")
        email_log.refresh_from_db()
        first_opened_at = email_log.opened_at
        assert first_opened_at is not None

        # Second open with a different ts_event
        import json
        data = json.loads(build_payload("opened", email_log.id))
        data["ts_event"] = TS_EVENT + 9999
        client.post(
            f"{WEBHOOK_PATH}?secret={TEST_SECRET}",
            data=json.dumps(data),
            content_type="application/json",
        )
        email_log.refresh_from_db()
        assert email_log.opened_at == first_opened_at

    # ── unique_opened ─────────────────────────────────────────────────────────

    def test_unique_opened_sets_status_and_opened_at(self, client, email_log):
        """
        'unique_opened' (Brevo's first-open event) must set status FIRST_OPENING
        and opened_at from ts_event.
        Matches the `first_opening` payload from the examples file.
        """
        response = post_event(
            client, email_log.id, "unique_opened",
            user_agent="Mozilla/5.0 (Windows NT 5.1; rv:11.0) Gecko Firefox/11.0",
            device_used="DESKTOP",
            mirror_link="https://app-smtp.brevo.com/log/preview/abc",
            contact_id=8,
            ts_epoch=1604933623,
        )
        assert response.status_code == 200
        email_log.refresh_from_db()
        assert email_log.status == EmailLog.Status.FIRST_OPENING
        expected_dt = datetime.fromtimestamp(TS_EVENT, tz=dt_timezone.utc)
        assert email_log.opened_at == expected_dt

    # ── proxy opens ───────────────────────────────────────────────────────────

    def test_proxy_open_sets_status_but_not_opened_at(self, client, email_log):
        """
        proxy_open (e.g. Apple MPP) must update status but must NOT set opened_at,
        as it inflates open metrics with machine-triggered events.
        """
        response = post_event(client, email_log.id, "proxy_open")
        assert response.status_code == 200
        email_log.refresh_from_db()
        assert email_log.status == EmailLog.Status.PROXY_OPEN
        assert email_log.opened_at is None

    def test_unique_proxy_open_sets_status_but_not_opened_at(self, client, email_log):
        """Same rule as proxy_open — unique_proxy_open must not set opened_at."""
        response = post_event(client, email_log.id, "unique_proxy_open")
        assert response.status_code == 200
        email_log.refresh_from_db()
        assert email_log.status == EmailLog.Status.UNIQUE_PROXY_OPEN
        assert email_log.opened_at is None

    def test_proxy_open_does_not_overwrite_existing_opened_at(self, client, email_log):
        """
        If a real open already set opened_at, a subsequent proxy_open must not
        clear or overwrite it.
        """
        post_event(client, email_log.id, "opened")
        email_log.refresh_from_db()
        real_opened_at = email_log.opened_at
        assert real_opened_at is not None

        post_event(client, email_log.id, "proxy_open")
        email_log.refresh_from_db()
        assert email_log.opened_at == real_opened_at

    # ── click ─────────────────────────────────────────────────────────────────

    def test_click_sets_status_clicked(self, client, email_log):
        response = post_event(client, email_log.id, "click")
        assert response.status_code == 200
        email_log.refresh_from_db()
        assert email_log.status == EmailLog.Status.CLICKED

    # ── unsubscribed ──────────────────────────────────────────────────────────

    def test_unsubscribed_sets_status(self, client, email_log):
        response = post_event(client, email_log.id, "unsubscribed")
        assert response.status_code == 200
        email_log.refresh_from_db()
        assert email_log.status == EmailLog.Status.UNSUBSCRIBED
