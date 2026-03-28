import ipaddress
import json
import logging
import secrets
from datetime import datetime, timezone as dt_timezone

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import DetailView
from django.conf import settings

from .models import EmailLog

logger = logging.getLogger(__name__)

class EmailLogDetailView(LoginRequiredMixin, DetailView):
    model = EmailLog
    template_name = 'emails/email_log_detail.html'
    context_object_name = 'email_log'



def _get_client_ip(request) -> str:
    """
    Return the real client IP, accounting for Caddy's X-Forwarded-For header.
    The leftmost address in X-Forwarded-For is the original client.
    Falls back to REMOTE_ADDR for direct connections (local dev).
    """
    forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


def _ip_is_allowed(ip_str: str, ranges_csv: str) -> bool:
    """
    Return True if ip_str falls within any CIDR in the comma-separated ranges_csv.
    Reads the authoritative list from settings.BREVO_WEBHOOK_IP_RANGES via the caller.
    An empty/unparseable IP string is always rejected.
    """
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return any(
        ip in ipaddress.ip_network(cidr.strip())
        for cidr in ranges_csv.split(',')
    )


# Map Brevo webhook event names → EmailLog.Status values.
# Full list: https://developers.brevo.com/docs/transactional-webhooks
BREVO_EVENT_MAP = {
    # Delivery — keys are the exact "event" strings Brevo sends in the payload
    'request':         EmailLog.Status.SENT,
    'delivered':       EmailLog.Status.DELIVERED,
    'deferred':        EmailLog.Status.DEFERRED,
    'soft_bounce':     EmailLog.Status.SOFT_BOUNCED,
    'hard_bounce':     EmailLog.Status.HARD_BOUNCED,
    'blocked':         EmailLog.Status.BLOCKED,
    'invalid_email':   EmailLog.Status.INVALID,
    'error':           EmailLog.Status.ERROR,
    'spam':            EmailLog.Status.SPAM,
    'unsubscribed':    EmailLog.Status.UNSUBSCRIBED,
    # Engagement
    'opened':          EmailLog.Status.OPENED,
    'unique_opened':   EmailLog.Status.FIRST_OPENING,
    'click':           EmailLog.Status.CLICKED,
    'proxy_open':      EmailLog.Status.PROXY_OPEN,
    'unique_proxy_open': EmailLog.Status.UNIQUE_PROXY_OPEN,
}


@method_decorator(csrf_exempt, name='dispatch')
class BrevoWebhookView(View):
    """
    Receives transactional email event webhooks from Brevo.

    Register this URL in Brevo under:
      Transactional → Settings → Webhook → Notifications

    Security (two layers):
    1. Shared secret as a query parameter:
         https://yourdomain.de/emails/webhooks/brevo/?secret=<BREVO_WEBHOOK_SECRET>
       Set BREVO_WEBHOOK_SECRET in your .env file.
    2. IP allowlist: only Brevo's published webhook IP ranges are accepted.
       Set BREVO_WEBHOOK_IP_RANGES= (empty) in .env to bypass during local/ngrok testing.
    """

    def post(self, request, *args, **kwargs):
        
        if request.content_type != "application/json":
            return HttpResponseBadRequest("Expected JSON.")
        
        # --- Shared-secret check (fail closed if not configured) ---
        expected_secret = getattr(settings, 'BREVO_WEBHOOK_SECRET', '')
        if not expected_secret:
            logger.error("Brevo webhook: BREVO_WEBHOOK_SECRET is not configured — rejecting request.")
            return HttpResponseForbidden("Webhook secret not configured.")
        provided = request.GET.get('secret', '')
        if not secrets.compare_digest(provided, expected_secret):
            logger.warning("Brevo webhook: invalid secret received.")
            return HttpResponseForbidden("Invalid secret.")

        # --- IP allowlist check ---
        # Skipped when BREVO_WEBHOOK_IP_RANGES is empty (local / ngrok testing).
        allowed_ranges = getattr(settings, 'BREVO_WEBHOOK_IP_RANGES', None)
        if allowed_ranges is not None:  # None means not configured at all — skip
            client_ip = _get_client_ip(request)
            if not _ip_is_allowed(client_ip, allowed_ranges):
                logger.warning("Brevo webhook: request from disallowed IP %s rejected.", client_ip)
                return HttpResponseForbidden("IP not allowed.")

        # --- Payload size guard ---
        if len(request.body) > 100_000:
            logger.warning("Brevo webhook: payload too large (%s bytes)", len(request.body))
            return HttpResponseBadRequest("Payload too large.")

        # --- Parse body ---
        try:
            payload = json.loads(request.body)
            if len(request.body) > 100_000:
                return HttpResponseBadRequest("Payload too large.")
        except (json.JSONDecodeError, ValueError):
            logger.warning("Brevo webhook: could not parse JSON body.")
            return HttpResponseBadRequest("Invalid JSON.")

        event = payload.get('event')
        # Brevo echoes X-Mailin-Tag as a list under 'tags'
        tags = payload.get('tags') or []
        log_id = tags[0] if tags else None

        if not log_id:
            # No tag means we can't correlate — acknowledge and move on
            logger.info("Brevo webhook: event '%s' received with no tag, ignoring.", event)
            return HttpResponse(status=200)

        new_status = BREVO_EVENT_MAP.get(event)
        if not new_status:
            # Untracked event (e.g. 'opened', 'click') — acknowledge silently
            return HttpResponse(status=200)

        # --- Update EmailLog ---
        try:
            log = EmailLog.objects.get(pk=log_id)
        except (EmailLog.DoesNotExist, ValueError, ValidationError):
            logger.warning("Brevo webhook: tag '%s' could not be resolved to an EmailLog, ignoring.", log_id)
            return HttpResponse(status=200)

        update_fields = ['status']
        log.status = new_status

        if new_status == EmailLog.Status.DELIVERED:
            # Prefer ts_event (seconds, GMT) from the payload — it records the
            # exact moment Brevo confirmed delivery rather than when we processed it.
            ts_event = payload.get('ts_event')
            if ts_event:
                log.delivered_at = datetime.fromtimestamp(int(ts_event), tz=dt_timezone.utc)
            else:
                log.delivered_at = timezone.now()
            update_fields.append('delivered_at')

        # Only genuine human opens set opened_at — proxy opens (Apple MPP, security gateways) are excluded because they fire regardless of whether the person actually read the email and would inflate the metric. Only record it once: first event wins; don't overwrite with later re-opens.
        HUMAN_OPEN_STATUSES = {
            EmailLog.Status.OPENED,
            EmailLog.Status.FIRST_OPENING,
        }
        if new_status in HUMAN_OPEN_STATUSES and not log.opened_at:
            ts_event = payload.get('ts_event')
            if ts_event:
                log.opened_at = datetime.fromtimestamp(int(ts_event), tz=dt_timezone.utc)
            else:
                log.opened_at = timezone.now()
            update_fields.append('opened_at')

        log.save(update_fields=update_fields)
        logger.info("Brevo webhook: EmailLog %s updated to '%s'.", log_id, new_status)
        logger.debug(
            "Brevo webhook: ip=%s event=%s tags=%s",
            _get_client_ip(request),
            payload.get("event"),
            payload.get("tags"),
        )
        return HttpResponse(status=200)
