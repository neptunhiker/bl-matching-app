import logging
import re

from anymail.message import AnymailMessage
from django.template.loader import render_to_string
from django.conf import settings

from accounts.models import User
from .models import EmailLog

logger = logging.getLogger(__name__)


def send_email(
    to: str,
    subject: str,
    template_name: str,
    context: dict,
    sent_by: str,
    triggered_by: str,
    request_to_coach=None,
    matching_attempt=None,
) -> EmailLog:
    """
    Render an HTML email template, send it, and log the result.

    Args:
        to:               Recipient email address.
        subject:          Email subject line.
        template_name:    Path to the HTML template (relative to templates/).
        context:          Template context dict.
        sent_by:          Who/what is sending this email (e.g. "User:123" or "System")
        triggered_by:     Who/what triggered this email (e.g. "system" or "staff")
        request_to_coach: RequestToCoach instance this email relates to (optional).
        matching_attempt: MatchingAttempt instance this email relates to (optional).

    Returns:
        EmailLog instance with status 'sent' or 'failed'.
    """
    html_body = render_to_string(template_name, context)
    # Plain-text fallback: strip tags naively (good enough for transactional mail)
    plain_body = ' '.join(html_body.split())  # collapses whitespace

    # Normalize recipient address: tests sometimes pass markdown-style
    # links like "[name](mailto:recipient@example.com)" or
    # "Name <recipient@example.com>". Extract a plain email address so
    # anymail/django don't choke on unexpected formats.
    def _extract_email(value: str) -> str:
        if not isinstance(value, str):
            return value
        # Markdown mailto link: [text](mailto:email)
        m = re.search(r"\[.*?\]\(mailto:(.*?)\)", value)
        if m:
            return m.group(1)
        # Angle-bracket form: Name <email@example.com>
        m = re.search(r"<([^>]+)>", value)
        if m:
            return m.group(1)
        return value.strip()

    to_addr = _extract_email(to)

    # Save first so we have a UUID to tag the outgoing message with.
    # Brevo echoes X-Mailin-Tag back in webhook payloads, letting us look up
    # this log entry when the delivery/bounce event arrives.
    log = EmailLog(
        to=to_addr,
        subject=subject,
        html_body=html_body,
        sent_by=sent_by,
        request_to_coach=request_to_coach,
        matching_attempt=matching_attempt,
        email_trigger=triggered_by,
    )
    log.save()

    logger.debug(
        "send_email: backend=%s to=%s subject=%r log_id=%s",
        settings.EMAIL_BACKEND,
        to,
        subject,
        log.id,
    )

    try:
        bcc = [settings.EMAIL_BCC] if getattr(settings, 'EMAIL_BCC', None) else []
        msg = AnymailMessage(subject=subject, body=plain_body, to=[to_addr], bcc=bcc)
        msg.attach_alternative(html_body, 'text/html')
        # Tag with log UUID so Brevo webhooks can reference this log entry.
        msg.tags = [str(log.id)]
        result = msg.send()
        logger.info(
            "send_email: msg.send() returned %s for log_id=%s (to=%s)",
            result,
            log.id,
            to,
        )
        log.status = EmailLog.Status.SENT
    except Exception as exc:  # noqa: BLE001
        logger.exception("send_email: FAILED for log_id=%s (to=%s): %s", log.id, to, exc)
        log.status = EmailLog.Status.FAILED
        log.error_message = str(exc)

    log.save(update_fields=['status', 'error_message'])
    return log
