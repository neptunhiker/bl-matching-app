# bookings/views.py
import json
import logging

from django.contrib.auth.mixins import UserPassesTestMixin
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView
from django.http import HttpResponse, JsonResponse
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt

from .models import CalendlyBooking

logger = logging.getLogger(__name__)

class StaffRequiredMixin(UserPassesTestMixin):
    """Restricts the view to staff users only."""
    def test_func(self):
        return self.request.user.is_active and self.request.user.is_staff
    
def extract_answer(questions, possible_labels):
    normalized_labels = [label.strip().lower() for label in possible_labels]

    for item in questions:
        question = (item.get("question") or "").strip().lower()
        if question in normalized_labels:
            return (item.get("answer") or "").strip()
    return ""


def split_full_name(full_name):
    full_name = (full_name or "").strip()
    if not full_name:
        return "", ""

    parts = full_name.split(" ", 1)
    first_name = parts[0]
    last_name = parts[1] if len(parts) > 1 else ""
    return first_name, last_name


def extract_uuid_from_uri(uri: str) -> str:
    if not uri:
        return ""
    return uri.rstrip("/").split("/")[-1]


def build_booking_defaults(invitee_data, scheduled_event, full_payload):
    questions = invitee_data.get("questions_and_answers", [])

    invitee_name = (invitee_data.get("name") or "").strip()

    first_name = (
        (invitee_data.get("first_name") or "").strip()
        or extract_answer(questions, ["First name", "Vorname", "first_name"])
    )

    last_name = (
        (invitee_data.get("last_name") or "").strip()
        or extract_answer(questions, ["Last name", "Nachname", "last_name", "Surname"])
    )

    if not first_name and not last_name and invitee_name:
        first_name, last_name = split_full_name(invitee_name)

    if not invitee_name:
        invitee_name = f"{first_name} {last_name}".strip()

    event_uri = (scheduled_event.get("uri") or invitee_data.get("event") or "").strip()

    return {
        "calendly_event_uri": event_uri,
        "calendly_event_uuid": CalendlyBooking.extract_uuid_from_uri(event_uri),
        "calendly_invitee_uri": (invitee_data.get("uri") or "").strip(),
        "invitee_first_name": first_name,
        "invitee_last_name": last_name,
        "invitee_name": invitee_name,
        "invitee_email": (invitee_data.get("email") or "").strip(),
        "timezone": (invitee_data.get("timezone") or "").strip(),
        "event_name": (scheduled_event.get("name") or "").strip(),
        "event_type": (scheduled_event.get("event_type") or "").strip(),
        "start_time": parse_datetime(scheduled_event.get("start_time"))
        if scheduled_event.get("start_time")
        else None,
        "end_time": parse_datetime(scheduled_event.get("end_time"))
        if scheduled_event.get("end_time")
        else None,
        "status": (invitee_data.get("status") or scheduled_event.get("status") or "active").strip(),
        "questions_and_answers": questions,
        "raw_payload": full_payload,
    }


def build_safe_webhook_summary(payload, invitee_data, scheduled_event):
    invitee_uri = (invitee_data.get("uri") or "").strip()
    event_uri = (scheduled_event.get("uri") or invitee_data.get("event") or "").strip()

    questions = invitee_data.get("questions_and_answers", []) or []
    cancellation = invitee_data.get("cancellation") or {}
    scheduled_cancellation = scheduled_event.get("cancellation") or {}

    return {
        "event": payload.get("event"),
        "payload_created_at": payload.get("created_at"),
        "invitee_created_at": invitee_data.get("created_at"),
        "invitee_updated_at": invitee_data.get("updated_at"),
        "scheduled_event_created_at": scheduled_event.get("created_at"),
        "scheduled_event_updated_at": scheduled_event.get("updated_at"),
        "invitee_uuid": extract_uuid_from_uri(invitee_uri),
        "event_uuid": extract_uuid_from_uri(event_uri),
        "status": invitee_data.get("status") or scheduled_event.get("status"),
        "scheduled_event_status": scheduled_event.get("status"),
        "event_name": scheduled_event.get("name"),
        "event_type_uuid": extract_uuid_from_uri(scheduled_event.get("event_type") or ""),
        "start_time": scheduled_event.get("start_time"),
        "end_time": scheduled_event.get("end_time"),
        "timezone": invitee_data.get("timezone"),
        "question_count": len(questions),
        "rescheduled": invitee_data.get("rescheduled"),
        "has_cancellation": bool(cancellation or scheduled_cancellation),
        "canceler_type": cancellation.get("canceler_type") or scheduled_cancellation.get("canceler_type"),
        "location_type": (scheduled_event.get("location") or {}).get("type"),
        "tracking_present": bool(invitee_data.get("tracking")),
    }


@csrf_exempt
def calendly_webhook(request):
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
    model = CalendlyBooking
    template_name = "bookings/calendly_bookings_list.html"
    context_object_name = "bookings"

    def get_queryset(self):
        return (
            CalendlyBooking.objects
            .order_by("-start_time", "-created_at")
        )