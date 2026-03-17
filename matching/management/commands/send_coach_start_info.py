from django.core.management.base import BaseCommand
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from matching.models import MatchingAttempt
from matching.notifications import send_coaching_start_info_notification


class Command(BaseCommand):
    help = "Send info about coaching start to coach and participant"

    MAX_PER_RUN = 5

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS(
                f"We are getting started with the coaching start info"
            )
        )
                
                
        sent = 0
        skipped = 0
        failed = 0

        pending = (
            MatchingAttempt.objects
                .eligible_for_start_info_notification()
                .select_related("matched_coach__user", "participant")
                .order_by("participant__start_date")
        )[:self.MAX_PER_RUN]

        for ma in pending.iterator():
            try:
                # Ensure any select_for_update inside the send routine runs
                # within a transaction (required by Django).
                with transaction.atomic():
                    send_coaching_start_info_notification(ma, triggered_by="system", triggered_by_user=None)

                sent += 1

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Sent coaching start info to coach {ma.matched_coach} and participant {ma.participant}."
                    )
                )

            except ValidationError as exc:
                skipped += 1

                self.stderr.write(
                    self.style.WARNING(
                        f"Skipped MatchingAttempt {ma.id}: {exc}"
                    )
                )

            except IntegrityError as exc:
                skipped += 1

                self.stderr.write(
                    self.style.WARNING(
                        f"Race condition prevented sending for {ma.id}: {exc}"
                    )
                )

            except Exception as exc:
                failed += 1

                self.stderr.write(
                    self.style.ERROR(
                        f"Error processing MatchingAttempt {ma.id}: {exc}"
                    )
                )

        self.stdout.write(
            f"Finished: {sent} sent, {skipped} skipped, {failed} failed"
        )
