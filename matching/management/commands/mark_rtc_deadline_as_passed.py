import logging
from django.utils import timezone

from django.core.management.base import BaseCommand
from django.db import transaction

from matching.models import MatchingAttempt, RequestToCoach, TriggeredByOptions, MatchingEvent
from matching import services

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Mark overdue coach requests as timed out and advance the matching queue"

    MAX_PER_RUN = 5

    def handle(self, *args, **options):
        now = timezone.now()
        verbosity = options["verbosity"]

        overdue = (
            RequestToCoach.objects
            .filter(
                state=RequestToCoach.State.AWAITING_REPLY,
                deadline_at__lt=now,
                matching_attempt__automation_enabled=True,
                matching_attempt__state=MatchingAttempt.State.AWAITING_RTC_REPLY,
            )
            .select_related("matching_attempt", "coach")
            .order_by("deadline_at")
        )[:self.MAX_PER_RUN]

        if verbosity >= 1:
            self.stdout.write(f"Found {overdue.count()} overdue coach request(s) to process.")

        marked = 0
        failed = 0

        for rtc in overdue:
            try:
                with transaction.atomic():
                    rtc.mark_deadline_as_passed()
                    rtc.save()
                    services.create_matching_event(
                        matching_attempt=rtc.matching_attempt,
                        event_type=MatchingEvent.EventType.RTC_TIMED_OUT,
                        triggered_by=TriggeredByOptions.SYSTEM,
                        payload={
                            "rtc_id": str(rtc.id),
                            "coach": str(rtc.coach) if rtc.coach is not None else None,
                            "deadline_at": rtc.deadline_at.isoformat(),
                        }
                    )
                marked += 1
                if verbosity >= 2:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Marked RTC {rtc.id} (coach: {rtc.coach}) as timed out."
                        )
                    )
            except Exception as exc:
                failed += 1
                logger.exception("Error processing RTC %s", rtc.id)
                self.stderr.write(
                    self.style.ERROR(f"Error processing RTC {rtc.id}: {exc}")
                )

        self.stdout.write(
            f"Finished: {marked} marked as timed out, {failed} failed."
        )