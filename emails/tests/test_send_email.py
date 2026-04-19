from unittest.mock import patch


import pytest
from django.core import mail

from emails.models import EmailLog
from emails.services import send_email
"""
Tests for emails.services.send_email().

Verifies that send_email():

* Creates an EmailLog row with correct fields.
* Sets status to 'sent' on success, 'failed' on exception.
* Attaches the log UUID as an Anymail tag.
* Correctly includes / excludes the BCC address.
* Persists the rendered HTML body.
* Generates a plain-text fallback.
* Correctly links RequestToCoach / MatchingAttempt when provided.
* Attaches HTML alternative to the outgoing message.
* Saves the email trigger metadata.
* Creates exactly one EmailLog per send.

The anymail test backend is activated via pytest settings so no real API
calls are made.

render_to_string is mocked in each test so no template file is required.
"""

from unittest.mock import patch

import pytest
from django.core import mail

from emails.models import EmailLog
from emails.services import send_email

# ── constants ────────────────────────────────────────────────────────────────

FAKE_HTML = "<html><body><p>Hello</p></body></html>"
TEMPLATE = "emails/base_email.html"  # never actually rendered

# ── helper ───────────────────────────────────────────────────────────────────

def _send(**kwargs) -> EmailLog:
    """
    Call send_email() with sensible defaults.
    render_to_string is mocked so tests don't depend on template content.
    """
    defaults = dict(
    to="[recipient@example.com](mailto:recipient@example.com)",
    subject="Test Subject",
    template_name=TEMPLATE,
    context={},
    triggered_by="system",
    sent_by="system",
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

    def test_creates_exactly_one_log_entry(self):
        """Only one EmailLog row should be created per send."""
        initial_count = EmailLog.objects.count()

        _send()

        assert EmailLog.objects.count() == initial_count + 1

    def test_log_status_sent_on_success(self):
        """A successful send must set status to SENT."""
        log = _send()

        assert log.status == EmailLog.Status.SENT

    def test_log_status_failed_on_error(self):
        """
        When the backend raises, status must be FAILED and error_message
        must contain the exception text.
        """
        with patch("emails.services.AnymailMessage.send", side_effect=Exception("API down")):
            log = _send()

        assert log.status == EmailLog.Status.FAILED
        assert "API down" in log.error_message

    def test_tag_is_log_uuid(self):
        """
        The outgoing message's tags must contain the EmailLog UUID as a string.
        This allows Brevo webhooks to reference this log entry.
        """
        log = _send()

        assert len(mail.outbox) == 1
        assert mail.outbox[0].tags == [str(log.id)]

    def test_bcc_included_when_configured(self, settings):
        """When EMAIL_BCC is set the outgoing message must include it."""
        settings.EMAIL_BCC = "bcc@example.com"

        _send()

        assert "bcc@example.com" in mail.outbox[0].bcc

    def test_no_bcc_when_not_configured(self, settings):
        """When EMAIL_BCC is empty no BCC address must be added."""
        settings.EMAIL_BCC = ""

        _send()

        assert mail.outbox[0].bcc == []

    def test_html_body_is_saved(self):
        """The rendered HTML body should be stored in EmailLog."""
        log = _send()

        assert log.html_body == FAKE_HTML

    def test_plain_text_body_generated(self):
        """Plain-text fallback should be generated from the HTML."""
        _send()

        msg = mail.outbox[0]

        assert "Hello" in msg.body

    def test_html_alternative_attached(self):
        """The HTML alternative must be attached to the outgoing email."""
        _send()

        msg = mail.outbox[0]

        assert msg.alternatives
        assert msg.alternatives[0][0] == FAKE_HTML
        assert msg.alternatives[0][1] == "text/html"

    def test_email_trigger_is_saved(self):
        """The email trigger metadata must be stored in EmailLog."""
        log = _send(triggered_by="staff")

        assert log.email_trigger == "staff"

    def test_links_request_to_coach(self, rtc):
        """If a RequestToCoach is provided it must be stored in EmailLog."""
        log = _send(request_to_coach=rtc)

        assert log.request_to_coach == rtc

    def test_links_matching_attempt(self, matching_attempt):
        """If a MatchingAttempt is provided it must be stored in EmailLog."""
        log = _send(matching_attempt=matching_attempt)

        assert log.matching_attempt == matching_attempt


# ---------------------------------------------------------------------------
# send_intro_call_reminder_email_to_coach
# ---------------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
class TestSendIntroCallReminderEmailToCoach:
    """
    Verifies that send_intro_call_reminder_email_to_coach() dispatches send_email
    with the correct recipient and template.
    """

    def test_dispatches_correct_email(self, matching_attempt, coach):
        """
        The function should call send_email with the coach's email address and
        the intro_call_reminder_to_coach template.
        """
        from emails.services import send_intro_call_reminder_email_to_coach

        matching_attempt.matched_coach = coach
        matching_attempt.save(update_fields=["matched_coach"])

        with patch("emails.services.send_email") as mock_send_email, \
             patch("emails.services.generate_intro_call_feedback_url", return_value="http://example.com/confirm"):
            send_intro_call_reminder_email_to_coach(matching_attempt)

        mock_send_email.assert_called_once()
        call_kwargs = mock_send_email.call_args.kwargs
        assert call_kwargs["to"] == coach.user.email
        assert call_kwargs["template_name"] == "emails/intro_call_reminder_to_coach.html"
        assert call_kwargs["matching_attempt"] == matching_attempt
