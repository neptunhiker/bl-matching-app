import pytest

from bookings.utils import (
    build_booking_defaults,
    build_safe_webhook_summary,
    extract_answer,
    extract_uuid_from_uri,
    split_full_name,
)


# ---------------------------------------------------------------------------
# extract_uuid_from_uri
# ---------------------------------------------------------------------------

def test_extract_uuid_from_uri_returns_last_segment():
    uri = "https://api.calendly.com/scheduled_events/abc-123-def"
    assert extract_uuid_from_uri(uri) == "abc-123-def"

def test_extract_uuid_from_uri_strips_trailing_slash():
    assert extract_uuid_from_uri("https://api.calendly.com/events/xyz/") == "xyz"

def test_extract_uuid_from_uri_empty_returns_empty():
    assert extract_uuid_from_uri("") == ""
    assert extract_uuid_from_uri(None) == ""


# ---------------------------------------------------------------------------
# split_full_name
# ---------------------------------------------------------------------------

def test_split_full_name_first_and_last():
    assert split_full_name("Jane Doe") == ("Jane", "Doe")

def test_split_full_name_compound_last_name():
    assert split_full_name("Jane van der Berg") == ("Jane", "van der Berg")

def test_split_full_name_single_word():
    assert split_full_name("Madonna") == ("Madonna", "")

def test_split_full_name_empty():
    assert split_full_name("") == ("", "")
    assert split_full_name(None) == ("", "")


# ---------------------------------------------------------------------------
# extract_answer
# ---------------------------------------------------------------------------

QUESTIONS = [
    {"question": "Vorname", "answer": "Anna"},
    {"question": "Last name", "answer": "Schmidt"},
    {"question": "City", "answer": "Berlin"},
]

def test_extract_answer_case_insensitive_match():
    assert extract_answer(QUESTIONS, ["vorname"]) == "Anna"

def test_extract_answer_multiple_labels_first_match_wins():
    assert extract_answer(QUESTIONS, ["First name", "Vorname"]) == "Anna"

def test_extract_answer_no_match_returns_empty():
    assert extract_answer(QUESTIONS, ["Email"]) == ""

def test_extract_answer_empty_questions():
    assert extract_answer([], ["Vorname"]) == ""


# ---------------------------------------------------------------------------
# build_booking_defaults
# ---------------------------------------------------------------------------

INVITEE = {
    "uri": "https://api.calendly.com/invitees/inv-1",
    "name": "Anna Schmidt",
    "email": "anna@example.com",
    "timezone": "Europe/Berlin",
    "status": "active",
    "questions_and_answers": [],
}

EVENT = {
    "uri": "https://api.calendly.com/scheduled_events/evt-1",
    "name": "60-min Coaching",
    "event_type": "https://api.calendly.com/event_types/type-1",
    "start_time": "2026-11-01T10:00:00.000000Z",
    "end_time": "2026-11-01T11:00:00.000000Z",
    "status": "active",
}

def test_build_booking_defaults_basic_fields():
    result = build_booking_defaults(INVITEE, EVENT, full_payload={})
    assert result["invitee_email"] == "anna@example.com"
    assert result["timezone"] == "Europe/Berlin"
    assert result["event_name"] == "60-min Coaching"
    assert result["status"] == "active"

def test_build_booking_defaults_parses_start_end_times():
    result = build_booking_defaults(INVITEE, EVENT, full_payload={})
    assert result["start_time"] is not None
    assert result["end_time"] is not None

def test_build_booking_defaults_name_split_from_full_name():
    invitee = {**INVITEE, "first_name": "", "last_name": ""}
    result = build_booking_defaults(invitee, EVENT, full_payload={})
    assert result["invitee_first_name"] == "Anna"
    assert result["invitee_last_name"] == "Schmidt"

def test_build_booking_defaults_name_from_questions_when_missing():
    invitee = {
        **INVITEE,
        "name": "",
        "first_name": "",
        "last_name": "",
        "questions_and_answers": [
            {"question": "Vorname", "answer": "Paul"},
            {"question": "Nachname", "answer": "Weber"},
        ],
    }
    result = build_booking_defaults(invitee, EVENT, full_payload={})
    assert result["invitee_first_name"] == "Paul"
    assert result["invitee_last_name"] == "Weber"

def test_build_booking_defaults_event_uri_extracted():
    result = build_booking_defaults(INVITEE, EVENT, full_payload={})
    assert result["calendly_event_uuid"] == "evt-1"


# ---------------------------------------------------------------------------
# build_safe_webhook_summary
# ---------------------------------------------------------------------------

def test_build_safe_webhook_summary_basic():
    payload = {"event": "invitee.created", "created_at": "2026-01-01T00:00:00Z"}
    result = build_safe_webhook_summary(payload, INVITEE, EVENT)
    assert result["event"] == "invitee.created"
    assert result["event_uuid"] == "evt-1"
    assert result["invitee_uuid"] == "inv-1"
    assert result["question_count"] == 0
    assert result["has_cancellation"] is False

def test_build_safe_webhook_summary_has_cancellation():
    invitee = {**INVITEE, "cancellation": {"canceler_type": "invitee"}}
    result = build_safe_webhook_summary({}, invitee, EVENT)
    assert result["has_cancellation"] is True
    assert result["canceler_type"] == "invitee"
