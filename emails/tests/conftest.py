import json
import pytest

from emails.models import EmailLog

# ── shared constants ────────────────────────────────────────────────────────

TEST_SECRET = "test-webhook-secret-for-pytest"
WEBHOOK_PATH = "/emails/webhooks/brevo/"

# A valid Brevo IP from the 1.179.112.0/20 range
BREVO_IP = "1.179.112.1"
# An IP outside all Brevo ranges
NON_BREVO_IP = "192.168.1.100"

# Timestamp used across all payload fixtures (seconds, UTC)
TS_EVENT = 1604933654

# Minimal payload: unknown event + no tags → view returns 200 without any DB
# access. Useful for testing the security layers in isolation.
MINIMAL_PAYLOAD = json.dumps({"event": "ignored_event"})


# ── shared fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def webhook_url():
    """Webhook URL with the correct test secret appended."""
    return f"{WEBHOOK_PATH}?secret={TEST_SECRET}"


@pytest.fixture
def auth_settings(settings):
    """
    Disable both security layers so business-logic tests aren't blocked by them.
    Uses pytest-django's `settings` fixture so overrides are scoped to the test.
    """
    settings.BREVO_WEBHOOK_SECRET = TEST_SECRET
    settings.BREVO_WEBHOOK_IP_RANGES = None
    return settings


@pytest.fixture
def email_log(db):
    """A minimal EmailLog in the test DB, ready to be updated by webhook events."""
    return EmailLog.objects.create(
        to="example@domain.com",
        subject="My first Transactional",
        html_body="<p>Hello</p>",
    )


def build_payload(event: str, log_id, **extra) -> str:
    """
    Build a Brevo webhook payload using the real field structure from the
    Brevo documentation examples, injecting the test log's UUID as the tag.
    Extra keyword arguments are merged in to allow per-event fields (e.g. reason).
    """
    base = {
        "event": event,
        "email": "example@domain.com",
        "id": "xxxxx",
        "date": "2020-10-09 00:00:00",
        "ts": 1604933619,
        "message-id": "201798300811.5787683@relay.domain.com",
        "ts_event": TS_EVENT,
        "subject": "My first Transactional",
        "X-Mailin-custom": "some_custom_header",
        "sending_ip": "xxx.xxx.xxx.xxx",
        "template_id": 22,
        "tags": [str(log_id)],
    }
    base.update(extra)
    return json.dumps(base)
