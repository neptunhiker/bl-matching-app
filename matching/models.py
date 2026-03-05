from datetime import timedelta

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
    
    @property
    def deadline(self):
        if self.first_sent_at:
            return self.first_sent_at + timedelta(hours=24)
        return None
    
    def on_save(self, *args, **kwargs):
        # Hier könnte Logik implementiert werden, um die Anzahl der gesendeten Anfragen zu erhöhen und die Fristen zu setzen.
        super().save(*args, **kwargs)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Anfrage an Coach'
        verbose_name_plural = 'Anfragen an Coaches'
        
    def __str__(self):
        return f"Matching-Anfrage an {self.coach} für Coaching mit {self.matching_attempt.participant} - Status: {self.get_status_display()}"