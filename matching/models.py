import uuid
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone


from accounts.models import User
from profiles.models import Participant, Coach





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
        IN_PREPARATION = "in_preparation", "In Vorbereitung"
        AWAITING_REPLY = "awaiting_reply", "Warten auf Antwort"
        ACCEPTED_ON_TIME = "accepted_on_time", "Akzeptiert (rechtzeitig)"
        ACCEPTED_LATE = "accepted_late", "Akzeptiert (verspätet)"
        REJECTED_ON_TIME = "rejected_on_time", "Abgelehnt (rechtzeitig)"
        REJECTED_LATE = "rejected_late", "Abgelehnt (verspätet)"
        NO_RESPONSE_UNTIL_DEADLINE = "no_response_until_deadline", "Keine Antwort bis zur Frist"
        CANCELLED = "cancelled", "Anfrage abgebrochen"

    # Immutable transition map
    ALLOWED_COACH_REQUEST_TRANSITIONS = {

        Status.IN_PREPARATION: frozenset({
            Status.AWAITING_REPLY,
            Status.CANCELLED,
        }),

        Status.AWAITING_REPLY: frozenset({
            Status.ACCEPTED_ON_TIME,
            Status.ACCEPTED_LATE,
            Status.REJECTED_ON_TIME,
            Status.REJECTED_LATE,
            Status.NO_RESPONSE_UNTIL_DEADLINE,
            Status.CANCELLED,
        }),

        Status.ACCEPTED_ON_TIME: frozenset({
            Status.CANCELLED,
        }),

        Status.ACCEPTED_LATE: frozenset({
            Status.CANCELLED,
        }),

        Status.REJECTED_ON_TIME: frozenset({
            Status.CANCELLED,
        }),

        Status.REJECTED_LATE: frozenset({
            Status.CANCELLED,
        }),

        Status.NO_RESPONSE_UNTIL_DEADLINE: frozenset({
            Status.CANCELLED,
        }),
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    matching_attempt = models.ForeignKey(
        "MatchingAttempt",
        on_delete=models.CASCADE,
        related_name="coach_requests",
    )

    coach = models.ForeignKey(
        "profiles.Coach",
        on_delete=models.CASCADE,
        related_name="coach_requests",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    requests_sent = models.PositiveIntegerField(default=0)
    max_number_of_requests = models.PositiveIntegerField(default=3)

    first_sent_at = models.DateTimeField(null=True, blank=True)
    last_sent_at = models.DateTimeField(null=True, blank=True)

    responded_at = models.DateTimeField(null=True, blank=True)

    status = models.CharField(
        max_length=50,
        choices=Status.choices,
        default=Status.IN_PREPARATION,
        db_index=True,
    )

    deadline_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Antwortfrist",
        help_text="Frist für rechtzeitige Antwort. Wird beim Versand automatisch vorausgefüllt (Wochenenden werden übersprungen), kann aber manuell angepasst werden.",
    )

    # ------------------------------------------------------------------
    # State Machine Helpers
    # ------------------------------------------------------------------

    @property
    def allowed_transitions(self):
        """Return allowed next states."""
        return self.ALLOWED_COACH_REQUEST_TRANSITIONS.get(self.status, frozenset())

    def can_send_request(self):
        return self.requests_sent < self.max_number_of_requests
    
    def can_send_reminder(self):
        return (
            self.status == self.Status.AWAITING_REPLY
            and not self.is_deadline_passed()
            and self.can_send_request()
            and self.first_sent_at is not None
        )

    def can_transition_to(self, new_status):
        """Check if transition is allowed."""
        return new_status in self.allowed_transitions

    def _validate_transition(self, new_status):
        """Ensure transition is valid."""
        if not self.can_transition_to(new_status):
            raise ValidationError(
                f"Transition {self.status} → {new_status} not allowed."
            )

    # ------------------------------------------------------------------
    # Transition Method
    # ------------------------------------------------------------------

    @transaction.atomic
    def transition_to(self, new_status, triggered_by="system", note=None) -> "RequestToCoach":
        """
        Perform a validated state transition and log it.
        """
        from .notifications import _get_locked_request

        locked = _get_locked_request(self)

        locked._validate_transition(new_status)

        old_status = locked.status
        locked.status = new_status
        locked.save(update_fields=["status"])

        RequestToCoachTransition.objects.create(
            request=locked,
            from_status=old_status,
            to_status=new_status,
            triggered_by=triggered_by,
            note=note,
        )

        return locked

    # ------------------------------------------------------------------
    # Convenience Helpers
    # ------------------------------------------------------------------

    def is_deadline_passed(self):
        if not self.deadline_at:
            return False
        return timezone.now() > self.deadline_at

    def mark_responded(self):
        """Record response timestamp."""
        RequestToCoach.objects.filter(
            pk=self.pk,
            responded_at__isnull=True
        ).update(responded_at=timezone.now())
            
    # ------------------------------------------------------------------
    # Domain Actions
    # ------------------------------------------------------------------
    
    
    def accept(self, triggered_by="coach") -> "RequestToCoach":

        if self.status != self.Status.AWAITING_REPLY:
            raise ValidationError("Cannot accept request in this state")

        now = timezone.now()

        if self.deadline_at and now > self.deadline_at:
            new_status = self.Status.ACCEPTED_LATE
        else:
            new_status = self.Status.ACCEPTED_ON_TIME

        updated_rtc = self.transition_to(new_status, triggered_by=triggered_by)
        
        updated_rtc.mark_responded()
        
        RequestToCoachEvent.objects.create(
            request=updated_rtc,
            event_type=RequestToCoachEvent.EventType.ACCEPTED,
            triggered_by=triggered_by,
        )
        
        return updated_rtc
        
    def reject(self, triggered_by: str = "coach") -> "RequestToCoach":

        if self.status != self.Status.AWAITING_REPLY:
            raise ValidationError("Cannot reject request in this state")

        now = timezone.now()

        if self.deadline_at and now > self.deadline_at:
            new_status = self.Status.REJECTED_LATE
        else:
            new_status = self.Status.REJECTED_ON_TIME

        updated_rtc = self.transition_to(new_status, triggered_by=triggered_by)
        
        updated_rtc.mark_responded()
        
        RequestToCoachEvent.objects.create(
            request=updated_rtc,
            event_type=RequestToCoachEvent.EventType.REJECTED,
            triggered_by=triggered_by,
        )

        return updated_rtc

    # ------------------------------------------------------------------
    # Django Metadata
    # ------------------------------------------------------------------

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Anfrage an Coach"
        verbose_name_plural = "Anfragen an Coaches"

        constraints = [
            models.UniqueConstraint(
                fields=["matching_attempt", "coach"],
                name="unique_coach_request_per_matching_attempt",
            )
        ]

    # ------------------------------------------------------------------
    # Representation
    # ------------------------------------------------------------------

    def __str__(self):
        return (
            f"Matching-Anfrage an {self.coach} "
            f"für Coaching mit {self.matching_attempt.participant} "
            f"- Status: {self.get_status_display()}"
        )
    

class RequestToCoachTransition(models.Model):

    request = models.ForeignKey(
        RequestToCoach,
        on_delete=models.CASCADE,
        related_name="transitions"
    )

    from_status = models.CharField(max_length=50, choices=RequestToCoach.Status.choices)
    to_status = models.CharField(max_length=50, choices=RequestToCoach.Status.choices)

    triggered_by = models.CharField(
        max_length=20,
        choices=[
            ("system", "System"),
            ("staff", "BL Mitarbeiter:in"),
            ("coach", "Coach"),
        ],
    )

    created_at = models.DateTimeField(auto_now_add=True)

    note = models.TextField(blank=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.from_status} → {self.to_status} ({self.triggered_by})"


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
        
        indexes = [
            models.Index(fields=["request_to_coach", "used_at"]),
        ]

    def __str__(self):
        used = 'verwendet' if self.used_at else 'offen'
        return (
            f"{self.get_action_display()}-Token für "
            f"{self.request_to_coach} ({used})"
        )
        
        
class RequestToCoachEvent(models.Model):

    class EventType(models.TextChoices):
        REQUEST_SENT = "request_sent", "Request sent"
        REMINDER_SENT = "reminder_sent", "Reminder sent"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"

    request = models.ForeignKey(
        "RequestToCoach",
        on_delete=models.CASCADE,
        related_name="events",
    )

    event_type = models.CharField(
        max_length=30,
        choices=EventType.choices,
    )

    triggered_by = models.CharField(
        max_length=20,
        choices=[
            ("system", "System"),
            ("staff", "BL Mitarbeiter:in"),
            ("coach", "Coach"),
        ],
    )

    created_at = models.DateTimeField(auto_now_add=True)

    note = models.TextField(blank=True)

    class Meta:
        ordering = ["created_at"]
     
        indexes = [
           models.Index(fields=["request", "created_at"]),
        ]

    def __str__(self):
        return f"{self.event_type} ({self.triggered_by})"