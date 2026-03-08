from django.core.management.base import BaseCommand
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.utils import timezone

from matching.models import RequestToCoach, MatchingAttempt
from matching.notifications import send_first_coach_request_email


class Command(BaseCommand):
    help = "Send first matching request email to coaches"

    MAX_PER_RUN = 5

    def handle(self, *args, **options):

        self.stdout.write(f"Starting coach request sender at {timezone.now()}")

        sent = 0
        skipped = 0
        failed = 0

        pending = (
            RequestToCoach.objects.filter(
                status=RequestToCoach.Status.IN_PREPARATION,
                first_sent_at__isnull=True,
                matching_attempt__automation_enabled=True,
                matching_attempt__status__in=[
                    MatchingAttempt.Status.READY_FOR_MATCHING,
                    MatchingAttempt.Status.MATCHING_ACTIVE,
                ],
            )
            .select_related("coach__user", "matching_attempt__participant")
            .order_by("matching_attempt_id", "priority", "id")
        )[:self.MAX_PER_RUN]

        for rtc in pending.iterator():
            try:
                send_first_coach_request_email(rtc)

                sent += 1

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Sent request {rtc.id} "
                        f"to coach {rtc.coach.user.email} "
                        f"for attempt {rtc.matching_attempt_id}"
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
