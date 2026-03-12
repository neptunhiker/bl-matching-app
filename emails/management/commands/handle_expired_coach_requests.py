from django.core.management.base import BaseCommand
from django.utils import timezone

from matching.models import RequestToCoach


class Command(BaseCommand):
    help = "Expire RequestToCoach records whose deadline has passed"

    MAX_PER_RUN = 20

    def handle(self, *args, **options):

        self.stdout.write("Processing request timeouts")

        now = timezone.now()
        expired = 0
        failed = 0

        qs = (
            RequestToCoach.objects.filter(
                status=RequestToCoach.Status.AWAITING_REPLY,
                deadline_at__lt=now,
            )
            .order_by("deadline_at", "id")
        )[:self.MAX_PER_RUN]

        for rtc in qs.iterator():
            try:
                rtc.mark_deadline_passed()
                expired += 1

            except Exception as exc:
                failed += 1
                self.stderr.write(
                    self.style.ERROR(f"Failed to expire {rtc.id}: {exc}")
                )

        self.stdout.write(
            f"Finished: {expired} expired, {failed} failed"
        )