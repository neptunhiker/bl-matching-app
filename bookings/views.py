# bookings/views.py
import json

from django.http import HttpResponse, JsonResponse
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt

from .models import CalendlyBooking


def extract_answer(questions, possible_labels):
    """
    Findet eine Antwort in questions_and_answers anhand möglicher Labels.
    Beispiel:
    extract_answer(questions, ["First name", "Vorname", "first_name"])
    """
    normalized_labels = [label.strip().lower() for label in possible_labels]

    for item in questions:
        question = (item.get("question") or "").strip().lower()
        if question in normalized_labels:
            return (item.get("answer") or "").strip()

    return ""


def split_full_name(full_name):
    """
    Fallback, falls Calendly nur einen kombinierten Namen liefert.
    """
    full_name = (full_name or "").strip()
    if not full_name:
        return "", ""

    parts = full_name.split(" ", 1)
    first_name = parts[0]
    last_name = parts[1] if len(parts) > 1 else ""
    return first_name, last_name


@csrf_exempt
def calendly_webhook(request):
    if request.method != "POST":
        return JsonResponse({"detail": "Method not allowed"}, status=405)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse({"detail": "Invalid JSON"}, status=400)

    event = payload.get("event")
    data = payload.get("payload", {})
    invitee = data.get("invitee", {})
    scheduled_event = data.get("scheduled_event", {})
    questions = invitee.get("questions_and_answers", [])

    invitee_uri = invitee.get("uri")
    event_uri = scheduled_event.get("uri", "")

    if event in {"invitee.created", "invitee.canceled"} and not invitee_uri:
        return JsonResponse({"detail": "Missing invitee uri"}, status=400)

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

        booking_defaults = {
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
        }

        CalendlyBooking.objects.update_or_create(
            calendly_invitee_uri=invitee_uri,
            defaults=booking_defaults,
        )

        return HttpResponse(status=200)

    if event == "invitee.canceled":
        updated_count = CalendlyBooking.objects.filter(
            calendly_invitee_uri=invitee_uri
        ).update(
            status="canceled",
            raw_payload=payload,
        )

        if updated_count == 0:
            # Falls die Buchung aus irgendeinem Grund noch nicht existiert,
            # legen wir optional einen Minimal-Datensatz an.
            CalendlyBooking.objects.create(
                calendly_invitee_uri=invitee_uri,
                calendly_event_uri=event_uri or f"https://api.calendly.com/scheduled_events/unknown/{invitee_uri.split('/')[-1]}",
                calendly_event_uuid=CalendlyBooking.extract_uuid_from_uri(event_uri),
                invitee_name=(invitee.get("name") or "").strip(),
                invitee_email=(invitee.get("email") or "").strip(),
                status="canceled",
                raw_payload=payload,
            )

        return HttpResponse(status=200)

    return HttpResponse(status=200)