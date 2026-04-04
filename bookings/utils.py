from django.utils.dateparse import parse_datetime

from .models import CalendlyBooking


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
