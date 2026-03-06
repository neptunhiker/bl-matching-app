"""
Phase 2 — Security tests for the Brevo webhook endpoint.

These tests cover the two protective layers in front of all business logic:
  1. Shared-secret validation
  2. IP allowlist validation

No EmailLog objects are created — the minimal payload used here either gets
rejected before reaching the DB or returns 200 via the "no tag, ignoring" path.
"""
import pytest

from .conftest import BREVO_IP, MINIMAL_PAYLOAD, NON_BREVO_IP, TEST_SECRET, WEBHOOK_PATH


# ── helpers ──────────────────────────────────────────────────────────────────

def post_webhook(client, path, *, ip=None, body=MINIMAL_PAYLOAD):
    """POST to the webhook endpoint, optionally spoofing REMOTE_ADDR."""
    kwargs = {"data": body, "content_type": "application/json"}
    if ip:
        kwargs["REMOTE_ADDR"] = ip
    return client.post(path, **kwargs)


# ── Layer 1: shared-secret validation ────────────────────────────────────────

@pytest.mark.django_db
class TestSecretValidation:
    """IP check is disabled for all tests in this class so it doesn't interfere."""

    @pytest.fixture(autouse=True)
    def _disable_ip_check(self, settings):
        settings.BREVO_WEBHOOK_SECRET = TEST_SECRET
        settings.BREVO_WEBHOOK_IP_RANGES = None  # bypass IP check

    def test_wrong_secret_returns_403(self, client):
        url = f"{WEBHOOK_PATH}?secret=completely-wrong"
        response = post_webhook(client, url)
        assert response.status_code == 403

    def test_missing_secret_query_param_returns_403(self, client):
        """No ?secret= in the URL at all."""
        response = post_webhook(client, WEBHOOK_PATH)
        assert response.status_code == 403

    def test_unconfigured_secret_returns_403(self, client, settings):
        """
        If BREVO_WEBHOOK_SECRET is empty (forgotten in .env), every request
        must be rejected — endpoint fails closed, not open.
        """
        settings.BREVO_WEBHOOK_SECRET = ""
        url = f"{WEBHOOK_PATH}?secret="  # even an empty secret should be refused
        response = post_webhook(client, url)
        assert response.status_code == 403

    def test_correct_secret_passes_secret_check(self, client):
        """A request with the right secret is not rejected with 403."""
        url = f"{WEBHOOK_PATH}?secret={TEST_SECRET}"
        response = post_webhook(client, url)
        assert response.status_code != 403


# ── Layer 2: IP allowlist ─────────────────────────────────────────────────────

@pytest.mark.django_db
class TestIPAllowlist:
    """Secret is always correct for these tests; only IP behaviour varies."""

    @pytest.fixture(autouse=True)
    def _set_secret(self, settings):
        settings.BREVO_WEBHOOK_SECRET = TEST_SECRET

    def test_disallowed_ip_returns_403(self, client, settings):
        """A request from an IP outside Brevo's ranges must be blocked."""
        settings.BREVO_WEBHOOK_IP_RANGES = "1.179.112.0/20,172.246.240.0/20"
        url = f"{WEBHOOK_PATH}?secret={TEST_SECRET}"
        response = post_webhook(client, url, ip=NON_BREVO_IP)
        assert response.status_code == 403

    def test_allowed_ip_passes(self, client, settings):
        """A request from within a Brevo range must not be blocked by the IP check."""
        settings.BREVO_WEBHOOK_IP_RANGES = "1.179.112.0/20,172.246.240.0/20"
        url = f"{WEBHOOK_PATH}?secret={TEST_SECRET}"
        response = post_webhook(client, url, ip=BREVO_IP)
        assert response.status_code != 403

    def test_x_forwarded_for_used_behind_proxy(self, client, settings):
        """
        Behind Caddy, the real client IP arrives in X-Forwarded-For.
        The view must extract it correctly and block non-Brevo IPs from that header.
        """
        settings.BREVO_WEBHOOK_IP_RANGES = "1.179.112.0/20,172.246.240.0/20"
        url = f"{WEBHOOK_PATH}?secret={TEST_SECRET}"
        response = client.post(
            url,
            data=MINIMAL_PAYLOAD,
            content_type="application/json",
            # Caddy would set REMOTE_ADDR to the internal container IP and
            # X-Forwarded-For to the real client IP.
            REMOTE_ADDR="10.0.0.1",
            HTTP_X_FORWARDED_FOR=NON_BREVO_IP,
        )
        assert response.status_code == 403

    def test_ip_check_skipped_when_ranges_none(self, client, settings):
        """
        Setting BREVO_WEBHOOK_IP_RANGES=None (empty in .env) disables the
        IP check — used for local dev and ngrok smoke testing.
        """
        settings.BREVO_WEBHOOK_IP_RANGES = None
        url = f"{WEBHOOK_PATH}?secret={TEST_SECRET}"
        response = post_webhook(client, url, ip=NON_BREVO_IP)
        assert response.status_code != 403


# ── Request parsing ───────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestRequestParsing:
    """Auth passes; tests cover malformed request bodies."""

    @pytest.fixture(autouse=True)
    def _auth(self, settings):
        settings.BREVO_WEBHOOK_SECRET = TEST_SECRET
        settings.BREVO_WEBHOOK_IP_RANGES = None

    def test_malformed_json_returns_400(self, client):
        url = f"{WEBHOOK_PATH}?secret={TEST_SECRET}"
        response = client.post(url, data=b"not valid json {{{{", content_type="application/json")
        assert response.status_code == 400

    def test_empty_body_returns_400(self, client):
        url = f"{WEBHOOK_PATH}?secret={TEST_SECRET}"
        response = client.post(url, data=b"", content_type="application/json")
        assert response.status_code == 400
