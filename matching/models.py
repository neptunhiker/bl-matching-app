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
    
    