import uuid
from django.db import models
from django.conf import settings


class EmailLog(models.Model):
    class Status(models.TextChoices):
        SENT = 'sent', 'Gesendet'
        FAILED = 'failed', 'Fehlgeschlagen'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    to = models.EmailField(verbose_name='Empfänger')
    subject = models.CharField(max_length=255, verbose_name='Betreff')
    html_body = models.TextField(verbose_name='HTML-Inhalt')
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.SENT,
        verbose_name='Status',
    )
    error_message = models.TextField(blank=True, verbose_name='Fehlermeldung')
    sent_at = models.DateTimeField(auto_now_add=True, verbose_name='Gesendet am')
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='sent_emails',
        verbose_name='Gesendet von',
    )

    class Meta:
        ordering = ['-sent_at']
        verbose_name = 'E-Mail-Log'
        verbose_name_plural = 'E-Mail-Logs'

    def __str__(self):
        return f"{self.subject} → {self.to} ({self.get_status_display()})"
