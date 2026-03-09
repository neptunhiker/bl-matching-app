import logging

from anymail.message import AnymailMessage
from django.template.loader import render_to_string
from django.conf import settings
from .models import EmailLog

logger = logging.getLogger(__name__)


def send_email(
    to: str,
    subject: str,
    template_name: str,
    context: dict,
    sent_by: str,
    email_trigger: str = EmailLog.EmailTrigger.AUTOMATED,
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
        request_to_coach: RequestToCoach instance this email relates to (optional).
        matching_attempt: MatchingAttempt instance this email relates to (optional).

    Returns:
        EmailLog instance with status 'sent' or 'failed'.
    """
    html_body = render_to_string(template_name, context)
    # Plain-text fallback: strip tags naively (good enough for transactional mail)
    plain_body = ' '.join(html_body.split())  # collapses whitespace

    # Save first so we have a UUID to tag the outgoing message with.
    # Brevo echoes X-Mailin-Tag back in webhook payloads, letting us look up
    # this log entry when the delivery/bounce event arrives.
    log = EmailLog(
        to=to,
        subject=subject,
        html_body=html_body,
        sent_by=sent_by,
        request_to_coach=request_to_coach,
        matching_attempt=matching_attempt,
        email_trigger=email_trigger,
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
        msg = AnymailMessage(subject=subject, body=plain_body, to=[to], bcc=bcc)
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
