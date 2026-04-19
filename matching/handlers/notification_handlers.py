import logging 

from django.db import transaction

from emails.services import send_first_coach_request_email, send_reminder_coach_request_email, send_intro_call_request_email, send_intro_call_info_email_to_participant, send_feedback_request_email_after_intro_call_to_participant, send_coaching_start_info_email_to_coach, send_coaching_start_info_email_to_participant, send_escalation_info_email_to_staff, send_clarification_call_booked_info_to_coach_email
from profiles.models import Coach
from slack.services import send_first_coach_request_slack, send_reminder_coach_request_slack, send_intro_call_request_slack, send_coaching_starting_info_slack, send_escalation_info_slack, send_all_rtcs_declined_info_slack, send_intro_call_reminder_slack, send_intro_call_timeout_notification_to_staff_slack, send_clarification_call_booked_info_to_staff_slack, send_clarification_call_booked_info_to_coach_slack

logger = logging.getLogger(__name__)

@transaction.atomic
def handle_matching_started_or_resumed_event(event):
    from matching import services
    from matching.models import MatchingEvent
    
    logger.debug(f"Handling matching started or resumed event: {event.id}")
    
    if event.event_type not in [MatchingEvent.EventType.STARTED, MatchingEvent.EventType.RESUMED]:
        return

    matching_attempt = event.matching_attempt
    
    next_rtc = matching_attempt.get_next_request()
    if next_rtc:
        logger.debug(f"Triggering send_request for RTC {next_rtc.id}")
        next_rtc.send_first_request() # Transitions state to AWAITING_REPLY and sets deadline for coach response
        next_rtc.save()  # Ensure state change is saved
        
        services.create_matching_event(
            matching_attempt=matching_attempt,
            event_type=MatchingEvent.EventType.RTC_SENT_TO_COACH,
            triggered_by=event.triggered_by,
            triggered_by_user=event.triggered_by_user,
            payload={
                "rtc_id": str(next_rtc.id),
            }
         )
        
    else:
        logger.debug(f"No RTC in preparation state found for MatchingAttempt {event.matching_attempt.id} at matching started event")

@transaction.atomic
def handle_rtq_sent_event(event):
    from matching.models import RequestToCoach
    from matching.models import MatchingEvent
    
    if event.event_type != MatchingEvent.EventType.RTC_SENT_TO_COACH:
        return
    
    logger.debug(f"Handling RTQ_SENT event: {event.id}")
    
    rtc_id = event.payload["rtc_id"]
    rtc = RequestToCoach.objects.get(id=rtc_id)
    coach = rtc.coach

    if coach.preferred_communication_channel == Coach.CommunicationChannel.SLACK:
        send_first_coach_request_slack(
            rtc, 
        )
        
    elif coach.preferred_communication_channel == Coach.CommunicationChannel.EMAIL:
        send_first_coach_request_email(
            rtc, 
        )
    else:
        raise ValueError(f"Unsupported communication channel for coach {coach}: {coach.preferred_communication_channel}")
    
def handle_rtc_reminder_sent_to_coach_event(event):
    from matching.models import MatchingEvent
    
    if event.event_type != MatchingEvent.EventType.RTC_REMINDER_SENT_TO_COACH:
        return
    
    logger.debug(f"Handling RTC_REMINDER_SENT event: {event.id}")
    
    rtc = event.request_to_coach
    coach = rtc.coach

    if coach.preferred_communication_channel == Coach.CommunicationChannel.SLACK:
        logger.debug(f"Sending reminder coach request notification via Slack for RequestToCoach to coach {coach} (user: {coach.user})")
        send_reminder_coach_request_slack(rtc)
        
    elif coach.preferred_communication_channel == Coach.CommunicationChannel.EMAIL:
        send_reminder_coach_request_email(rtc)
    else:
        raise ValueError(f"Unsupported communication channel for coach {coach}: {coach.preferred_communication_channel}")
    
    
@transaction.atomic
def handle_matching_request_accepted_event(event):
    from matching.models import MatchingEvent
    from matching import services
    
    if event.event_type != MatchingEvent.EventType.RTC_ACCEPTED:
        return
    
    logger.debug(f"Handling RTC_ACCEPTED event: {event.id}")
    
    on_time = event.payload.get("on_time", None)
    matching_attempt = event.matching_attempt
    
    if on_time: 
        # if on_time we need to update the state of the matching_attempt and create events that will trigger the sending of notifications to coach and participant
        
        # Change state of matching attempt to AWAITING_INTRO_CALL_FEEDBACK_FROM_COACH
        matching_attempt.send_intro_call_notifications()
        matching_attempt.save() # Ensure state change is saved before event is created
        
        services.continue_matching_after_rtc_accepted(matching_attempt)

        
@transaction.atomic
def handle_matching_request_declined_event(event):
    from matching.models import MatchingEvent, TriggeredByOptions
    from matching import services
    
    if event.event_type != MatchingEvent.EventType.RTC_DECLINED:
        return
    
    logger.debug(f"Handling RTC_DECLINED event: {event.id}")
    
    on_time = event.payload.get("on_time", None)
    matching_attempt = event.matching_attempt
    
    if on_time: 
        # if on_time we can already proceed with approaching the next coach and sending out a new request to coach notification
        
        next_request = matching_attempt.get_next_request()
        if not next_request:
            logger.debug(f"No more coaches to approach for MatchingAttempt {matching_attempt.id} after RTC declined event")
            services.create_matching_event(
                matching_attempt=matching_attempt,
                triggered_by=TriggeredByOptions.SYSTEM,
                triggered_by_user=None,
                event_type=MatchingEvent.EventType.ALL_RTCS_DECLINED,
                payload={
                    "reason": "No more coaches to approach",
                }
            )
            return
        
        next_request.send_first_request() # Transitions state to AWAITING_REPLY and sets deadline for coach response
        next_request.save() # Ensure state change is saved before event is created
        
        services.create_matching_event(
            matching_attempt=matching_attempt,
            event_type=MatchingEvent.EventType.RTC_SENT_TO_COACH,
            triggered_by=TriggeredByOptions.SYSTEM,
            triggered_by_user=None,
            payload={
                "rtc_id": str(next_request.id),
            }
        )
        
 
    # if not on_time we don't need to do anything
        
    
def handle_intro_call_sent_to_coach_event(event):
    from matching.models import MatchingEvent
    
    if event.event_type != MatchingEvent.EventType.INTRO_CALL_REQUEST_SENT_TO_COACH:
        return
    
    logger.debug(f"Handling INTRO_CALL_REQUEST_SENT_TO_COACH event: {event.id}")
    
    matching_attempt = event.matching_attempt
    triggered_by = event.triggered_by
    triggered_by_user = event.triggered_by_user
    
    coach = matching_attempt.matched_coach

    if coach.preferred_communication_channel == Coach.CommunicationChannel.SLACK:
        send_intro_call_request_slack(matching_attempt)
        
    elif coach.preferred_communication_channel == Coach.CommunicationChannel.EMAIL:
        send_intro_call_request_email(matching_attempt)
    else:
        raise ValueError(f"Unsupported communication channel for coach {coach}: {coach.preferred_communication_channel}")


def handle_intro_call_info_sent_to_participant_event(event):
    from matching.models import MatchingEvent
    
    if event.event_type != MatchingEvent.EventType.INTRO_CALL_INFO_SENT_TO_PARTICIPANT:
        return
    
    logger.debug(f"Handling INTRO_CALL_INFO_SENT_TO_PARTICIPANT event: {event.id}")
    
    matching_attempt = event.matching_attempt
    triggered_by = event.triggered_by
        
    # Inform participant
    send_intro_call_info_email_to_participant(matching_attempt, triggered_by=triggered_by)
    
    
def handle_intro_call_feedback_received_from_coach_event(event):
    from matching.models import MatchingEvent
    from matching import services
    
    if event.event_type != MatchingEvent.EventType.INTRO_CALL_FEEDBACK_RECEIVED_FROM_COACH:
        return
    
    logger.debug(f"Handling INTRO_CALL_FEEDBACK_RECEIVED_FROM_COACH event: {event.id}")

    matching_attempt = event.matching_attempt
    
    matching_attempt.send_request_for_intro_call_feedback_to_participant()
    matching_attempt.save()
    
    services.continue_matching_after_intro_call_feedback_from_coach(matching_attempt)
    
def handle_intro_call_feedback_requested_from_participant_event(event):
    from matching.models import MatchingEvent, TriggeredByOptions
    
    if event.event_type != MatchingEvent.EventType.INTRO_CALL_FEEDBACK_REQUESTED_FROM_PARTICIPANT:
        return
    
    logger.debug(f"Handling INTRO_CALL_FEEDBACK_REQUESTED_FROM_PARTICIPANT event: {event.id}")

    matching_attempt = event.matching_attempt
    
    # Inform participant
    send_feedback_request_email_after_intro_call_to_participant(matching_attempt, triggered_by=TriggeredByOptions.SYSTEM)
    
def handle_coaching_can_start_feedback_received_from_participant_event(event):
    from matching.models import MatchingEvent
    from matching import services
    
    if event.event_type != MatchingEvent.EventType.COACHING_CAN_START_FEEDBACK_RECEIVED_FROM_PARTICIPANT:
        return
    
    logger.debug(f"Handling COACHING_CAN_START_FEEDBACK_RECEIVED_FROM_PARTICIPANT event: {event.id}")

    matching_attempt = event.matching_attempt
    matching_attempt.complete_matching()
    matching_attempt.save()
    
    services.send_out_official_coaching_start_notification(matching_attempt)
    
def handle_coaching_start_info_sent_out_to_coach_event(event):
    from matching.models import MatchingEvent
    
    if event.event_type != MatchingEvent.EventType.COACHING_START_INFO_SENT_TO_COACH:
        return
    
    logger.debug(f"Handling COACHING_START_INFO_SENT_TO_COACH event: {event.id}")
    
    matching_attempt = event.matching_attempt

        
    coach = matching_attempt.matched_coach

    if coach.preferred_communication_channel == Coach.CommunicationChannel.SLACK:
        send_coaching_starting_info_slack(matching_attempt)
        
    elif coach.preferred_communication_channel == Coach.CommunicationChannel.EMAIL:
        send_coaching_start_info_email_to_coach(matching_attempt)
    else:
        raise ValueError(f"Unsupported communication channel for coach {coach}: {coach.preferred_communication_channel}")
    
def handle_coaching_start_info_sent_out_to_participant_event(event):
    from matching.models import MatchingEvent
    
    if event.event_type != MatchingEvent.EventType.COACHING_START_INFO_SENT_TO_PARTICIPANT:
        return
    
    logger.debug(f"Handling COACHING_START_INFO_SENT_TO_PARTICIPANT event: {event.id}")
    
    send_coaching_start_info_email_to_participant(event.matching_attempt)
    
def handle_escalation_notification_sent_to_staff_event(event):
    from matching.models import MatchingEvent
    
    if event.event_type != MatchingEvent.EventType.ESCALATION_NOTIFICATION_SENT_TO_STAFF:
        return
    
    logger.debug(f"Handling ESCALATION_NOTIFICATION_SENT_TO_STAFF event: {event.id}")
    
    try:
        send_escalation_info_slack(event.matching_attempt)
    except Exception as e:
        logger.warning(
            f"Failed to send escalation info Slack message for MatchingAttempt "
            f"{event.matching_attempt.id}: {e}. Falling back to email."
        )
        send_escalation_info_email_to_staff(event.matching_attempt)
    
    
@transaction.atomic
def handle_all_rtcs_declined_event(event):
    from matching.models import MatchingEvent, TriggeredByOptions
    
    if event.event_type != MatchingEvent.EventType.ALL_RTCS_DECLINED:
        return
    
    logger.debug(f"Handling ALL_RTCS_DECLINED event: {event.id}")
    
    matching_attempt = event.matching_attempt
    matching_attempt.run_out_of_matching_requests_to_coaches()
    matching_attempt.disable_automation(triggered_by=TriggeredByOptions.SYSTEM)
    matching_attempt.save()
    
    # inform bl_contact via Slack
    send_all_rtcs_declined_info_slack(matching_attempt)
    
@transaction.atomic
def handle_rtc_timed_out_event(event):
    from matching import services
    from matching.models import MatchingEvent, TriggeredByOptions
    
    logger.debug(f"Handling RTC_TIMED_OUT event: {event.id}")
    
    if event.event_type != MatchingEvent.EventType.RTC_TIMED_OUT:
        return

    matching_attempt = event.matching_attempt
    
    next_rtc = matching_attempt.get_next_request()
    if next_rtc:
        logger.debug(f"Triggering send_request for RTC {next_rtc.id}")
        next_rtc.send_first_request() # Transitions state to AWAITING_REPLY and sets deadline for coach response
        next_rtc.save()  # Ensure state change is saved
        
        services.create_matching_event(
            matching_attempt=matching_attempt,
            event_type=MatchingEvent.EventType.RTC_SENT_TO_COACH,
            triggered_by=TriggeredByOptions.SYSTEM,
            payload={
                "rtc_id": str(next_rtc.id),
            }
         )
        
    else:
        
        logger.debug(f"No more coaches to approach for MatchingAttempt {matching_attempt.id} after RTC declined event")
        services.create_matching_event(
            matching_attempt=matching_attempt,
            triggered_by=TriggeredByOptions.SYSTEM,
            triggered_by_user=None,
            event_type=MatchingEvent.EventType.ALL_RTCS_DECLINED,
            payload={
                "reason": "No more coaches to approach",
            }
        )
        return


def handle_intro_call_reminder_sent_to_coach_event(event):
    from matching.models import MatchingEvent

    if event.event_type != MatchingEvent.EventType.INTRO_CALL_REMINDER_SENT_TO_COACH:
        return

    logger.debug(f"Handling INTRO_CALL_REMINDER_SENT_TO_COACH event: {event.id}")

    matching_attempt = event.matching_attempt
    coach = matching_attempt.matched_coach

    if coach.preferred_communication_channel == Coach.CommunicationChannel.SLACK:
        send_intro_call_reminder_slack(matching_attempt)
    elif coach.preferred_communication_channel == Coach.CommunicationChannel.EMAIL:
        # Email reminder not yet implemented — fall back to Slack
        logger.warning(
            f"Email intro call reminder not implemented for coach {coach}; "
            f"sending Slack reminder instead."
        )
        send_intro_call_reminder_slack(matching_attempt)
    else:
        raise ValueError(f"Unsupported communication channel for coach {coach}: {coach.preferred_communication_channel}")


def handle_intro_call_timed_out_staff_notified_event(event):
    from matching.models import MatchingEvent

    if event.event_type != MatchingEvent.EventType.INTRO_CALL_TIMED_OUT_STAFF_NOTIFIED:
        return

    logger.debug(f"Handling INTRO_CALL_TIMED_OUT_STAFF_NOTIFIED event: {event.id}")

    send_intro_call_timeout_notification_to_staff_slack(event.matching_attempt)


def handle_clarification_call_booked_event(event):
    from matching.models import MatchingEvent

    if event.event_type != MatchingEvent.EventType.CLARIFICATION_CALL_BOOKED:
        return

    logger.debug(f"Handling CLARIFICATION_CALL_BOOKED event: {event.id}")

    matching_attempt = event.matching_attempt
    coach = matching_attempt.matched_coach

    # Staff: Slack first, email fallback on failure
    try:
        send_clarification_call_booked_info_to_staff_slack(matching_attempt)
    except Exception:
        logger.warning(
            "Failed to send clarification call booked Slack to staff for MA %s — falling back to email",
            matching_attempt.id,
            exc_info=True,
        )
        send_escalation_info_email_to_staff(matching_attempt)

    # Coach: respect preferred_communication_channel
    if coach.preferred_communication_channel == Coach.CommunicationChannel.SLACK:
        send_clarification_call_booked_info_to_coach_slack(matching_attempt)
    elif coach.preferred_communication_channel == Coach.CommunicationChannel.EMAIL:
        send_clarification_call_booked_info_to_coach_email(matching_attempt)
    else:
        raise ValueError(
            f"Unsupported communication channel for coach {coach}: {coach.preferred_communication_channel}"
        )


def handle_clarification_call_canceled_event(event):
    from matching.models import MatchingEvent

    if event.event_type != MatchingEvent.EventType.CLARIFICATION_CALL_CANCELED:
        return

    # No automated notification on cancellation — staff see this in the event log / admin
    logger.info("Clarification call canceled for matching attempt %s", event.matching_attempt_id)
