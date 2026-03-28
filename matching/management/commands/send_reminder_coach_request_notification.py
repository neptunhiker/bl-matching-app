import logging

from django.core.management.base import BaseCommand
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from matching.models import RequestToCoach, TriggeredByOptions
from matching.notifications import send_reminder_request_notification
from profiles.models import Coach

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Send reminder matching request notification to coaches"

    MAX_PER_RUN = 5

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS(
                f"We are getting started with reminders"
            )
        )
                
                
        sent = 0
        skipped = 0
        failed = 0

        pending = (
            RequestToCoach.objects
                .eligible_for_reminder()
                .select_related("coach__user", "matching_attempt__participant")
                .order_by("matching_attempt_id", "priority", "id")
        )[:self.MAX_PER_RUN]
        
        self.stdout.write(
            self.style.SUCCESS(
                f"Pending reminders: {pending.count()}"
            )
        )

        for rtc in pending.iterator():
            try:
                rtc.send_reminder(triggered_by=TriggeredByOptions.SYSTEM, triggered_by_user=None)

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Sent request {rtc.id} "
                        f"to coach {rtc.coach.user} "
                        f"for matching '{rtc.matching_attempt}'"
                    )
                )

            except ValidationError as exc:
                skipped += 1

                self.stderr.write(
                    self.style.WARNING(
                        f"Skipped RequestToCoach {rtc.id}: {exc}"
                    )
                )

            except IntegrityError as exc:
                skipped += 1

                self.stderr.write(
                    self.style.WARNING(
                        f"Race condition prevented sending for {rtc.id}: {exc}"
                    )
                )

            except Exception as exc:
                failed += 1

                self.stderr.write(
                    self.style.ERROR(
                        f"Error processing RequestToCoach {rtc.id}: {exc}"
                    )
                )

        self.stdout.write(
            f"Finished: {sent} sent, {skipped} skipped, {failed} failed"
        )
