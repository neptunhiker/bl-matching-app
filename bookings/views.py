# bookings/views.py
import json
import logging

from django.contrib.auth.mixins import UserPassesTestMixin
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .models import CalendlyBooking
from .utils import (
    build_booking_defaults,
    build_safe_webhook_summary,
    extract_uuid_from_uri,
)

logger = logging.getLogger(__name__)


class StaffRequiredMixin(UserPassesTestMixin):
    """Restricts the view to staff users only."""
    def test_func(self):
        return (self.request.user.is_active and self.request.user.is_staff) or self.request.user.is_superuser


@csrf_exempt
def calendly_webhook(request):
    """
    Receives Calendly webhook events and persists them as CalendlyBooking records.

    Handles:
      - invitee.created  → upsert a new booking
      - invitee.canceled → upsert with canceled status
      - anything else    → acknowledge silently (200)

    No authentication is applied; Calendly does not support shared-secret
    verification on its webhook delivery.
    """
    logger.info("========== NEW WEBHOOK ==========")
    logger.info(
        "Webhook received",
        extra={
            "method": request.method,
            "path": request.path,
        },
    )

    if request.method != "POST":
        logger.warning("Invalid method for webhook", extra={"method": request.method})
        return JsonResponse({"detail": "Method not allowed"}, status=405)

    try:
        raw_body = request.body.decode("utf-8")
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        logger.exception("Invalid JSON received from Calendly")
        return JsonResponse({"detail": "Invalid JSON"}, status=400)

    event = payload.get("event")
    invitee_data = payload.get("payload", {}) or {}
    scheduled_event = invitee_data.get("scheduled_event", {}) or {}

    invitee_uri = (invitee_data.get("uri") or "").strip()
    event_uri = (scheduled_event.get("uri") or invitee_data.get("event") or "").strip()

    safe_summary = build_safe_webhook_summary(
        payload=payload,
        invitee_data=invitee_data,
        scheduled_event=scheduled_event,
    )

    logger.info("Webhook parsed summary: %s", safe_summary)

    if event in {"invitee.created", "invitee.canceled"} and not invitee_uri:
        logger.error(
            "Missing invitee_uri for event=%s event_uuid=%s",
            event,
            extract_uuid_from_uri(event_uri),
        )
        return JsonResponse({"detail": "Missing invitee uri"}, status=400)

    if event == "invitee.created":
        # New booking — create or update by invitee URI (idempotent on re-delivery).
        try:
            booking, created = CalendlyBooking.objects.update_or_create(
                calendly_invitee_uri=invitee_uri,
                defaults=build_booking_defaults(
                    invitee_data=invitee_data,
                    scheduled_event=scheduled_event,
                    full_payload=payload,
                ),
            )

            logger.info(
                "Booking stored successfully: booking_id=%s created=%s invitee_uuid=%s event_uuid=%s start_time=%s status=%s",
                booking.id,
                created,
                extract_uuid_from_uri(invitee_uri),
                booking.calendly_event_uuid,
                booking.start_time,
                booking.status,
            )
        except Exception:
            logger.exception(
                "Error while saving booking for event=%s invitee_uuid=%s event_uuid=%s",
                event,
                extract_uuid_from_uri(invitee_uri),
                extract_uuid_from_uri(event_uri),
            )
            return JsonResponse({"detail": "Error saving booking"}, status=500)

        return HttpResponse(status=200)

    if event == "invitee.canceled":
        # Cancellation — upsert so the status and cancellation fields are persisted
        # even if the booking record was not created by an earlier invitee.created event.
        try:
            booking, created = CalendlyBooking.objects.update_or_create(
                calendly_invitee_uri=invitee_uri,
                defaults=build_booking_defaults(
                    invitee_data=invitee_data,
                    scheduled_event=scheduled_event,
                    full_payload=payload,
                ),
            )

            logger.info(
                "Booking canceled successfully: booking_id=%s created=%s invitee_uuid=%s event_uuid=%s start_time=%s status=%s",
                booking.id,
                created,
                extract_uuid_from_uri(invitee_uri),
                booking.calendly_event_uuid,
                booking.start_time,
                booking.status,
            )
        except Exception:
            logger.exception(
                "Error while updating canceled booking for event=%s invitee_uuid=%s event_uuid=%s",
                event,
                extract_uuid_from_uri(invitee_uri),
                extract_uuid_from_uri(event_uri),
            )
            return JsonResponse({"detail": "Error updating booking"}, status=500)

        return HttpResponse(status=200)

    logger.info(
        "Unhandled event type: event=%s invitee_uuid=%s event_uuid=%s",
        event,
        extract_uuid_from_uri(invitee_uri),
        extract_uuid_from_uri(event_uri),
    )
    return HttpResponse(status=200)


class CalendlyBookingsListView(LoginRequiredMixin, StaffRequiredMixin, ListView):
    """Staff-only list of all Calendly bookings, ordered by most recent first."""

    model = CalendlyBooking
    template_name = "bookings/calendly_bookings_list.html"
    context_object_name = "bookings"

    def get_queryset(self):
        return (
            CalendlyBooking.objects
            .order_by("-start_time", "-created_at")
        )