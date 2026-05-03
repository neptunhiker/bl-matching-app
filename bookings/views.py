# bookings/views.py
import hashlib
import hmac
import json
import logging
import time

from django.conf import settings
from django.contrib.auth.mixins import UserPassesTestMixin
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, DetailView
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .models import CalendlyBooking
from .utils import (
    build_booking_defaults,
    build_safe_webhook_summary,
    extract_uuid_from_uri,
)

logger = logging.getLogger(__name__)

# Maximum age (seconds) we accept for a webhook timestamp — prevents replays.
_WEBHOOK_MAX_AGE_SECONDS = 300


def _verify_calendly_signature(header: str, raw_body: bytes, signing_key: str) -> bool:
    """
    Verify the Calendly-Webhook-Signature header.

    Header format:  t=<unix_timestamp>,v1=<hex_hmac>
    Signed message: f"{timestamp}.{raw_body_as_str}"
    Algorithm:      HMAC-SHA256 with the account signing key.
    """
    try:
        parts = dict(part.split("=", 1) for part in header.split(","))
        timestamp = parts["t"]
        expected_sig = parts["v1"]
    except (KeyError, ValueError):
        logger.error(
            "[CALENDLY-SIG] Could not parse Calendly-Webhook-Signature header — "
            "expected format 't=<ts>,v1=<hex>' but got: %.120s",
            header,
        )
        return False

    # Reject stale requests (replay attack prevention).
    try:
        now = int(time.time())
        age = now - int(timestamp)
        logger.debug(
            "[CALENDLY-SIG] Timestamp check: header_ts=%s server_ts=%s age_seconds=%s max=%s",
            timestamp, now, age, _WEBHOOK_MAX_AGE_SECONDS,
        )
        if not (0 <= age <= _WEBHOOK_MAX_AGE_SECONDS):
            logger.warning(
                "[CALENDLY-SIG] Timestamp out of window: age=%s seconds (max %s). "
                "Check that server clock is correct.",
                age, _WEBHOOK_MAX_AGE_SECONDS,
            )
            return False
    except ValueError:
        logger.error("[CALENDLY-SIG] Non-integer timestamp in header: %s", timestamp)
        return False

    message = f"{timestamp}.{raw_body.decode('utf-8')}".encode("utf-8")
    computed = hmac.new(
        signing_key.encode("utf-8"),
        msg=message,
        digestmod=hashlib.sha256,
    ).hexdigest()

    match = hmac.compare_digest(computed, expected_sig)
    if not match:
        logger.warning(
            "[CALENDLY-SIG] HMAC mismatch. "
            "computed=%.16s… expected=%.16s… "
            "(signing key length=%d chars)",
            computed, expected_sig, len(signing_key),
        )
    else:
        logger.debug("[CALENDLY-SIG] Signature verified OK.")
    return match


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

    Every request is authenticated via HMAC-SHA256: Calendly signs the payload
    with the account signing key and includes the signature in the
    ``Calendly-Webhook-Signature`` header (format: ``t=<ts>,v1=<hexdigest>``).
    Requests with a missing, invalid, or stale signature are rejected with 403.
    Set ``CALENDLY_SIGNING_KEY`` in .env (copy from Calendly webhook settings).
    """
    logger.info("========== NEW WEBHOOK ==========")
    logger.info(
        "[CALENDLY] Incoming request: method=%s path=%s content_type=%s content_length=%s",
        request.method,
        request.path,
        request.content_type,
        request.META.get("CONTENT_LENGTH", "?"),
    )

    if request.method != "POST":
        logger.warning("[CALENDLY] Rejected: method=%s (expected POST)", request.method)
        return JsonResponse({"detail": "Method not allowed"}, status=405)

    # --- Signature verification ---
    signing_key = getattr(settings, "CALENDLY_SIGNING_KEY", "")
    if not signing_key:
        logger.error(
            "[CALENDLY] CALENDLY_SIGNING_KEY is empty — check your .env file. Rejecting request."
        )
        return HttpResponseForbidden("Webhook signing key not configured.")

    logger.debug("[CALENDLY] Signing key loaded (length=%d chars).", len(signing_key))

    sig_header = request.META.get("HTTP_CALENDLY_WEBHOOK_SIGNATURE", "")
    if not sig_header:
        logger.warning(
            "[CALENDLY] Missing Calendly-Webhook-Signature header. "
            "Request headers present: %s",
            [k for k in request.META if k.startswith("HTTP_")],
        )
        return HttpResponseForbidden("Missing signature.")

    logger.debug("[CALENDLY] Signature header received: %.80s", sig_header)

    raw_body = request.body
    logger.debug("[CALENDLY] Raw body length: %d bytes.", len(raw_body))

    if not _verify_calendly_signature(sig_header, raw_body, signing_key):
        logger.warning("[CALENDLY] Signature verification failed — returning 403.")
        return HttpResponseForbidden("Invalid signature.")

    logger.info("[CALENDLY] Signature verified successfully.")

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError:
        logger.exception("Invalid JSON received from Calendly")
        return JsonResponse({"detail": "Invalid JSON"}, status=400)

    event = payload.get("event")
    invitee_data = payload.get("payload", {}) or {}
    scheduled_event = invitee_data.get("scheduled_event", {}) or {}

    invitee_uri = (invitee_data.get("uri") or "").strip()
    event_uri = (scheduled_event.get("uri") or invitee_data.get("event") or "").strip()

    logger.info("[CALENDLY] Event type: %s", event)

    # --- Event-type discrimination ---
    # Route by scheduled_event.name — more reliable than UTM which can be null
    # on direct Calendly bookings (e.g. staff test bookings).
    _scheduled_event_name = (scheduled_event.get("name") or "").strip()
    _is_clarification_call = _scheduled_event_name == "Check In"

    # --- Environment-based event filtering ---
    # Test detection differs by event type:
    #   - Check In: prefix the free-text description answer with "test"
    #   - Intake (Erstgespräch): prefix the answer to "Hier kannst du uns dein Anliegen mitteilen:" with "test"
    _qa_list = invitee_data.get("questions_and_answers") or []
    if _is_clarification_call:
        # Real question label has a trailing space, so match via startswith.
        _test_indicator_answer = next(
            (
                (qa.get("answer") or "")
                for qa in _qa_list
                if (qa.get("question") or "").strip().lower().startswith("bitte beschreibe")
            ),
            "",
        )
    else:
        _TEST_QUESTION = "Hier kannst du uns dein Anliegen mitteilen:"
        _test_indicator_answer = next(
            (
                (qa.get("answer") or "")
                for qa in _qa_list
                if (qa.get("question") or "").strip() == _TEST_QUESTION
            ),
            "",
        )
    is_test_event = _test_indicator_answer.strip()[:4].lower() == "test"
    environment = getattr(settings, "ENVIRONMENT", "development")

    if environment == "production" and is_test_event:
        logger.info(
            "[CALENDLY] Ignoring test event on production (answer prefix=%r). Returning 200.",
            _test_indicator_answer[:10],
        )
        return JsonResponse({"detail": "Test event ignored on production."})

    if environment == "staging" and not is_test_event and event in {"invitee.created", "invitee.canceled"}:
        logger.info(
            "[CALENDLY] Ignoring non-test event on staging (answer prefix=%r). Returning 200.",
            _test_indicator_answer[:10],
        )
        return JsonResponse({"detail": "Only test events are processed on staging."})

    safe_summary = build_safe_webhook_summary(
        payload=payload,
        invitee_data=invitee_data,
        scheduled_event=scheduled_event,
    )

    logger.info("[CALENDLY] Parsed payload summary: %s", safe_summary)

    if event in {"invitee.created", "invitee.canceled"} and not invitee_uri:
        logger.error(
            "Missing invitee_uri for event=%s event_uuid=%s",
            event,
            extract_uuid_from_uri(event_uri),
        )
        return JsonResponse({"detail": "Missing invitee uri"}, status=400)

    # --- Clarification call lookup keys ---
    # Primary: UTM campaign contains the matching attempt ID (set when participant clicks email link).
    # Fallback: invitee email (used when UTM is absent, e.g. staff test booking directly in Calendly).
    _tracking = (invitee_data.get("tracking") or {})
    _utm_campaign = (_tracking.get("utm_campaign") or "").strip()
    _clarification_matching_id = _utm_campaign.removeprefix("matching-") if _utm_campaign.startswith("matching-") else None
    _clarification_invitee_email = (invitee_data.get("email") or "").strip()

    if event == "invitee.created":
        if _is_clarification_call:
            from matching.services import record_clarification_call_booked
            try:
                record_clarification_call_booked(
                    matching_attempt_id=_clarification_matching_id,
                    invitee_email=_clarification_invitee_email,
                    invitee_data=invitee_data,
                    scheduled_event=scheduled_event,
                    raw_payload=payload,
                )
            except Exception:
                logger.exception(
                    "Error recording clarification call booking — matching_id=%s email=%s",
                    _clarification_matching_id, _clarification_invitee_email,
                )
                return JsonResponse({"detail": "Error recording clarification call booking"}, status=500)
            return HttpResponse(status=200)

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
        if _is_clarification_call:
            from matching.services import record_clarification_call_canceled
            try:
                record_clarification_call_canceled(
                    matching_attempt_id=_clarification_matching_id,
                    invitee_email=_clarification_invitee_email,
                    invitee_data=invitee_data,
                    raw_payload=payload,
                )
            except Exception:
                logger.exception(
                    "Error recording clarification call cancellation — matching_id=%s email=%s",
                    _clarification_matching_id, _clarification_invitee_email,
                )
                return JsonResponse({"detail": "Error recording clarification call cancellation"}, status=500)
            return HttpResponse(status=200)

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


class CalendlyBookingDetailView(LoginRequiredMixin, StaffRequiredMixin, DetailView):
    """Staff-only detail view of a single Calendly booking."""

    model = CalendlyBooking
    template_name = "bookings/calendly_booking_detail.html"
    context_object_name = "booking"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        from profiles.models import Participant

        booking_email_normalized = (self.object.invitee_email or "").strip().lower()
        existing_participant = None
        show_create_participant_button = False

        if booking_email_normalized:
            existing_participant = (
                Participant.objects
                .filter(email__iexact=booking_email_normalized)
                .order_by("created_at", "id")
                .first()
            )
            show_create_participant_button = existing_participant is None

        context.update(
            {
                "booking_email_normalized": booking_email_normalized,
                "existing_participant": existing_participant,
                "show_create_participant_button": show_create_participant_button,
            }
        )
        return context