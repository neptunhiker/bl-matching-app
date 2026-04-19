import logging

from matching.models import MatchingEvent
from matching.handlers import notification_handlers
from matching.handlers import state_handlers

logger = logging.getLogger(__name__)


def dispatch_event(event: MatchingEvent):
    """
    Routes a MatchingEvent to its registered handlers.

    Automation gate: if automation_enabled is False on the underlying
    MatchingAttempt, dispatch is skipped entirely. No exceptions —
    when automation is off, nothing happens.
    """
    if not event.matching_attempt.automation_enabled:
        logger.info(
            "Automation disabled for MatchingAttempt %s — skipping dispatch for event %s",
            event.matching_attempt_id,
            event.event_type,
        )
        return

    handlers = {
        MatchingEvent.EventType.STARTED: [
            notification_handlers.handle_matching_started_or_resumed_event,
        ],
        MatchingEvent.EventType.RESUMED: [
            notification_handlers.handle_matching_started_or_resumed_event,
        ],
        MatchingEvent.EventType.RTC_SENT_TO_COACH: [
            notification_handlers.handle_rtq_sent_event,
        ],
        MatchingEvent.EventType.RTC_ACCEPTED: [
            notification_handlers.handle_matching_request_accepted_event,
        ],
        MatchingEvent.EventType.RTC_DECLINED: [
            notification_handlers.handle_matching_request_declined_event,
        ],
        MatchingEvent.EventType.INTRO_CALL_REQUEST_SENT_TO_COACH: [
            notification_handlers.handle_intro_call_sent_to_coach_event,
        ],
        MatchingEvent.EventType.INTRO_CALL_INFO_SENT_TO_PARTICIPANT: [
            notification_handlers.handle_intro_call_info_sent_to_participant_event,
        ],
        MatchingEvent.EventType.INTRO_CALL_FEEDBACK_RECEIVED_FROM_COACH: [
            notification_handlers.handle_intro_call_feedback_received_from_coach_event,
        ],
        MatchingEvent.EventType.INTRO_CALL_FEEDBACK_REQUESTED_FROM_PARTICIPANT: [
            notification_handlers.handle_intro_call_feedback_requested_from_participant_event,
        ],
        MatchingEvent.EventType.COACHING_CAN_START_FEEDBACK_RECEIVED_FROM_PARTICIPANT: [
            notification_handlers.handle_coaching_can_start_feedback_received_from_participant_event,
        ],
        MatchingEvent.EventType.COACHING_START_INFO_SENT_TO_COACH: [
            notification_handlers.handle_coaching_start_info_sent_out_to_coach_event,
        ],
        MatchingEvent.EventType.COACHING_START_INFO_SENT_TO_PARTICIPANT: [
            notification_handlers.handle_coaching_start_info_sent_out_to_participant_event,
        ],
        MatchingEvent.EventType.ESCALATION_NOTIFICATION_SENT_TO_STAFF: [
            notification_handlers.handle_escalation_notification_sent_to_staff_event,
        ],
        MatchingEvent.EventType.RTC_TIMED_OUT: [
            notification_handlers.handle_rtc_timed_out_event,
        ],
        MatchingEvent.EventType.RTC_REMINDER_SENT_TO_COACH: [
            notification_handlers.handle_rtc_reminder_sent_to_coach_event,
        ],
        MatchingEvent.EventType.INTRO_CALL_REMINDER_SENT_TO_COACH: [
            notification_handlers.handle_intro_call_reminder_sent_to_coach_event,
        ],
        MatchingEvent.EventType.INTRO_CALL_TIMED_OUT_STAFF_NOTIFIED: [
            notification_handlers.handle_intro_call_timed_out_staff_notified_event,
        ],
        MatchingEvent.EventType.CLARIFICATION_CALL_BOOKED: [
            notification_handlers.handle_clarification_call_booked_event,
        ],
        MatchingEvent.EventType.CLARIFICATION_CALL_CANCELED: [
            notification_handlers.handle_clarification_call_canceled_event,
        ],
        
        # State handlers
        MatchingEvent.EventType.ALL_RTCS_DECLINED: [
            notification_handlers.handle_all_rtcs_declined_event,
        ],
        
    }

    event_handlers = handlers.get(event.event_type, [])

    for handler in event_handlers:
        handler(event)