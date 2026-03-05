from django.core.management.base import BaseCommand
from django.utils import timezone

from emails.models import EmailLog
from matching.models import RequestToCoach
from matching.notifications import send_reminder_coach_request_email

MAX_NUMBER_OF_REQUESTS = 3

class Command(BaseCommand):
    help = "Send reminder email to coaches for pending matching requests"

    def handle(self, *args, **options):
        pending = RequestToCoach.objects.filter(
            status=RequestToCoach.Status.AWAITING_REPLY,
            first_sent_at__isnull=False,
            number_of_requests_sent__lt=MAX_NUMBER_OF_REQUESTS,
        ).select_related('coach__user', 'matching_attempt__participant')

        if not pending.exists():
            return

        for coach_request in pending:
            now = timezone.now()
            deadline = coach_request.deadline
            if now > deadline:
                coach_request.status = RequestToCoach.Status.NO_RESPONSE_UNTIL_DEADLINE
                coach_request.save(update_fields=['status'])
                self.stdout.write(
                    self.style.WARNING(
                        f"RequestToCoach {coach_request.id} has passed the deadline without response. "
                        f"Status updated to 'No Response Until Deadline'."
                    )
                )
                continue
            
            time_since_last_reminder = now - coach_request.last_sent_at
            # Only send a reminder if at least 2 minutes have passed since the last reminder
            if time_since_last_reminder < timezone.timedelta(minutes=2):
                self.stdout.write(
                    f"Skipping RequestToCoach {coach_request.id} for Coach {coach_request.coach} "
                    f"— last reminder sent {time_since_last_reminder.seconds} seconds ago."
                )
                continue
                
            # Otherwise, send a reminder email
            log = send_reminder_coach_request_email(request_to_coach=coach_request)

            if log.status == EmailLog.Status.FAILED:
                self.stderr.write(
                    self.style.ERROR(
                        f"Failed to send reminder email for RequestToCoach {coach_request.id}: {log.error_message}"
                    )
                )
                continue

            coach_request.last_sent_at = timezone.now()
            coach_request.number_of_requests_sent += 1
            coach_request.save(update_fields=['last_sent_at', 'number_of_requests_sent'])
            self.stdout.write(
                self.style.SUCCESS(
                    f"Sent reminder email to Coach {coach_request.coach} for RequestToCoach {coach_request.id} "
                    f"— total reminders sent: {coach_request.number_of_requests_sent}"
                )
            )