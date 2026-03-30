# bookings/views.py
import json
import logging

from django.http import HttpResponse, JsonResponse
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt

from .models import CalendlyBooking

logger = logging.getLogger(__name__)

logger.info("TEST LOG")


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


@csrf_exempt
def calendly_webhook(request):
    logger.info("Webhook received", extra={
        "method": request.method,
        "path": request.path,
    })

    if request.method != "POST":
        logger.warning("Invalid method for webhook", extra={
            "method": request.method
        })
        return JsonResponse({"detail": "Method not allowed"}, status=405)

    try:
        raw_body = request.body.decode("utf-8")
        payload = json.loads(raw_body)
        
        # remove later - just for debugging
        logger.info("FULL PAYLOAD:\n%s", json.dumps(payload, indent=2))
    except json.JSONDecodeError:
        logger.exception("Invalid JSON received from Calendly")
        return JsonResponse({"detail": "Invalid JSON"}, status=400)

    event = payload.get("event")
    data = payload.get("payload", {})
    invitee = data.get("invitee", {})
    scheduled_event = data.get("scheduled_event", {})

    invitee_uri = invitee.get("uri")
    event_uri = scheduled_event.get("uri", "")

    logger.info("Webhook parsed", extra={
        "event": event,
        "invitee_uri": invitee_uri,
    })

    if event in {"invitee.created", "invitee.canceled"} and not invitee_uri:
        logger.error("Missing invitee_uri", extra={
            "event": event,
        })
        return JsonResponse({"detail": "Missing invitee uri"}, status=400)

    questions = invitee.get("questions_and_answers", [])

    # =========================
    # INVITEE CREATED
    # =========================
    if event == "invitee.created":
        invitee_name = (invitee.get("name") or "").strip()

        first_name = (
            (invitee.get("first_name") or "").strip()
            or extract_answer(questions, ["First name", "Vorname", "first_name"])
        )

        last_name = (
            (invitee.get("last_name") or "").strip()
            or extract_answer(questions, ["Last name", "Nachname", "last_name", "Surname"])
        )

        if not first_name and not last_name and invitee_name:
            first_name, last_name = split_full_name(invitee_name)

        if not invitee_name:
            invitee_name = f"{first_name} {last_name}".strip()

        try:
            booking, created = CalendlyBooking.objects.update_or_create(
                calendly_invitee_uri=invitee_uri,
                defaults={
                    "calendly_event_uri": event_uri,
                    "calendly_event_uuid": CalendlyBooking.extract_uuid_from_uri(event_uri),
                    "invitee_first_name": first_name,
                    "invitee_last_name": last_name,
                    "invitee_name": invitee_name,
                    "invitee_email": (invitee.get("email") or "").strip(),
                    "timezone": (invitee.get("timezone") or "").strip(),
                    "event_name": (scheduled_event.get("name") or "").strip(),
                    "event_type": (scheduled_event.get("event_type") or "").strip(),
                    "start_time": parse_datetime(scheduled_event.get("start_time"))
                    if scheduled_event.get("start_time")
                    else None,
                    "end_time": parse_datetime(scheduled_event.get("end_time"))
                    if scheduled_event.get("end_time")
                    else None,
                    "status": (invitee.get("status") or "active").strip(),
                    "questions_and_answers": questions,
                    "raw_payload": payload,
                },
            )

            logger.info("Booking stored", extra={
                "booking_id": str(booking.id),
                "created": created,
                "email": booking.invitee_email,
                "event": booking.event_name,
            })

        except Exception:
            logger.exception("Error while saving booking")
            return JsonResponse({"detail": "Error saving booking"}, status=500)

        return HttpResponse(status=200)

    # =========================
    # INVITEE CANCELED
    # =========================
    if event == "invitee.canceled":
        try:
            updated_count = CalendlyBooking.objects.filter(
                calendly_invitee_uri=invitee_uri
            ).update(
                status="canceled",
                raw_payload=payload,
            )

            logger.info("Booking canceled", extra={
                "invitee_uri": invitee_uri,
                "updated_count": updated_count,
            })

        except Exception:
            logger.exception("Error while canceling booking")
            return JsonResponse({"detail": "Error updating booking"}, status=500)

        return HttpResponse(status=200)

    # =========================
    # OTHER EVENTS
    # =========================
    logger.info("Unhandled event type", extra={"event": event})

    return HttpResponse(status=200)