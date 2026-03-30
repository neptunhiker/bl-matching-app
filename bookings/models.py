import uuid
from django.db import models


class CalendlyBooking(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    # Calendly identifiers
    calendly_event_uri = models.URLField(max_length=500, blank=True)
    calendly_invitee_uri = models.URLField(max_length=500, unique=True)
    calendly_event_uuid = models.CharField(max_length=100, blank=True)

    # Core info
    invitee_first_name = models.CharField(max_length=255, blank=True)
    invitee_last_name = models.CharField(max_length=255, blank=True)
    invitee_name = models.CharField(max_length=255, blank=True)
    invitee_email = models.EmailField(blank=True, db_index=True)
    timezone = models.CharField(max_length=100, blank=True)

    # Event info
    event_name = models.CharField(max_length=255, blank=True)
    event_type = models.CharField(max_length=255, blank=True)

    # Time
    start_time = models.DateTimeField(null=True, blank=True, db_index=True)
    end_time = models.DateTimeField(null=True, blank=True)

    # Status
    status = models.CharField(max_length=50, default="active", db_index=True)

    # Custom answers
    questions_and_answers = models.JSONField(default=list, blank=True)

    # Debug / safety
    raw_payload = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @staticmethod
    def extract_uuid_from_uri(uri: str):
        if not uri:
            return ""
        return uri.rstrip("/").split("/")[-1]

    def save(self, *args, **kwargs):
        if self.calendly_event_uri and not self.calendly_event_uuid:
            self.calendly_event_uuid = self.extract_uuid_from_uri(self.calendly_event_uri)
        super().save(*args, **kwargs)
        
    class Meta:
        verbose_name = "Calendly Buchung"
        verbose_name_plural = "Calendly Buchungen"
        ordering = ["-created_at"]

    def __str__(self):
        full_name = f"{self.invitee_first_name} {self.invitee_last_name}".strip()
        return f"{full_name or self.invitee_email} - {self.start_time}"