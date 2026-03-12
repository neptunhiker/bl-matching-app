from django.core.management.base import BaseCommand
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from matching.models import RequestToCoach
from matching.notifications import send_reminder_coach_request_email


class Command(BaseCommand):
    help = "Send reminder emails to coaches"

    MAX_PER_RUN = 5

    def handle(self, *args, **options):

        self.stdout.write("Sending coach reminders")

        reminders_sent = 0
        skipped = 0
        failed = 0

        qs = (
            RequestToCoach.objects.eligible_for_reminder()
            .select_related("coach__user", "matching_attempt__participant")
            .order_by("deadline_at", "id")
        )[:self.MAX_PER_RUN]

        for rtc in qs.iterator():
            try:
                send_reminder_coach_request_email(rtc)

                reminders_sent += 1

            except ValidationError:
                skipped += 1

            except IntegrityError:
                skipped += 1

            except Exception as exc:
                failed += 1
                self.stderr.write(
                    self.style.ERROR(f"Error for {rtc.id}: {exc}")
                )

        self.stdout.write(
            f"Finished: {reminders_sent} reminders sent, "
            f"{skipped} skipped, {failed} failed"
        )