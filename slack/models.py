import uuid
from django.db import models
from django.conf import settings

from profiles.models import Coach

import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class SlackLog(models.Model):

    class Status(models.TextChoices):
        SENT = 'sent', 'Gesendet'
        FAILED = 'failed', 'Fehlgeschlagen'

    class SentBy(models.TextChoices):
        SYSTEM = 'System', 'System'
        STAFF = 'Staff', 'Mitarbeiter:in'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="received_slack_logs",
        verbose_name="Empfänger:in",
    )

    subject = models.CharField(max_length=255, verbose_name='Betreff')
    message = models.TextField(blank=True, verbose_name='Nachricht')

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.SENT,
        verbose_name='Status',
    )

    error_message = models.TextField(blank=True, verbose_name='Fehlermeldung')

    sent_at = models.DateTimeField(auto_now_add=True, verbose_name='Gesendet am')

    sent_by = models.CharField(
        max_length=20,
        choices=SentBy.choices,
        default=SentBy.SYSTEM,
        verbose_name='Gesendet von',
    )

    sent_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='sent_slack_logs',
        verbose_name='Gesendet von (User)',
    )

    request_to_coach = models.ForeignKey(
        "matching.RequestToCoach",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='slack_logs',
        verbose_name='Matching-Anfrage an Coach',
    )

    matching_attempt = models.ForeignKey(
        "matching.MatchingAttempt",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='slack_logs',
        verbose_name='Matching',
    )

    # -------------------------
    # 🔑 CORE LOGIC (NEW)
    # -------------------------


    def clean(self):

        # Enforce exactly one linked object (XOR)
        if bool(self.request_to_coach) == bool(self.matching_attempt):
            raise ValidationError(
                "Exactly one of request_to_coach or matching_attempt must be set."
            )

    def save(self, *args, **kwargs):
        self.full_clean()  # 👈 ensures clean() runs every time
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['-sent_at']
        verbose_name = 'Slack-Log'
        verbose_name_plural = 'Slack-Logs'

        constraints = [
            # XOR constraint (fixed!)
            models.CheckConstraint(
            condition=(
                # at most one is set
                ~(
                    models.Q(request_to_coach__isnull=False) &
                    models.Q(matching_attempt__isnull=False)
                )
            ),
            name='slacklog_at_most_one_linked_object',
        ),

            # Sender consistency
            models.CheckConstraint(
                condition=(
                    (models.Q(sent_by="System") & models.Q(sent_by_user__isnull=True)) |
                    (models.Q(sent_by="Staff") & models.Q(sent_by_user__isnull=False))
                ),
                name='slacklog_sent_by_user_consistency',
            ),
        ]

    def __str__(self):
        return f"{self.message} → {self.to} ({self.get_status_display()})"

