import logging

from django.core.management.base import BaseCommand
from django.db import transaction

from matching.models import MatchingAttempt, MatchingEvent, TriggeredByOptions
from matching.services import create_matching_event

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Notify BL staff via Slack when a participant has not responded to the "
        "intro call feedback request even after receiving a reminder. Staff should "
        "follow up directly with the participant. Safe to run as a cron job: "
        "automation guard and event-based deduplication prevent double-sending."
    )

    MAX_PER_RUN = 10

    def handle(self, *args, **options):
        verbosity = options["verbosity"]

        pending = list(
            MatchingAttempt.objects
            .eligible_for_participant_intro_call_feedback_staff_escalation()
            .select_related("matched_coach__user", "participant", "bl_contact")
            .order_by("participant_intro_call_feedback_deadline_at")
            [:self.MAX_PER_RUN]
        )

        if verbosity >= 1:
            self.stdout.write(
                f"Found {len(pending)} attempt(s) eligible for participant feedback staff escalation."
            )

        sent = 0
        failed = 0

        for attempt in pending:
            try:
                with transaction.atomic():
                    create_matching_event(
                        matching_attempt=attempt,
                        event_type=MatchingEvent.EventType.INTRO_CALL_FEEDBACK_PARTICIPANT_TIMED_OUT_STAFF_NOTIFIED,
                        triggered_by=TriggeredByOptions.SYSTEM,
                        triggered_by_user=None,
                    )
                sent += 1
                if verbosity >= 2:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Staff escalation queued for attempt {attempt.id} "
                            f"(participant: {attempt.participant}, coach: {attempt.matched_coach})"
                        )
                    )
            except Exception as exc:
                failed += 1
                logger.exception(
                    "Error sending participant feedback staff escalation for attempt %s", attempt.id
                )
                self.stderr.write(
                    self.style.ERROR(f"Error processing attempt {attempt.id}: {exc}")
                )

        self.stdout.write(f"Finished: {sent} escalation(s) queued, {failed} failed.")
