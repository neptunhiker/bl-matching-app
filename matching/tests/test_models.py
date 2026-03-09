import pytest

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.utils import timezone

from matching.models import MatchingAttempt, MatchingAttemptTransition, MatchingAttemptEvent, RequestToCoach, RequestToCoachTransition, RequestToCoachEvent, CoachActionToken


# ── RequestToCoach: Transitions ───────────────────────────────────────────────

class TestRequestToCoachTransition:

    def test_valid_transition_updates_status_and_creates_transition(self, rtc):
        rtc.status = RequestToCoach.Status.IN_PREPARATION
        rtc.save()

        updated = rtc.transition_to(RequestToCoach.Status.AWAITING_REPLY)

        updated.refresh_from_db()

        assert updated.status == RequestToCoach.Status.AWAITING_REPLY

        transition = RequestToCoachTransition.objects.get(request=updated)

        assert transition.from_status == RequestToCoach.Status.IN_PREPARATION
        assert transition.to_status == RequestToCoach.Status.AWAITING_REPLY

    def test_invalid_transition_raises_validation_error(self, rtc):
        rtc.status = RequestToCoach.Status.IN_PREPARATION
        rtc.save()

        with pytest.raises(ValidationError):
            rtc.transition_to(RequestToCoach.Status.ACCEPTED_ON_TIME)

    def test_invalid_triggered_by_raises(self, rtc):
        with pytest.raises(ValueError):
            rtc.transition_to(RequestToCoach.Status.AWAITING_REPLY, triggered_by="alien")

    def test_triggered_by_user_requires_staff_or_coach(self, rtc, coach_user):
        with pytest.raises(ValueError):
            rtc.transition_to(
                RequestToCoach.Status.AWAITING_REPLY,
                triggered_by="system",
                triggered_by_user=coach_user,
            )

    def test_transition_actor_constraint(self, rtc, coach_user):
        with pytest.raises(IntegrityError):
            RequestToCoachTransition.objects.create(
                request=rtc,
                from_status=RequestToCoach.Status.IN_PREPARATION,
                to_status=RequestToCoach.Status.AWAITING_REPLY,
                triggered_by="system",
                triggered_by_user=coach_user,
            )


# ── RequestToCoach: Accept / Reject ───────────────────────────────────────────

class TestRequestToCoachAcceptReject:

    def test_accept_before_deadline_sets_status_and_event(self, rtc):
        rtc.status = RequestToCoach.Status.AWAITING_REPLY
        rtc.deadline_at = timezone.now() + timezone.timedelta(hours=2)
        rtc.save()

        rtc.accept()

        rtc.refresh_from_db()

        assert rtc.status == RequestToCoach.Status.ACCEPTED_ON_TIME
        assert rtc.responded_at is not None

        event = RequestToCoachEvent.objects.get(request=rtc)
        assert event.event_type == RequestToCoachEvent.EventType.ACCEPTED

    def test_accept_after_deadline_sets_late_status(self, rtc):
        rtc.status = RequestToCoach.Status.AWAITING_REPLY
        rtc.deadline_at = timezone.now() - timezone.timedelta(hours=1)
        rtc.save()

        rtc.accept()

        rtc.refresh_from_db()

        assert rtc.status == RequestToCoach.Status.ACCEPTED_LATE

    def test_reject_before_deadline_sets_status_and_event(self, rtc):
        rtc.status = RequestToCoach.Status.AWAITING_REPLY
        rtc.deadline_at = timezone.now() + timezone.timedelta(hours=2)
        rtc.save()

        rtc.reject()

        rtc.refresh_from_db()

        assert rtc.status == RequestToCoach.Status.REJECTED_ON_TIME
        assert rtc.responded_at is not None

        event = RequestToCoachEvent.objects.get(request=rtc)
        assert event.event_type == RequestToCoachEvent.EventType.REJECTED

    def test_accept_not_allowed_if_not_awaiting_reply(self, rtc):
        rtc.status = RequestToCoach.Status.IN_PREPARATION
        rtc.save()

        with pytest.raises(ValidationError):
            rtc.accept()

    def test_reject_not_allowed_if_not_awaiting_reply(self, rtc):
        rtc.status = RequestToCoach.Status.IN_PREPARATION
        rtc.save()

        with pytest.raises(ValidationError):
            rtc.reject()


# ── RequestToCoach: Helpers ───────────────────────────────────────────────────

class TestRequestToCoachHelpers:

    def test_mark_responded_sets_timestamp_once(self, rtc):
        rtc.mark_responded()
        rtc.refresh_from_db()

        first_timestamp = rtc.responded_at
        assert first_timestamp is not None

        rtc.mark_responded()
        rtc.refresh_from_db()

        assert rtc.responded_at == first_timestamp

    def test_deadline_passed_returns_true_if_past(self, rtc):
        rtc.deadline_at = timezone.now() - timezone.timedelta(hours=1)

        assert rtc.is_deadline_passed() is True

    def test_deadline_passed_returns_false_if_future(self, rtc):
        rtc.deadline_at = timezone.now() + timezone.timedelta(hours=1)

        assert rtc.is_deadline_passed() is False

    def test_deadline_passed_returns_false_if_no_deadline(self, rtc):
        rtc.deadline_at = None

        assert rtc.is_deadline_passed() is False

    def test_can_send_request_respects_max_limit(self, rtc):
        rtc.requests_sent = 3
        rtc.max_number_of_requests = 3

        assert rtc.can_send_request() is False

    def test_cannot_send_reminder_without_first_email(self, rtc):
        rtc.status = RequestToCoach.Status.AWAITING_REPLY
        rtc.requests_sent = 0
        rtc.first_sent_at = None

        assert rtc.can_send_reminder() is False

    def test_cannot_send_reminder_after_deadline(self, rtc):
        rtc.status = RequestToCoach.Status.AWAITING_REPLY
        rtc.first_sent_at = timezone.now()
        rtc.deadline_at = timezone.now() - timezone.timedelta(hours=1)

        assert rtc.can_send_reminder() is False

    def test_can_send_reminder_when_all_conditions_met(self, rtc):
        rtc.status = RequestToCoach.Status.AWAITING_REPLY
        rtc.first_sent_at = timezone.now() - timezone.timedelta(hours=1)
        rtc.deadline_at = timezone.now() + timezone.timedelta(hours=24)
        rtc.requests_sent = 1
        rtc.max_number_of_requests = 3

        assert rtc.can_send_reminder() is True


# ── MatchingAttempt: Queue Helpers ────────────────────────────────────────────

class TestMatchingAttemptQueueHelpers:

    @pytest.mark.django_db
    def test_get_active_request(self, matching_attempt, coach, coach_2):
        rtc_1 = RequestToCoach.objects.create(
            matching_attempt=matching_attempt,
            coach=coach,
            status=RequestToCoach.Status.AWAITING_REPLY,
            priority=1,
        )

        rtc_2 = RequestToCoach.objects.create(
            matching_attempt=matching_attempt,
            coach=coach_2,
            status=RequestToCoach.Status.ACCEPTED_ON_TIME,
            priority=30,
        )

        assert matching_attempt.get_active_requests() == [rtc_1]

    @pytest.mark.django_db
    def test_get_next_request_returns_lowest_priority(self, matching_attempt, coach, coach_2):
        rtc_high = RequestToCoach.objects.create(
            matching_attempt=matching_attempt,
            coach=coach,
            status=RequestToCoach.Status.IN_PREPARATION,
            priority=1,
        )
        RequestToCoach.objects.create(
            matching_attempt=matching_attempt,
            coach=coach_2,
            status=RequestToCoach.Status.IN_PREPARATION,
            priority=30,
        )

        assert matching_attempt.get_next_request() == rtc_high

    @pytest.mark.django_db
    def test_has_remaining_requests_returns_true(self, matching_attempt, coach):
        RequestToCoach.objects.create(
            matching_attempt=matching_attempt,
            coach=coach,
            status=RequestToCoach.Status.IN_PREPARATION,
            priority=1,
        )

        assert matching_attempt.has_remaining_requests() is True

    @pytest.mark.django_db
    def test_has_remaining_requests_returns_false_when_none_left(self, matching_attempt, coach):
        RequestToCoach.objects.create(
            matching_attempt=matching_attempt,
            coach=coach,
            status=RequestToCoach.Status.AWAITING_REPLY,
            priority=1,
        )

        assert matching_attempt.has_remaining_requests() is False


# ── RequestToCoach: Constraints & String Representation ──────────────────────

class TestRequestToCoachConstraints:

    def test_unique_coach_request_per_matching_attempt(self, matching_attempt, coach):

        RequestToCoach.objects.create(
            matching_attempt=matching_attempt,
            coach=coach,
            priority=1,
        )

        with pytest.raises(IntegrityError):
            RequestToCoach.objects.create(
                matching_attempt=matching_attempt,
                coach=coach,
                priority=2,
            )

    def test_request_to_coach_str_contains_names(self, rtc):

        text = str(rtc)

        assert rtc.coach.first_name in text
        assert rtc.matching_attempt.participant.first_name in text

    def test_only_one_awaiting_reply_per_matching_attempt(self, matching_attempt, coach, coach_2):
        RequestToCoach.objects.create(
            matching_attempt=matching_attempt,
            coach=coach,
            status=RequestToCoach.Status.AWAITING_REPLY,
            priority=1,
        )

        with pytest.raises(IntegrityError):
            RequestToCoach.objects.create(
                matching_attempt=matching_attempt,
                coach=coach_2,
                status=RequestToCoach.Status.AWAITING_REPLY,
                priority=2,
            )


# ── RequestToCoachEvent ───────────────────────────────────────────────────────

class TestRequestToCoachEvent:

    def test_system_event_created_without_user(self, rtc):
        event = RequestToCoachEvent.objects.create(
            request=rtc,
            event_type=RequestToCoachEvent.EventType.REQUEST_SENT,
            triggered_by=RequestToCoachEvent.TriggeredBy.SYSTEM,
        )

        assert event.triggered_by_user is None

    def test_coach_event_without_user_violates_constraint(self, rtc):
        with pytest.raises(IntegrityError):
            RequestToCoachEvent.objects.create(
                request=rtc,
                event_type=RequestToCoachEvent.EventType.ACCEPTED,
                triggered_by=RequestToCoachEvent.TriggeredBy.COACH,
                triggered_by_user=None,
            )

    def test_events_deleted_when_rtc_deleted(self, rtc, coach_user):
        RequestToCoachEvent.objects.create(
            request=rtc,
            event_type=RequestToCoachEvent.EventType.REQUEST_SENT,
            triggered_by=RequestToCoachEvent.TriggeredBy.SYSTEM,
        )

        rtc.delete()

        assert RequestToCoachEvent.objects.filter(request_id=rtc.pk).count() == 0


# ── CoachActionToken ──────────────────────────────────────────────────────────

class TestCoachActionToken:

    def test_token_must_be_unique(self, rtc):

        CoachActionToken.objects.create(
            token="test-token",
            request_to_coach=rtc,
            action=CoachActionToken.Action.ACCEPT,
        )

        with pytest.raises(IntegrityError):
            CoachActionToken.objects.create(
                token="test-token",
                request_to_coach=rtc,
                action=CoachActionToken.Action.DECLINE,
            )

    def test_new_token_is_unused(self, rtc):

        token = CoachActionToken.objects.create(
            token="abc123",
            request_to_coach=rtc,
            action=CoachActionToken.Action.ACCEPT,
        )

        assert token.used_at is None

    def test_token_action_is_stored_correctly(self, rtc):

        token = CoachActionToken.objects.create(
            token="xyz",
            request_to_coach=rtc,
            action=CoachActionToken.Action.DECLINE,
        )

        assert token.action == CoachActionToken.Action.DECLINE

    def test_token_belongs_to_request(self, rtc):

        token = CoachActionToken.objects.create(
            token="abc",
            request_to_coach=rtc,
            action=CoachActionToken.Action.ACCEPT,
        )

        assert token.request_to_coach == rtc


# ── MatchingAttempt ───────────────────────────────────────────────────────────

class TestMatchingAttempt:
    def test_draft_to_ready_for_matching_allowed(self, matching_attempt):

        matching_attempt = matching_attempt.transition_to(
            MatchingAttempt.Status.READY_FOR_MATCHING
        )

        assert matching_attempt.status == MatchingAttempt.Status.READY_FOR_MATCHING

    def test_draft_to_match_confirmed_not_allowed(self, matching_attempt):
        with pytest.raises(ValidationError):
            matching_attempt.transition_to(MatchingAttempt.Status.MATCH_CONFIRMED)

    def test_no_transition_from_match_confirmed(self, matching_attempt):
        matching_attempt.status = MatchingAttempt.Status.MATCH_CONFIRMED

        with pytest.raises(ValidationError):
            matching_attempt.transition_to(MatchingAttempt.Status.MATCHING_ACTIVE)

    def test_only_one_active_matching_attempt_per_participant(self, participant):
        MatchingAttempt.objects.create(
            participant=participant,
            status=MatchingAttempt.Status.DRAFT
        )

        with pytest.raises(IntegrityError):
            MatchingAttempt.objects.create(
                participant=participant,
                status=MatchingAttempt.Status.READY_FOR_MATCHING
            )

    def test_new_attempt_allowed_after_failure(self, participant):
        MatchingAttempt.objects.create(
            participant=participant,
            status=MatchingAttempt.Status.FAILED
        )

        MatchingAttempt.objects.create(
            participant=participant,
            status=MatchingAttempt.Status.DRAFT
        )

    def test_is_active_property(self, matching_attempt):
        matching_attempt.status = MatchingAttempt.Status.MATCHING_ACTIVE
        matching_attempt.save()

        assert matching_attempt.is_active is True

    def test_is_active_returns_false_for_terminal_status(self, matching_attempt):
        matching_attempt.status = MatchingAttempt.Status.CANCELLED
        matching_attempt.save()

        assert matching_attempt.is_active is False

    def test_string_representation(self, matching_attempt):

        assert str(matching_attempt).startswith("Matching für")


# ── MatchingAttemptTransition ─────────────────────────────────────────────────

class TestMatchingAttemptTransition:

    def test_transition_creates_transition_record(self, matching_attempt):
        matching_attempt.transition_to(MatchingAttempt.Status.READY_FOR_MATCHING)

        transition = MatchingAttemptTransition.objects.get()

        assert transition.from_status == MatchingAttempt.Status.DRAFT
        assert transition.to_status == MatchingAttempt.Status.READY_FOR_MATCHING

    def test_invalid_triggered_by_raises(self, matching_attempt):

        with pytest.raises(ValueError):
            matching_attempt.transition_to(
                MatchingAttempt.Status.READY_FOR_MATCHING,
                triggered_by="alien"
            )

    def test_triggered_by_user_requires_staff_or_coach(self, matching_attempt, coach_user):

        with pytest.raises(ValueError):
            matching_attempt.transition_to(
                MatchingAttempt.Status.READY_FOR_MATCHING,
                triggered_by="system",
                triggered_by_user=coach_user
            )

    def test_transition_actor_constraint(self, matching_attempt, coach_user):
        with pytest.raises(IntegrityError):
            MatchingAttemptTransition.objects.create(
                matching_attempt=matching_attempt,
                from_status="draft",
                to_status="ready_for_matching",
                triggered_by="system",
                triggered_by_user=coach_user,
            )

    def test_invalid_transition_raises_validation_error(self, matching_attempt):
        with pytest.raises(ValidationError):
            matching_attempt.transition_to(MatchingAttempt.Status.MATCH_CONFIRMED)

    def test_transition_updates_status_on_instance(self, matching_attempt):
        updated = matching_attempt.transition_to(MatchingAttempt.Status.READY_FOR_MATCHING)

        assert updated.status == MatchingAttempt.Status.READY_FOR_MATCHING

    def test_staff_transition_records_user(self, matching_attempt, coach_user):
        matching_attempt.transition_to(
            MatchingAttempt.Status.READY_FOR_MATCHING,
            triggered_by="staff",
            triggered_by_user=coach_user,
        )

        transition = MatchingAttemptTransition.objects.get()
        assert transition.triggered_by == "staff"
        assert transition.triggered_by_user == coach_user

    def test_actor_constraint_staff_without_user(self, matching_attempt):
        with pytest.raises(IntegrityError):
            MatchingAttemptTransition.objects.create(
                matching_attempt=matching_attempt,
                from_status="draft",
                to_status="ready_for_matching",
                triggered_by="staff",
                triggered_by_user=None,
            )


# ── TestAutomationControl ─────────────────────────────────────────────────────

class TestAutomationControl:

    def test_enable_automation_sets_timestamp(self, matching_attempt):
        matching_attempt.status = MatchingAttempt.Status.MATCHING_ACTIVE
        matching_attempt.save()

        matching_attempt.enable_automation()

        assert matching_attempt.automation_enabled is True
        assert matching_attempt.automation_enabled_at is not None

    def test_disable_automation(self, matching_attempt):
        matching_attempt.status = MatchingAttempt.Status.MATCHING_ACTIVE
        matching_attempt.save()
        matching_attempt.enable_automation()

        matching_attempt.disable_automation()

        assert matching_attempt.automation_enabled is False

    def test_enable_automation_raises_in_disallowed_status(self, matching_attempt):
        matching_attempt.status = MatchingAttempt.Status.DRAFT
        matching_attempt.save()

        with pytest.raises(ValidationError):
            matching_attempt.enable_automation()

    def test_enable_automation_is_noop_if_already_enabled(self, matching_attempt):
        matching_attempt.status = MatchingAttempt.Status.MATCHING_ACTIVE
        matching_attempt.automation_enabled = True
        matching_attempt.save()

        matching_attempt.enable_automation()  # should not raise or create a second event

        assert MatchingAttemptEvent.objects.filter(
            matching_attempt=matching_attempt,
            event_type=MatchingAttemptEvent.EventType.AUTOMATION_ENABLED,
        ).count() == 0

    def test_automation_allowed_only_in_active_states(self, matching_attempt):
        matching_attempt.status = MatchingAttempt.Status.MATCH_CONFIRMED
        matching_attempt.save()

        with pytest.raises(ValidationError):
            matching_attempt.enable_automation()

    def test_automation_is_allowed_true_when_status_allows(self, matching_attempt):
        for status in (MatchingAttempt.Status.READY_FOR_MATCHING, MatchingAttempt.Status.MATCHING_ACTIVE):
            matching_attempt.status = status
            assert matching_attempt.automation_is_allowed is True

    def test_automation_is_allowed_false_when_wrong_status(self, matching_attempt):
        for status in (
            MatchingAttempt.Status.DRAFT,
            MatchingAttempt.Status.CHEMISTRY_PENDING,
            MatchingAttempt.Status.MATCH_CONFIRMED,
            MatchingAttempt.Status.FAILED,
            MatchingAttempt.Status.CANCELLED,
        ):
            matching_attempt.status = status
            assert matching_attempt.automation_is_allowed is False
