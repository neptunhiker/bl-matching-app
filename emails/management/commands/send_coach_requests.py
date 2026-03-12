from django.core.management.base import BaseCommand
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.utils import timezone

from emails.models import EmailLog
from matching.models import RequestToCoach, MatchingAttempt
from matching.notifications import send_first_coach_request_email


class Command(BaseCommand):
    help = "Send first matching request email to coaches"

    MAX_PER_RUN = 5

    def handle(self, *args, **options):

        sent = 0
        skipped = 0
        failed = 0

        pending = (
            RequestToCoach.objects
                .eligible_for_first_request()
                .select_related("coach__user", "matching_attempt__participant")
                .order_by("matching_attempt_id", "priority", "id")
        )[:self.MAX_PER_RUN]

        for rtc in pending.iterator():
            try:
                send_first_coach_request_email(rtc, email_trigger=EmailLog.EmailTrigger.AUTOMATED)

                sent += 1

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Sent request {rtc.id} "
                        f"to coach {rtc.coach.user.email} "
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
