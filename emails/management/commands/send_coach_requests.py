from django.core.management.base import BaseCommand
from django.utils import timezone

from emails.models import EmailLog
from matching.models import RequestToCoach
from matching.notifications import send_first_coach_request_email


class Command(BaseCommand):
    help = "Send first matching request email to coaches"

    def handle(self, *args, **options):
        pending = RequestToCoach.objects.filter(
            status=RequestToCoach.Status.IN_PREPARATION,
            first_sent_at__isnull=True,
        ).select_related('coach__user', 'matching_attempt__participant')

        if not pending.exists():
            return

        for coach_request in pending:
            self.stdout.write(
                f"Processing RequestToCoach {coach_request.id} "
                f"for Coach {coach_request.coach} "
                f"and MatchingAttempt {coach_request.matching_attempt}"
            )

            log = send_first_coach_request_email(request_to_coach=coach_request)

            if log.status == EmailLog.Status.FAILED:
                self.stderr.write(
                    self.style.ERROR(
                        f"Failed to send email for RequestToCoach {coach_request.id}: {log.error_message}"
                    )
                )
                continue

            now = timezone.now()
            coach_request.status = RequestToCoach.Status.AWAITING_REPLY
            coach_request.first_sent_at = now
            coach_request.last_sent_at = now
            coach_request.number_of_requests_sent += 1
            coach_request.save(update_fields=[
                'status', 'first_sent_at', 'last_sent_at', 'number_of_requests_sent'
            ])
            self.stdout.write(
                self.style.SUCCESS(
                    f"Sent email to Coach {coach_request.coach} for RequestToCoach {coach_request.id} "
                    f"— status → {coach_request.get_status_display()}"
                )
            )
            
            