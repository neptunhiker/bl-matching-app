from django.core.management.base import BaseCommand
from django.utils import timezone

from matching.models import RequestToCoach, MatchingAttempt

class Command(BaseCommand):
    help = "Handle expired coach requests"

    def handle(self, *args, **options):
        now = timezone.now()

        self.stdout.write("Starting to handle expired coach requests")

        attempts = MatchingAttempt.objects.filter(
            coach_requests__status=RequestToCoach.Status.AWAITING_REPLY,
            coach_requests__deadline_at__lt=now,
        ).distinct()

        for attempt in attempts:
            attempt.handle_expired_requests()