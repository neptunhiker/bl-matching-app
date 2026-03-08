import uuid
from django.db import models
from django.conf import settings


class EmailLog(models.Model):
    class Status(models.TextChoices):
        # Internal states (set by Django, not Brevo)
        SENT = 'sent', 'Gesendet'
        FAILED = 'failed', 'Fehlgeschlagen'
        # Brevo delivery events
        DELIVERED = 'delivered', 'Zugestellt'
        DEFERRED = 'deferred', 'Verzögert'
        SOFT_BOUNCED = 'soft_bounce', 'Soft Bounce'
        HARD_BOUNCED = 'hard_bounce', 'Hard Bounce'
        BLOCKED = 'blocked', 'Blockiert'
        INVALID = 'invalid', 'Ungültige E-Mail'
        ERROR = 'error', 'Fehler'
        SPAM = 'spam', 'Spam'
        UNSUBSCRIBED = 'unsubscribed', 'Abgemeldet'
        # Brevo engagement events
        OPENED = 'opened', 'Geöffnet'
        FIRST_OPENING = 'first_open', 'Erstöffnung'
        CLICKED = 'clicked', 'Geklickt'
        PROXY_OPEN = 'proxy_open', 'Proxy-Öffnung'
        UNIQUE_PROXY_OPEN = 'proxy_unique', 'Einmalige Proxy-Öffnung'
        
    class EmailTrigger(models.TextChoices):
        AUTOMATED = 'automtic', 'Automatisch'
        MANUAL = 'manual', 'Manuell'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    to = models.EmailField(verbose_name='Empfänger')
    subject = models.CharField(max_length=255, verbose_name='Betreff')
    html_body = models.TextField(verbose_name='HTML-Inhalt')
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.SENT,
        verbose_name='Status',
    )
    email_trigger = models.CharField(
        max_length=20,
        choices=EmailTrigger.choices,
        default=EmailTrigger.AUTOMATED,
        verbose_name='Typ (automatisch oder manuell)',
    )
    error_message = models.TextField(blank=True, verbose_name='Fehlermeldung')
    sent_at = models.DateTimeField(auto_now_add=True, verbose_name='Gesendet am')
    delivered_at = models.DateTimeField(null=True, blank=True, verbose_name='Zugestellt am')
    opened_at = models.DateTimeField(null=True, blank=True, verbose_name='Erstmals geöffnet am')
    sent_by = models.CharField(max_length=255, blank=True, verbose_name='Gesendet von')  # e.g. "User:123" or "System"
    request_to_coach = models.ForeignKey(
        'matching.RequestToCoach',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='email_logs',
        verbose_name='Anfrage an Coach',
    )
    matching_attempt = models.ForeignKey(
        'matching.MatchingAttempt',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='email_logs',
        verbose_name='Matching',
    )

    class Meta:
        ordering = ['-sent_at']
        verbose_name = 'E-Mail-Log'
        verbose_name_plural = 'E-Mail-Logs'
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(request_to_coach__isnull=True) |
                    models.Q(matching_attempt__isnull=True)
                ),
                name='emaillog_single_linked_object',
            )
        ]

    def __str__(self):
        return f"{self.subject} → {self.to} ({self.get_status_display()})"

