from django.db import models
import uuid
# iomport user
from accounts.models import User

from profiles.models import Participant, Coach

# Create your models here.
class MatchingAttempt(models.Model):
    
    class Status(models.TextChoices):
        PENDING = 'in_prep', 'In Vorbereitung'
        AWAITING_PARTICIPANT_REPLY = 'awaiting_participant_reply', 'Warten auf TN-Antwort'
        AWAITING_COACH_REPLY = 'awaiting_coach_reply', 'Warten auf Coach-Antwort'
        MATCHED = 'matched', 'Matched'
        CANCELLED = 'cancelled', 'Matching abgebrochen'
    
    class ParticipantReply(models.TextChoices):
        ACCEPTED = 'accepted', 'Akzeptiert'
        REJECTED = 'rejected', 'Abgelehnt'
        PENDING = 'pending', 'Ausstehend'
        
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    participant = models.ForeignKey(Participant, on_delete=models.CASCADE, related_name='matching_attempts')
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='created_matching_attempts')
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.PENDING)
    matched_coach = models.ForeignKey(Coach, null=True, blank=True, on_delete=models.SET_NULL, related_name='matched_attempts')
    participant_status = models.CharField(max_length=10, choices=ParticipantReply.choices, default=ParticipantReply.PENDING)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Matching'
        verbose_name_plural = 'Matchings'
        
    def __str__(self):
        return f"Matching für {self.participant} - Status: {self.get_status_display()}"
    
class RequestToCoach(models.Model):
    
    class Status(models.TextChoices):
        IN_PREPARATION = 'in_preparation', 'In Vorbereitung'
        AWAITING_REPLY = 'awaiting_reply', 'Warten auf Antwort'
        ACCEPTED_ON_TIME = 'accepted_on_time', 'Akzeptiert (rechtzeitig)'
        ACCEPTED_LATE = 'accepted_late', 'Akzeptiert (verspätet)'
        REJECTED_ON_TIME = 'rejected_on_time', 'Abgelehnt (rechtzeitig)'
        REJECTED_LATE = 'rejected_late', 'Abgelehnt (verspätet)'
        NO_RESPONSE_UNTIL_DEADLINE = 'no_response_until_deadline', 'Keine Antwort bis zur Frist'
        CANCELLED = 'cancelled', 'Anfrage abgebrochen'
        
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    matching_attempt = models.ForeignKey(MatchingAttempt, on_delete=models.CASCADE, related_name='coach_requests')
    coach = models.ForeignKey(Coach, on_delete=models.CASCADE, related_name='coach_requests')
    created_at = models.DateTimeField(auto_now_add=True)
    number_of_requests_sent = models.PositiveIntegerField(default=0)
    max_number_of_requests = models.PositiveIntegerField(default=3)
    first_sent_at = models.DateTimeField(null=True, blank=True)
    last_sent_at = models.DateTimeField(null=True, blank=True)
    last_sent_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='sent_coach_requests')
    status = models.CharField(max_length=50, choices=Status.choices, default=Status.IN_PREPARATION)
    deadline = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Antwortfrist',
        help_text='Frist für rechtzeitige Antwort. Wird beim Versand automatisch vorausgefüllt (Wochenden werden übersprungen), kann aber manuell angepasst werden.',
    )

    def on_save(self, *args, **kwargs):
        # Hier könnte Logik implementiert werden, um die Anzahl der gesendeten Anfragen zu erhöhen und die Fristen zu setzen.
        super().save(*args, **kwargs)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Anfrage an Coach'
        verbose_name_plural = 'Anfragen an Coaches'
        
    def __str__(self):
        return f"Matching-Anfrage an {self.coach} für Coaching mit {self.matching_attempt.participant} - Status: {self.get_status_display()}"


class CoachActionToken(models.Model):
    """
    A one-time-use token that authorises a coach to accept or decline a
    RequestToCoach directly from an email link — no login required.

    One ACCEPT token and one DECLINE token are created each time a coach
    invitation email is sent (initial send + every reminder).  Old tokens
    from earlier emails remain valid so the coach can use any email they
    received.

    The view that handles the URL must:
      1. Look up the token (invalid link if not found).
      2. Call consume_token() — shows "already responded" if used_at is set.
      3. Check request_to_coach.status for a terminal state — shows
         "already responded" if the coach replied via a different email's token.
      4. Compare now() against request_to_coach.deadline to decide
         ACCEPTED_ON_TIME vs ACCEPTED_LATE (or REJECTED_*).
    """

    class Action(models.TextChoices):
        ACCEPT = 'accept', 'Annehmen'
        DECLINE = 'decline', 'Ablehnen'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    token = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        verbose_name='Token',
        help_text='URL-safe random string generated by secrets.token_urlsafe(48).',
    )
    request_to_coach = models.ForeignKey(
        RequestToCoach,
        on_delete=models.CASCADE,
        related_name='action_tokens',
        verbose_name='Anfrage an Coach',
    )
    action = models.CharField(
        max_length=10,
        choices=Action.choices,
        verbose_name='Aktion',
        help_text='Baked in at creation — cannot change after the token is issued.',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Erstellt am')
    used_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Verwendet am',
        help_text='None = not yet clicked. Set atomically by consume_token() on first use.',
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Coach-Aktions-Token'
        verbose_name_plural = 'Coach-Aktions-Tokens'

    def __str__(self):
        used = 'verwendet' if self.used_at else 'offen'
        return (
            f"{self.get_action_display()}-Token für "
            f"{self.request_to_coach} ({used})"
        )