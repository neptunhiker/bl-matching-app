import uuid
from django.db import models
from django.conf import settings

from matching.models import RequestToCoach, MatchingAttempt
from profiles.models import Coach

class SlackLog(models.Model):
    class Status(models.TextChoices):
        SENT = 'sent', 'Gesendet'
        FAILED = 'failed', 'Fehlgeschlagen'
        
    class SentBy(models.TextChoices):
        SYSTEM = 'System', 'System'
        STAFF = 'Staff', 'Mitarbeiter:in'
        
    class SlackTrigger(models.TextChoices):
        AUTOMATED = 'automatic', 'Automatisch'
        MANUAL = 'manual', 'Manuell'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    to = models.ForeignKey(Coach, on_delete=models.CASCADE, related_name='slack_logs', verbose_name='Coach', help_text="An Coach")
    subject = models.CharField(max_length=255, verbose_name='Betreff')
    message = models.TextField(verbose_name='Nachricht')
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.SENT,
        verbose_name='Status',
    )
    slack_trigger = models.CharField(
        max_length=20,
        choices=SlackTrigger.choices,
        default=SlackTrigger.AUTOMATED,
        verbose_name='Typ (automatisch oder manuell)',
    )
    error_message = models.TextField(blank=True, verbose_name='Fehlermeldung')
    sent_at = models.DateTimeField(auto_now_add=True, verbose_name='Gesendet am')
    sent_by = models.CharField(max_length=255, blank=True, verbose_name='Gesendet von')  # e.g. "User:123" or "System"
    sent_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='sent_slack_logs',
        verbose_name='Gesendet von',
    )
    request_to_coach = models.ForeignKey(
        RequestToCoach,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='slack_logs',
        verbose_name='Matching-Anfrage an Coach',
    )
    matching_attempt = models.ForeignKey(
        MatchingAttempt,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='slack_logs',
        verbose_name='Matching',
    )

    class Meta:
        ordering = ['-sent_at']
        verbose_name = 'Slack-Log'
        verbose_name_plural = 'Slack-Logs'
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(request_to_coach__isnull=True) |
                    models.Q(matching_attempt__isnull=True)
                ),
                name='slacklog_single_linked_object',
            ),
                # if sent by is System, sent_by_user must be null, if sent by Staff, sent_by_user must not be null
                models.CheckConstraint(
                    condition=(
                        (models.Q(sent_by="system") & models.Q(sent_by_user__isnull=True)) |
                        (models.Q(sent_by="staff") & models.Q(sent_by_user__isnull=False))
                    ),
                    name='slacklog_sent_by_user_consistency',
                ),
        ]

    def __str__(self):
        return f"{self.message} → {self.to} ({self.get_status_display()})"

