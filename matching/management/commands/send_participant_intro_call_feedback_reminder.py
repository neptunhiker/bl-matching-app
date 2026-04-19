import logging

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from matching.models import MatchingAttempt, MatchingEvent, TriggeredByOptions
from matching.utils import get_standard_extension_deadline
from matching.services import create_matching_event

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Send a one-time reminder to participants who have not responded to the "
        "intro call feedback request by their deadline. Extends the deadline by one "
        "working day. Safe to run as a cron job: automation guard and event-based "
        "deduplication prevent double-sending."
    )

    MAX_PER_RUN = 10

    def handle(self, *args, **options):
        verbosity = options["verbosity"]

        pending = list(
            MatchingAttempt.objects
            .eligible_for_participant_intro_call_feedback_reminder()
            .select_related("matched_coach__user", "participant")
            .order_by("participant_intro_call_feedback_deadline_at")
            [:self.MAX_PER_RUN]
        )

        if verbosity >= 1:
            self.stdout.write(
                f"Found {len(pending)} attempt(s) eligible for a participant intro call feedback reminder."
            )

        sent = 0
        failed = 0

        for attempt in pending:
            try:
                with transaction.atomic():
                    attempt.participant_intro_call_feedback_deadline_at = get_standard_extension_deadline(
                        timezone.now()
                    )
                    attempt.save(update_fields=["participant_intro_call_feedback_deadline_at"])

                    create_matching_event(
                        matching_attempt=attempt,
                        event_type=MatchingEvent.EventType.INTRO_CALL_FEEDBACK_REMINDER_SENT_TO_PARTICIPANT,
                        triggered_by=TriggeredByOptions.SYSTEM,
                        triggered_by_user=None,
                        payload={
                            "deadline_at": attempt.participant_intro_call_feedback_deadline_at.isoformat()
                        },
                    )
                sent += 1
                if verbosity >= 2:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Reminder queued for attempt {attempt.id} "
                            f"(participant: {attempt.participant}, "
                            f"new deadline: {attempt.participant_intro_call_feedback_deadline_at})"
                        )
                    )
            except Exception as exc:
                failed += 1
                logger.exception(
                    "Error sending participant intro call feedback reminder for attempt %s", attempt.id
                )
                self.stderr.write(
                    self.style.ERROR(f"Error processing attempt {attempt.id}: {exc}")
                )

        self.stdout.write(f"Finished: {sent} reminder(s) queued, {failed} failed.")
