from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
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

    log = EmailLog(to=to, subject=subject, html_body=html_body, sent_by=sent_by)

    try:
        msg = EmailMultiAlternatives(subject=subject, body=plain_body, to=[to])
        msg.attach_alternative(html_body, 'text/html')
        msg.send()
        log.status = EmailLog.Status.SENT
    except Exception as exc:  # noqa: BLE001
        log.status = EmailLog.Status.FAILED
        log.error_message = str(exc)

    log.save()
    return log
