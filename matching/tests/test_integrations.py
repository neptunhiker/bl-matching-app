import pytest

from matching.models import MatchingAttempt


# ---------------------------------------------------------------------------
# Issue 1a — handle_all_rtcs_declined_event atomicity
# ---------------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_all_rtcs_declined_atomicity(matching_attempt, monkeypatch):
    """
    @transaction.atomic on handle_all_rtcs_declined_event must roll back
    both the disable_automation save and the state transition save if any
    later step (e.g. Slack notification) raises.
    """
    from matching.models import MatchingEvent, TriggeredByOptions
    from matching.handlers.notification_handlers import handle_all_rtcs_declined_event

    # Bypass FSM protection to put the attempt in the required source state.
    MatchingAttempt.objects.filter(pk=matching_attempt.pk).update(
        state=MatchingAttempt.State.AWAITING_RTC_REPLY,
        automation_enabled=True,
    )
    # refresh_from_db() is blocked by FSMField protected=True; fetch a fresh instance.
    attempt = MatchingAttempt.objects.get(pk=matching_attempt.pk)

    def raise_slack(*_args, **_kwargs):
        raise RuntimeError("slack is down")

    monkeypatch.setattr(
        "matching.handlers.notification_handlers.send_all_rtcs_declined_info_slack",
        raise_slack,
    )

    # Pass an unsaved event instance directly — bypasses signal dispatch so
    # we control the exact moment the handler runs.
    event = MatchingEvent(
        matching_attempt=attempt,
        event_type=MatchingEvent.EventType.ALL_RTCS_DECLINED,
        triggered_by=TriggeredByOptions.SYSTEM,
    )

    with pytest.raises(RuntimeError, match="slack is down"):
        handle_all_rtcs_declined_event(event)

    # FSMField protected=True blocks refresh_from_db(); fetch a fresh instance.
    fresh = MatchingAttempt.objects.get(pk=matching_attempt.pk)
    assert fresh.automation_enabled is True, (
        "automation_enabled should be rolled back to True — "
        "@transaction.atomic did not protect the disable_automation write"
    )
    assert fresh.state == MatchingAttempt.State.AWAITING_RTC_REPLY, (
        "state should be rolled back to AWAITING_RTC_REPLY — "
        "@transaction.atomic did not protect the state save"
    )


# ---------------------------------------------------------------------------
# Issue 1c — save() before trigger_start_matching() in the view
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_start_matching_state_committed_before_handlers_fire(
    matching_attempt, rtc, staff_user, monkeypatch
):
    """
    After the 1c fix, matching_attempt.save() is called before
    trigger_start_matching(), so when handle_matching_started_or_resumed_event
    executes the DB-persisted state is already AWAITING_RTC_REPLY.
    """
    from django.db import transaction
    from matching import services
    from matching.handlers import notification_handlers

    matching_attempt.automation_enabled = True
    matching_attempt.save()

    captured_state = []

    def capturing_handler(event):
        db_state = (
            MatchingAttempt.objects
            .values_list("state", flat=True)
            .get(pk=event.matching_attempt.pk)
        )
        captured_state.append(db_state)

    monkeypatch.setattr(
        notification_handlers,
        "handle_matching_started_or_resumed_event",
        capturing_handler,
    )

    with transaction.atomic():
        matching_attempt.start_matching()
        matching_attempt.save()
        services.trigger_start_matching(matching_attempt, staff_user)

    assert len(captured_state) == 1, "handler should have been called exactly once"
    assert captured_state[0] == MatchingAttempt.State.AWAITING_RTC_REPLY, (
        "DB state must be AWAITING_RTC_REPLY when the handler fires — "
        "save() must come before trigger_start_matching()"
    )
