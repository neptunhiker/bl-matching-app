from django.core.management.base import BaseCommand
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.utils import timezone

from matching.models import RequestToCoach, MatchingAttempt
from matching.notifications import send_reminder_coach_request_email


class Command(BaseCommand):
    help = "Send reminder email to coaches for pending matching requests"

    MAX_PER_RUN = 5

    def handle(self, *args, **options):

        self.stdout.write("Starting coach reminder sender")

        reminders_sent = 0
        timed_out = 0
        skipped = 0
        failed = 0

        pending = (
            RequestToCoach.objects.filter(
                status=RequestToCoach.Status.AWAITING_REPLY,
                matching_attempt__automation_enabled=True,
                matching_attempt__status__in=[
                    MatchingAttempt.Status.READY_FOR_MATCHING,
                    MatchingAttempt.Status.MATCHING_ACTIVE,
                ],
            )
            .select_related("coach__user", "matching_attempt__participant")
            .order_by("deadline_at", "id")
        )[:self.MAX_PER_RUN]

        for rtc in pending.iterator():
            try:

                # Handle timeout
                if rtc.is_deadline_passed():

                    rtc.transition_to(
                        RequestToCoach.Status.NO_RESPONSE_UNTIL_DEADLINE
                    )

                    timed_out += 1

                    self.stdout.write(
                        self.style.WARNING(
                            f"Request {rtc.id} timed out for coach {rtc.coach_id}"
                        )
                    )

                    continue

                # Skip if reminder should not be sent
                if not rtc.can_send_reminder():
                    skipped += 1
                    continue

                send_reminder_coach_request_email(rtc)

                reminders_sent += 1

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Reminder sent for request {rtc.id} "
                        f"to coach {rtc.coach.user.email}"
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
                        f"Race condition prevented reminder for {rtc.id}: {exc}"
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
            f"Finished: {reminders_sent} reminders sent, "
            f"{timed_out} timed out, {skipped} skipped, {failed} failed"
        )