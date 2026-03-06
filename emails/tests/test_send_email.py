"""
Tests for emails.services.send_email().

Verifies that send_email():
  - Creates an EmailLog row with correct fields.
  - Sets status to 'sent' on success, 'failed' on exception.
  - Attaches the log UUID as an Anymail tag (the Phase 2 change from
    X-Mailin-Tag header to msg.tags).
  - Correctly includes / excludes the BCC address.

The anymail test backend is activated for every test via the autouse fixture
in the root conftest.py, so no real API calls are made.
render_to_string is mocked in each test so no specific template file is needed.
"""
from unittest.mock import patch

import pytest
from django.core import mail

from emails.models import EmailLog
from emails.services import send_email

# ── constants ────────────────────────────────────────────────────────────────

FAKE_HTML = "<html><body><p>Hello</p></body></html>"
TEMPLATE = "emails/base_email.html"  # mocked out; path is never used for real


# ── helper ───────────────────────────────────────────────────────────────────

def _send(**kwargs) -> EmailLog:
    """
    Call send_email() with sensible defaults.
    render_to_string is mocked so tests don't depend on template content.
    """
    defaults = dict(
        to="recipient@example.com",
        subject="Test Subject",
        template_name=TEMPLATE,
        context={},
    )
    defaults.update(kwargs)
    with patch("emails.services.render_to_string", return_value=FAKE_HTML):
        return send_email(**defaults)


# ── tests ────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestSendEmail:

    def test_creates_email_log(self):
        """send_email() must persist an EmailLog row."""
        log = _send()
        assert EmailLog.objects.filter(pk=log.id).exists()
        assert log.to == "recipient@example.com"
        assert log.subject == "Test Subject"

    def test_log_status_sent_on_success(self):
        """A successful send must set status to SENT."""
        log = _send()
        assert log.status == EmailLog.Status.SENT

    def test_tag_is_log_uuid(self):
        """
        The outgoing message's tags must contain the EmailLog UUID as a string.
        This is the core assertion for Phase 2: the UUID travels via the API
        tags field rather than the X-Mailin-Tag email header.
        """
        log = _send()
        assert len(mail.outbox) == 1
        assert mail.outbox[0].tags == [str(log.id)]

    def test_bcc_included_when_configured(self, settings):
        """When EMAIL_BCC is set the outgoing message must include it as BCC."""
        settings.EMAIL_BCC = "bcc@example.com"
        _send()
        assert "bcc@example.com" in mail.outbox[0].bcc

    def test_no_bcc_when_not_configured(self, settings):
        """When EMAIL_BCC is empty no BCC address must be added."""
        settings.EMAIL_BCC = ""
        _send()
        assert mail.outbox[0].bcc == []

    def test_log_status_failed_on_error(self):
        """
        When the backend raises, status must be FAILED and error_message
        must contain the exception text.
        """
        with patch("emails.services.AnymailMessage.send", side_effect=Exception("API down")):
            log = _send()
        assert log.status == EmailLog.Status.FAILED
        assert "API down" in log.error_message
