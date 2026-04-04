from unittest.mock import MagicMock, patch

import pytest
from slack_sdk.errors import SlackApiError

from slack.models import SlackLog
from slack.services import (
    create_slack_log,
    _blocks_to_text,
    _open_dm_channel,
    send_first_coach_request_slack,
    send_reminder_coach_request_slack,
    send_intro_call_request_slack,
    send_coaching_starting_info_slack,
    send_escalation_info_slack,
    send_all_rtcs_declined_info_slack,
    send_clarification_need_info_to_coach_slack,
)


def _make_slack_error(code="invalid_auth"):
    return SlackApiError(message=code, response={"ok": False, "error": code})


# ── 1. create_slack_log ───────────────────────────────────────────────────────

@pytest.mark.django_db
class TestCreateSlackLog:

    def test_create_slack_log_rtc_only(self, plain_user, rtc):
        log = create_slack_log(
            to=plain_user,
            subject="Test",
            message="Hello",
            request_to_coach=rtc,
        )
        assert SlackLog.objects.count() == 1
        assert log.request_to_coach == rtc
        assert log.matching_attempt is None
        assert log.status == SlackLog.Status.SENT

    def test_create_slack_log_ma_only(self, plain_user, matching_attempt):
        log = create_slack_log(
            to=plain_user,
            subject="Test",
            message="Hello",
            matching_attempt=matching_attempt,
        )
        assert SlackLog.objects.count() == 1
        assert log.matching_attempt == matching_attempt
        assert log.request_to_coach is None

    def test_create_slack_log_both_fks_raises(self, plain_user, rtc, matching_attempt):
        with pytest.raises(ValueError):
            create_slack_log(
                to=plain_user,
                subject="Test",
                message="Hello",
                request_to_coach=rtc,
                matching_attempt=matching_attempt,
            )
        assert SlackLog.objects.count() == 0

    def test_create_slack_log_neither_fk_raises(self, plain_user):
        with pytest.raises(ValueError):
            create_slack_log(
                to=plain_user,
                subject="Test",
                message="Hello",
            )
        assert SlackLog.objects.count() == 0

    def test_create_slack_log_status_failed(self, plain_user, rtc):
        log = create_slack_log(
            to=plain_user,
            subject="Test",
            message="Hello",
            request_to_coach=rtc,
            status=SlackLog.Status.FAILED,
            error_message="boom",
        )
        assert log.status == SlackLog.Status.FAILED
        assert log.error_message == "boom"

    def test_create_slack_log_returns_instance(self, plain_user, rtc):
        log = create_slack_log(
            to=plain_user,
            subject="Test",
            message="Hello",
            request_to_coach=rtc,
        )
        assert isinstance(log, SlackLog)
        assert log.pk is not None


# ── 2. _blocks_to_text ────────────────────────────────────────────────────────

class TestBlocksToText:

    def test_blocks_to_text_section_blocks(self):
        blocks = [
            {"type": "section", "text": {"type": "mrkdwn", "text": "Hello"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": "World"}},
        ]
        assert _blocks_to_text(blocks) == "Hello\nWorld"

    def test_blocks_to_text_context_blocks(self):
        blocks = [
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": "Note one"},
                    {"type": "mrkdwn", "text": "Note two"},
                ],
            }
        ]
        result = _blocks_to_text(blocks)
        assert "Note one" in result
        assert "Note two" in result

    def test_blocks_to_text_mixed_blocks(self):
        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": "Header"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": "Section text"}},
            {
                "type": "actions",
                "elements": [{"type": "button", "text": {"type": "plain_text", "text": "Click"}}],
            },
            {"type": "context", "elements": [{"type": "mrkdwn", "text": "Context text"}]},
        ]
        result = _blocks_to_text(blocks)
        assert "Header" in result        # header has text.text → included
        assert "Section text" in result
        assert "Click" not in result     # actions elements are not extracted
        assert "Context text" in result

    def test_blocks_to_text_empty_list(self):
        assert _blocks_to_text([]) == ""

    def test_blocks_to_text_actions_block_skipped(self):
        blocks = [
            {
                "type": "actions",
                "elements": [{"type": "button", "text": {"type": "plain_text", "text": "OK"}}],
            }
        ]
        assert _blocks_to_text(blocks) == ""


# ── 3. _open_dm_channel ───────────────────────────────────────────────────────

class TestOpenDmChannel:

    def test_open_dm_channel_returns_channel_id(self):
        client = MagicMock()
        client.conversations_open.return_value = {"channel": {"id": "C99"}}
        assert _open_dm_channel(client, "U123") == "C99"

    def test_open_dm_channel_calls_conversations_open(self):
        client = MagicMock()
        client.conversations_open.return_value = {"channel": {"id": "C99"}}
        _open_dm_channel(client, "U123")
        client.conversations_open.assert_called_once_with(users=["U123"])


# ── 4. send_first_coach_request_slack ─────────────────────────────────────────

_FIRST_PATCHES = (
    "slack.services.WebClient",
    "slack.services._get_locked_request_to_coach",
    "slack.services.generate_accept_and_decline_token",
)


@pytest.mark.django_db
class TestSendFirstCoachRequestSlack:

    def test_send_first_happy_path(self, rtc_with_slack, mock_slack_client):
        with patch(_FIRST_PATCHES[0], return_value=mock_slack_client), \
             patch(_FIRST_PATCHES[1], return_value=rtc_with_slack), \
             patch(_FIRST_PATCHES[2], return_value=("http://a", "http://d")):
            send_first_coach_request_slack(rtc_with_slack)

        mock_slack_client.chat_postMessage.assert_called_once()
        log = SlackLog.objects.get()
        assert log.status == SlackLog.Status.SENT
        assert log.request_to_coach == rtc_with_slack
        assert log.sent_by == SlackLog.SentBy.SYSTEM
        assert log.subject != ""
        assert log.message != ""

    def test_send_first_postmessage_called_with_subject(self, rtc_with_slack, mock_slack_client):
        first_name = rtc_with_slack.matching_attempt.participant.first_name
        expected_subject = f"Matching-Anfrage für {first_name}"

        with patch(_FIRST_PATCHES[0], return_value=mock_slack_client), \
             patch(_FIRST_PATCHES[1], return_value=rtc_with_slack), \
             patch(_FIRST_PATCHES[2], return_value=("http://a", "http://d")):
            send_first_coach_request_slack(rtc_with_slack)

        _, kwargs = mock_slack_client.chat_postMessage.call_args
        assert kwargs["channel"] == "C12345"
        assert kwargs["text"] == expected_subject

    def test_send_first_no_slack_id_raises(self, rtc_no_slack, mock_slack_client):
        with patch(_FIRST_PATCHES[0], return_value=mock_slack_client), \
             patch(_FIRST_PATCHES[1]) as mock_lock:
            with pytest.raises(ValueError):
                send_first_coach_request_slack(rtc_no_slack)

        mock_lock.assert_not_called()
        mock_slack_client.conversations_open.assert_not_called()
        assert SlackLog.objects.count() == 0

    def test_send_first_slack_api_error(self, rtc_with_slack, mock_slack_client):
        mock_slack_client.conversations_open.side_effect = _make_slack_error()

        with patch(_FIRST_PATCHES[0], return_value=mock_slack_client), \
             patch(_FIRST_PATCHES[1], return_value=rtc_with_slack), \
             patch(_FIRST_PATCHES[2], return_value=("http://a", "http://d")):
            send_first_coach_request_slack(rtc_with_slack)

        log = SlackLog.objects.get()
        assert log.status == SlackLog.Status.FAILED
        assert log.error_message != ""

    def test_send_first_generic_exception(self, rtc_with_slack, mock_slack_client):
        mock_slack_client.chat_postMessage.side_effect = RuntimeError("connection lost")

        with patch(_FIRST_PATCHES[0], return_value=mock_slack_client), \
             patch(_FIRST_PATCHES[1], return_value=rtc_with_slack), \
             patch(_FIRST_PATCHES[2], return_value=("http://a", "http://d")):
            send_first_coach_request_slack(rtc_with_slack)

        log = SlackLog.objects.get()
        assert log.status == SlackLog.Status.FAILED
        assert "connection lost" in log.error_message

    def test_send_first_acquires_lock_before_api_call(self, rtc_with_slack, mock_slack_client):
        call_order = []

        def lock_side_effect(rtc):
            call_order.append("lock")
            return rtc

        def open_side_effect(users):
            call_order.append("open")
            return {"channel": {"id": "C12345"}}

        mock_slack_client.conversations_open.side_effect = open_side_effect

        with patch(_FIRST_PATCHES[0], return_value=mock_slack_client), \
             patch(_FIRST_PATCHES[1], side_effect=lock_side_effect), \
             patch(_FIRST_PATCHES[2], return_value=("http://a", "http://d")):
            send_first_coach_request_slack(rtc_with_slack)

        assert call_order.index("lock") < call_order.index("open")


# ── 5. send_reminder_coach_request_slack ──────────────────────────────────────

_REMINDER_PATCHES = (
    "slack.services.WebClient",
    "slack.services._get_locked_request_to_coach",
    "slack.services.generate_accept_and_decline_token",
)


@pytest.mark.django_db
class TestSendReminderCoachRequestSlack:

    def test_send_reminder_happy_path(self, rtc_with_slack, mock_slack_client):
        with patch(_REMINDER_PATCHES[0], return_value=mock_slack_client), \
             patch(_REMINDER_PATCHES[1], return_value=rtc_with_slack), \
             patch(_REMINDER_PATCHES[2], return_value=("http://a", "http://d")):
            send_reminder_coach_request_slack(rtc_with_slack)

        mock_slack_client.chat_postMessage.assert_called_once()
        log = SlackLog.objects.get()
        assert log.status == SlackLog.Status.SENT
        assert log.request_to_coach == rtc_with_slack
        assert log.sent_by == SlackLog.SentBy.SYSTEM

    def test_send_reminder_no_slack_id_raises(self, rtc_no_slack, mock_slack_client):
        # In send_reminder, lock is acquired BEFORE the slack_user_id check.
        # The mock returns the same no-slack RTC; check fires after lock → ValueError.
        with patch(_REMINDER_PATCHES[0], return_value=mock_slack_client), \
             patch(_REMINDER_PATCHES[1], return_value=rtc_no_slack):
            with pytest.raises(ValueError):
                send_reminder_coach_request_slack(rtc_no_slack)

        mock_slack_client.conversations_open.assert_not_called()
        assert SlackLog.objects.count() == 0

    def test_send_reminder_slack_api_error(self, rtc_with_slack, mock_slack_client):
        mock_slack_client.conversations_open.side_effect = _make_slack_error()

        with patch(_REMINDER_PATCHES[0], return_value=mock_slack_client), \
             patch(_REMINDER_PATCHES[1], return_value=rtc_with_slack), \
             patch(_REMINDER_PATCHES[2], return_value=("http://a", "http://d")):
            send_reminder_coach_request_slack(rtc_with_slack)

        log = SlackLog.objects.get()
        assert log.status == SlackLog.Status.FAILED
        assert log.error_message != ""

    def test_send_reminder_generic_exception(self, rtc_with_slack, mock_slack_client):
        mock_slack_client.chat_postMessage.side_effect = RuntimeError("timeout")

        with patch(_REMINDER_PATCHES[0], return_value=mock_slack_client), \
             patch(_REMINDER_PATCHES[1], return_value=rtc_with_slack), \
             patch(_REMINDER_PATCHES[2], return_value=("http://a", "http://d")):
            send_reminder_coach_request_slack(rtc_with_slack)

        log = SlackLog.objects.get()
        assert log.status == SlackLog.Status.FAILED
        assert "timeout" in log.error_message

    def test_send_reminder_lock_acquired_before_api_call(self, rtc_with_slack, mock_slack_client):
        call_order = []

        def lock_side_effect(rtc):
            call_order.append("lock")
            return rtc

        def open_side_effect(users):
            call_order.append("open")
            return {"channel": {"id": "C12345"}}

        mock_slack_client.conversations_open.side_effect = open_side_effect

        with patch(_REMINDER_PATCHES[0], return_value=mock_slack_client), \
             patch(_REMINDER_PATCHES[1], side_effect=lock_side_effect), \
             patch(_REMINDER_PATCHES[2], return_value=("http://a", "http://d")):
            send_reminder_coach_request_slack(rtc_with_slack)

        assert call_order.index("lock") < call_order.index("open")


# ── 6. send_intro_call_request_slack ──────────────────────────────────────────

_INTRO_CALL_PATCHES = (
    "slack.services.WebClient",
    "slack.services.generate_intro_call_feedback_url",
)
_FEEDBACK_URL = "https://example.com/feedback"


@pytest.mark.django_db
class TestSendIntroCallRequestSlack:

    def test_send_intro_call_happy_path(self, matching_attempt_with_coach, mock_slack_client):
        with patch(_INTRO_CALL_PATCHES[0], return_value=mock_slack_client), \
             patch(_INTRO_CALL_PATCHES[1], return_value=_FEEDBACK_URL):
            send_intro_call_request_slack(matching_attempt_with_coach)

        mock_slack_client.chat_postMessage.assert_called_once()
        log = SlackLog.objects.get()
        assert log.status == SlackLog.Status.SENT
        assert log.matching_attempt == matching_attempt_with_coach
        assert log.sent_by == SlackLog.SentBy.SYSTEM
        assert log.subject != ""
        assert log.message != ""

    def test_send_intro_call_no_slack_id_raises(self, matching_attempt_no_coach_slack, mock_slack_client):
        with patch(_INTRO_CALL_PATCHES[0], return_value=mock_slack_client), \
             patch(_INTRO_CALL_PATCHES[1], return_value=_FEEDBACK_URL):
            with pytest.raises(ValueError):
                send_intro_call_request_slack(matching_attempt_no_coach_slack)

        mock_slack_client.conversations_open.assert_not_called()
        assert SlackLog.objects.count() == 0

    def test_send_intro_call_slack_api_error(self, matching_attempt_with_coach, mock_slack_client):
        mock_slack_client.conversations_open.side_effect = _make_slack_error()

        with patch(_INTRO_CALL_PATCHES[0], return_value=mock_slack_client), \
             patch(_INTRO_CALL_PATCHES[1], return_value=_FEEDBACK_URL):
            send_intro_call_request_slack(matching_attempt_with_coach)

        log = SlackLog.objects.get()
        assert log.status == SlackLog.Status.FAILED
        assert log.error_message != ""

    def test_send_intro_call_generic_exception(self, matching_attempt_with_coach, mock_slack_client):
        mock_slack_client.chat_postMessage.side_effect = RuntimeError("boom")

        with patch(_INTRO_CALL_PATCHES[0], return_value=mock_slack_client), \
             patch(_INTRO_CALL_PATCHES[1], return_value=_FEEDBACK_URL):
            send_intro_call_request_slack(matching_attempt_with_coach)

        log = SlackLog.objects.get()
        assert log.status == SlackLog.Status.FAILED
        assert "boom" in log.error_message

    def test_send_intro_call_feedback_url_in_blocks(self, matching_attempt_with_coach, mock_slack_client):
        with patch(_INTRO_CALL_PATCHES[0], return_value=mock_slack_client), \
             patch(_INTRO_CALL_PATCHES[1], return_value=_FEEDBACK_URL):
            send_intro_call_request_slack(matching_attempt_with_coach)

        _, kwargs = mock_slack_client.chat_postMessage.call_args
        blocks_str = str(kwargs["blocks"])
        assert _FEEDBACK_URL in blocks_str


# ── 7. send_coaching_starting_info_slack ──────────────────────────────────────

_COACHING_START_PATCH = "slack.services.WebClient"


@pytest.mark.django_db
class TestSendCoachingStartingInfoSlack:

    def test_send_coaching_start_happy_path(self, matching_attempt_with_coach, mock_slack_client):
        with patch(_COACHING_START_PATCH, return_value=mock_slack_client):
            send_coaching_starting_info_slack(matching_attempt_with_coach)

        mock_slack_client.chat_postMessage.assert_called_once()
        log = SlackLog.objects.get()
        assert log.status == SlackLog.Status.SENT
        assert log.matching_attempt == matching_attempt_with_coach
        assert log.sent_by == SlackLog.SentBy.SYSTEM

    def test_send_coaching_start_no_slack_id_raises(self, matching_attempt_no_coach_slack, mock_slack_client):
        with patch(_COACHING_START_PATCH, return_value=mock_slack_client):
            with pytest.raises(ValueError):
                send_coaching_starting_info_slack(matching_attempt_no_coach_slack)

        mock_slack_client.conversations_open.assert_not_called()
        assert SlackLog.objects.count() == 0

    def test_send_coaching_start_slack_api_error(self, matching_attempt_with_coach, mock_slack_client):
        mock_slack_client.conversations_open.side_effect = _make_slack_error()

        with patch(_COACHING_START_PATCH, return_value=mock_slack_client):
            send_coaching_starting_info_slack(matching_attempt_with_coach)

        log = SlackLog.objects.get()
        assert log.status == SlackLog.Status.FAILED
        assert log.error_message != ""

    def test_send_coaching_start_generic_exception(self, matching_attempt_with_coach, mock_slack_client):
        mock_slack_client.chat_postMessage.side_effect = RuntimeError("timeout")

        with patch(_COACHING_START_PATCH, return_value=mock_slack_client):
            send_coaching_starting_info_slack(matching_attempt_with_coach)

        log = SlackLog.objects.get()
        assert log.status == SlackLog.Status.FAILED
        assert "timeout" in log.error_message


# ── 8. send_escalation_info_slack ─────────────────────────────────────────────

_ESCALATION_PATCH = "slack.services.WebClient"


@pytest.mark.django_db
class TestSendEscalationInfoSlack:

    def test_send_escalation_happy_path(self, matching_attempt_with_coach, mock_slack_client):
        with patch(_ESCALATION_PATCH, return_value=mock_slack_client):
            send_escalation_info_slack(matching_attempt_with_coach)

        mock_slack_client.conversations_open.assert_called_once_with(users=["U_BL"])
        log = SlackLog.objects.get()
        assert log.status == SlackLog.Status.SENT
        assert log.matching_attempt == matching_attempt_with_coach

    def test_send_escalation_no_slack_id_raises(self, matching_attempt_no_bl_slack, mock_slack_client):
        with patch(_ESCALATION_PATCH, return_value=mock_slack_client):
            with pytest.raises(ValueError):
                send_escalation_info_slack(matching_attempt_no_bl_slack)

        mock_slack_client.conversations_open.assert_not_called()
        assert SlackLog.objects.count() == 0

    def test_send_escalation_slack_api_error(self, matching_attempt_with_coach, mock_slack_client):
        mock_slack_client.conversations_open.side_effect = _make_slack_error()

        with patch(_ESCALATION_PATCH, return_value=mock_slack_client):
            send_escalation_info_slack(matching_attempt_with_coach)

        log = SlackLog.objects.get()
        assert log.status == SlackLog.Status.FAILED
        assert log.error_message != ""

    def test_send_escalation_generic_exception(self, matching_attempt_with_coach, mock_slack_client):
        mock_slack_client.chat_postMessage.side_effect = RuntimeError("error")

        with patch(_ESCALATION_PATCH, return_value=mock_slack_client):
            send_escalation_info_slack(matching_attempt_with_coach)

        log = SlackLog.objects.get()
        assert log.status == SlackLog.Status.FAILED
        assert "error" in log.error_message

    def test_send_escalation_log_linked_to_ma(self, matching_attempt_with_coach, bl_contact, mock_slack_client):
        with patch(_ESCALATION_PATCH, return_value=mock_slack_client):
            send_escalation_info_slack(matching_attempt_with_coach)

        log = SlackLog.objects.get()
        assert log.matching_attempt == matching_attempt_with_coach
        assert log.to == bl_contact.user


# ── 9. send_all_rtcs_declined_info_slack ──────────────────────────────────────

_ALL_DECLINED_PATCH = "slack.services.WebClient"


@pytest.mark.django_db
class TestSendAllRtcsDeclinedInfoSlack:

    def test_send_all_declined_happy_path(self, matching_attempt_with_coach, mock_slack_client):
        with patch(_ALL_DECLINED_PATCH, return_value=mock_slack_client):
            send_all_rtcs_declined_info_slack(matching_attempt_with_coach)

        mock_slack_client.chat_postMessage.assert_called_once()
        log = SlackLog.objects.get()
        assert log.status == SlackLog.Status.SENT
        assert log.matching_attempt == matching_attempt_with_coach

    def test_send_all_declined_no_slack_id_raises(self, matching_attempt_no_bl_slack, mock_slack_client):
        with patch(_ALL_DECLINED_PATCH, return_value=mock_slack_client):
            with pytest.raises(ValueError):
                send_all_rtcs_declined_info_slack(matching_attempt_no_bl_slack)

        mock_slack_client.conversations_open.assert_not_called()
        assert SlackLog.objects.count() == 0

    def test_send_all_declined_slack_api_error(self, matching_attempt_with_coach, mock_slack_client):
        mock_slack_client.conversations_open.side_effect = _make_slack_error()

        with patch(_ALL_DECLINED_PATCH, return_value=mock_slack_client):
            send_all_rtcs_declined_info_slack(matching_attempt_with_coach)

        log = SlackLog.objects.get()
        assert log.status == SlackLog.Status.FAILED
        assert log.error_message != ""

    def test_send_all_declined_generic_exception(self, matching_attempt_with_coach, mock_slack_client):
        mock_slack_client.chat_postMessage.side_effect = RuntimeError("net error")

        with patch(_ALL_DECLINED_PATCH, return_value=mock_slack_client):
            send_all_rtcs_declined_info_slack(matching_attempt_with_coach)

        log = SlackLog.objects.get()
        assert log.status == SlackLog.Status.FAILED
        assert "net error" in log.error_message


# ── 10. send_clarification_need_info_to_coach_slack ───────────────────────────

_CLARIFICATION_PATCH = "slack.services.WebClient"


@pytest.mark.django_db
class TestSendClarificationNeedInfoToCoachSlack:

    def test_send_clarification_happy_path(self, matching_attempt_with_coach, mock_slack_client):
        with patch(_CLARIFICATION_PATCH, return_value=mock_slack_client):
            send_clarification_need_info_to_coach_slack(matching_attempt_with_coach)

        mock_slack_client.chat_postMessage.assert_called_once()
        log = SlackLog.objects.get()
        assert log.status == SlackLog.Status.SENT
        assert log.matching_attempt == matching_attempt_with_coach
        assert log.sent_by == SlackLog.SentBy.SYSTEM

    def test_send_clarification_no_slack_id_raises(self, matching_attempt_no_coach_slack, mock_slack_client):
        with patch(_CLARIFICATION_PATCH, return_value=mock_slack_client):
            with pytest.raises(ValueError):
                send_clarification_need_info_to_coach_slack(matching_attempt_no_coach_slack)

        mock_slack_client.conversations_open.assert_not_called()
        assert SlackLog.objects.count() == 0

    def test_send_clarification_slack_api_error(self, matching_attempt_with_coach, mock_slack_client):
        mock_slack_client.conversations_open.side_effect = _make_slack_error()

        with patch(_CLARIFICATION_PATCH, return_value=mock_slack_client):
            send_clarification_need_info_to_coach_slack(matching_attempt_with_coach)

        log = SlackLog.objects.get()
        assert log.status == SlackLog.Status.FAILED
        assert log.error_message != ""

    def test_send_clarification_generic_exception(self, matching_attempt_with_coach, mock_slack_client):
        mock_slack_client.chat_postMessage.side_effect = RuntimeError("crash")

        with patch(_CLARIFICATION_PATCH, return_value=mock_slack_client):
            send_clarification_need_info_to_coach_slack(matching_attempt_with_coach)

        log = SlackLog.objects.get()
        assert log.status == SlackLog.Status.FAILED
        assert "crash" in log.error_message

