import json
import logging

from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings

from .models import EmailLog

logger = logging.getLogger(__name__)

# Map Brevo event names → EmailLog.Status values
BREVO_EVENT_MAP = {
    'delivered': EmailLog.Status.DELIVERED,
    'hardBounce': EmailLog.Status.BOUNCED,
    'softBounce': EmailLog.Status.BOUNCED,
    'spam': EmailLog.Status.SPAM,
    'blocked': EmailLog.Status.BLOCKED,
}


@method_decorator(csrf_exempt, name='dispatch')
class BrevoWebhookView(View):
    """
    Receives transactional email event webhooks from Brevo.

    Register this URL in Brevo under:
      Transactional → Settings → Webhook → Notifications
    Events to subscribe: delivered, hardBounce, softBounce, spam, blocked

    Security: pass a shared secret as a query parameter, e.g.
      https://yourdomain.de/emails/webhooks/brevo/?secret=<BREVO_WEBHOOK_SECRET>
    Set BREVO_WEBHOOK_SECRET in your .env file.
    """

    def post(self, request, *args, **kwargs):
        # --- Optional shared-secret check ---
        expected_secret = getattr(settings, 'BREVO_WEBHOOK_SECRET', None)
        if expected_secret:
            provided = request.GET.get('secret', '')
            if provided != expected_secret:
                logger.warning("Brevo webhook: invalid secret received.")
                return HttpResponseForbidden("Invalid secret.")

        # --- Parse body ---
        try:
            payload = json.loads(request.body)
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
        except EmailLog.DoesNotExist:
            logger.warning("Brevo webhook: EmailLog %s not found for event '%s'.", log_id, event)
            # Still return 200 so Brevo doesn't keep retrying
            return HttpResponse(status=200)

        update_fields = ['status']
        log.status = new_status

        if new_status == EmailLog.Status.DELIVERED:
            log.delivered_at = timezone.now()
            update_fields.append('delivered_at')

        log.save(update_fields=update_fields)
        logger.info("Brevo webhook: EmailLog %s updated to '%s'.", log_id, new_status)
        return HttpResponse(status=200)
