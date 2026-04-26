import logging

from django.core.management.base import BaseCommand
from django.db import transaction

from matching.models import RequestToCoach, TriggeredByOptions

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Send a one-time reminder to coaches whose request-to-coach is still "
        "awaiting reply and whose deadline is within 2 hours. "
        "Safe to run as a cron job: automation guard and event-based "
        "deduplication prevent double-sending."
    )

    MAX_PER_RUN = 10

    def handle(self, *args, **options):
        verbosity = options["verbosity"]

        pending = (
            RequestToCoach.objects
            .eligible_for_reminder()
            .select_related("coach", "matching_attempt__participant")
            .order_by("deadline_at")
        )[:self.MAX_PER_RUN]

        if verbosity >= 1:
            self.stdout.write(f"Found {len(pending)} coach request(s) eligible for a reminder.")

        sent = 0
        failed = 0

        for rtc in pending:
            try:
                with transaction.atomic():
                    rtc.send_reminder(
                        triggered_by=TriggeredByOptions.SYSTEM,
                        triggered_by_user=None,
                    )
                sent += 1
                if verbosity >= 2:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Reminder queued for RTC {rtc.id} "
                            f"(coach: {rtc.coach}, deadline: {rtc.deadline_at})"
                        )
                    )
            except Exception as exc:
                failed += 1
                logger.exception("Error sending reminder for RTC %s", rtc.id)
                self.stderr.write(
                    self.style.ERROR(f"Error processing RTC {rtc.id}: {exc}")
                )

        self.stdout.write(f"Finished: {sent} reminder(s) queued, {failed} failed.")
