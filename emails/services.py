from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from .models import EmailLog


def send_email(
    to: str,
    subject: str,
    template_name: str,
    context: dict,
    sent_by=None,
) -> EmailLog:
    """
    Render an HTML email template, send it, and log the result.

    Args:
        to:            Recipient email address.
        subject:       Email subject line.
        template_name: Path to the HTML template (relative to templates/).
        context:       Template context dict.
        sent_by:       User instance triggering the send (optional).

    Returns:
        EmailLog instance with status 'sent' or 'failed'.
    """
    html_body = render_to_string(template_name, context)
    # Plain-text fallback: strip tags naively (good enough for transactional mail)
    plain_body = ' '.join(html_body.split())  # collapses whitespace

    # Save first so we have a UUID to tag the outgoing message with.
    # Brevo echoes X-Mailin-Tag back in webhook payloads, letting us look up
    # this log entry when the delivery/bounce event arrives.
    log = EmailLog(to=to, subject=subject, html_body=html_body, sent_by=sent_by)
    log.save()

    try:
        bcc = [settings.EMAIL_BCC] if getattr(settings, 'EMAIL_BCC', None) else []
        msg = EmailMultiAlternatives(subject=subject, body=plain_body, to=[to], bcc=bcc)
        msg.attach_alternative(html_body, 'text/html')
        # Tag with log UUID so Brevo webhooks can reference this log entry.
        msg.extra_headers['X-Mailin-Tag'] = str(log.id)
        msg.send()
        log.status = EmailLog.Status.SENT
    except Exception as exc:  # noqa: BLE001
        log.status = EmailLog.Status.FAILED
        log.error_message = str(exc)

    log.save(update_fields=['status', 'error_message'])
    return log
