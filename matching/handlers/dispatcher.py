from matching.models import MatchingEvent
from matching.handlers import notification_handlers
from matching.handlers import state_hanlders

def dispatch_event(event: MatchingEvent):
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
        MatchingEvent.EventType.CLARIFICATION_NEEEDED_FEEDBACK_RECEIVED_FROM_PARTICIPANT: [
            notification_handlers.handle_clarification_needed_feedback_received_from_participant_event,
        ],
        MatchingEvent.EventType.ESCALATION_NOTIFICATION_SENT_TO_STAFF: [
            notification_handlers.handle_escalation_notification_sent_to_staff_event,
        ],
        MatchingEvent.EventType.INFORMATION_ABOUT_CLARIFICATION_SENT_TO_COACH: [
            notification_handlers.handle_clarification_need_info_to_coach_event,
        ],
        MatchingEvent.EventType.RTC_TIMED_OUT: [
            notification_handlers.handle_rtc_timed_out_event,
        ],
        MatchingEvent.EventType.RTC_REMINDER_SENT_TO_COACH: [
            notification_handlers.handle_rtc_reminder_sent_to_coach_event,
        ],
        
        # State handlers
        MatchingEvent.EventType.ALL_RTCS_DECLINED: [
            notification_handlers.handle_all_rtcs_declined_event,
        ],
        
    }

    event_handlers = handlers.get(event.event_type, [])

    for handler in event_handlers:
        handler(event)