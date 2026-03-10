from typing import List
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from accounts.models import User
from .locks import _get_locked_matching_attempt
from profiles.models import Participant, Coach


class MatchingAttempt(models.Model):

    class Status(models.TextChoices):
        IN_PREPARATION = "in_preparation", "In Vorbereitung"
        READY_FOR_MATCHING = "ready_for_matching", "Bereit für Matching"
        MATCHING_ONGOING= "matching_ongoing", "Matching läuft"
        MATCHING_CONFIRMED = "matching_confirmed", "Matching bestätigt"
        FAILED = "failed", "Kein Coach gefunden"
        CANCELLED = "cancelled", "Matching abgebrochen"

    ACTIVE_MATCHING_ATTEMPT_STATUSES = frozenset({
        Status.IN_PREPARATION,
        Status.READY_FOR_MATCHING,
        Status.MATCHING_ONGOING,
    })

    ALLOWED_TRANSITIONS = {

        Status.IN_PREPARATION: frozenset({
            Status.READY_FOR_MATCHING,
            Status.CANCELLED,
        }),

        Status.READY_FOR_MATCHING: frozenset({
            Status.MATCHING_ONGOING,
            Status.CANCELLED,
        }),

        Status.MATCHING_ONGOING: frozenset({
            Status.FAILED,
            Status.CANCELLED,
        }),

        Status.MATCHING_CONFIRMED: frozenset(),

        Status.FAILED: frozenset(),

        Status.CANCELLED: frozenset(),
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    participant = models.ForeignKey(
        Participant,
        on_delete=models.CASCADE,
        related_name="matching_attempts",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    created_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_matching_attempts",
    )

    status = models.CharField(
        max_length=50,
        choices=Status.choices,
        default=Status.IN_PREPARATION,
        db_index=True,
    )

    # automation

    automation_enabled = models.BooleanField(
        default=False,
        help_text="Automatisches Versenden von Coach-Anfragen und Erinnerungen."
    )

    automation_enabled_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    @property
    def automation_is_allowed(self):
        return self.status in {
            self.Status.READY_FOR_MATCHING,
            self.Status.MATCHING_ONGOING,
        }

    # match outcome

    matched_coach = models.ForeignKey(
        Coach,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="successful_matches",
    )

    # chemistry phase

    chemistry_requested_at = models.DateTimeField(null=True, blank=True)

    chemistry_deadline_at = models.DateTimeField(null=True, blank=True)

    chemistry_confirmed_at = models.DateTimeField(null=True, blank=True)

    chemistry_declined_at = models.DateTimeField(null=True, blank=True)

    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:

        ordering = ["-created_at"]

        constraints = [
            models.UniqueConstraint(
                fields=["participant"],
                condition=Q(
                    status__in=[
                        "in_preparation",
                        "ready_for_matching",
                        "matching_ongoing",
                    ]
                ),
                name="unique_ongoing_matching_attempt_per_participant",
            )
        ]

        indexes = [
            models.Index(fields=["participant", "created_at"]),
        ]

    # -------------------------------------------------------
    # state machine helpers
    # -------------------------------------------------------

    @property
    def allowed_transitions(self):
        return self.ALLOWED_TRANSITIONS.get(self.status, frozenset())

    @property
    def is_active(self):
        return self.status in self.ACTIVE_MATCHING_ATTEMPT_STATUSES

    def can_transition_to(self, new_status):
        return new_status in self.allowed_transitions

    def _validate_transition(self, new_status):
        if not self.can_transition_to(new_status):
            raise ValidationError(
                f"Transition {self.status} → {new_status} not allowed."
            )

    @transaction.atomic
    def transition_to(
        self,
        new_status,
        triggered_by="system",
        triggered_by_user: User = None
    ):

        if triggered_by not in ["system", "staff", "coach"]:
            raise ValueError("Invalid triggered_by")

        if triggered_by_user and triggered_by == "system":
            raise ValueError("System transitions cannot specify triggered_by_user")

        if triggered_by == "staff" and triggered_by_user is not None:
            if not (triggered_by_user.is_staff or triggered_by_user.is_superuser):
                raise ValidationError(
                    "triggered_by_user must be a staff member or superuser when triggered_by is 'staff'."
                )

        locked = _get_locked_matching_attempt(self)

        locked._validate_transition(new_status)

        old_status = locked.status
        locked.status = new_status
        locked.save(update_fields=["status"])

        MatchingAttemptTransition.objects.create(
            matching_attempt=locked,
            from_status=old_status,
            to_status=new_status,
            triggered_by=triggered_by,
            triggered_by_user=triggered_by_user,
        )

        return locked

    # -------------------------------------------------------
    # automation control
    # -------------------------------------------------------

    def enable_automation(self, triggered_by_user: User):

        if self.automation_enabled:
            return

        if not self.automation_is_allowed:
            raise ValidationError("Automation cannot be enabled in the current status.")

        self.automation_enabled = True
        self.automation_enabled_at = timezone.now()

        self.save(update_fields=["automation_enabled", "automation_enabled_at"])

        MatchingAttemptEvent.objects.create(
            matching_attempt=self,
            event_type=MatchingAttemptEvent.EventType.AUTOMATION_ENABLED,
            triggered_by=MatchingAttemptEvent.TriggeredBy.STAFF,
            triggered_by_user=triggered_by_user,
        )

    def disable_automation(self, triggered_by_user: User):

        if not self.automation_enabled:
            return

        self.automation_enabled = False
        self.save(update_fields=["automation_enabled"])

        MatchingAttemptEvent.objects.create(
            matching_attempt=self,
            event_type=MatchingAttemptEvent.EventType.AUTOMATION_DISABLED,
            triggered_by=MatchingAttemptEvent.TriggeredBy.STAFF,
            triggered_by_user=triggered_by_user,
        )

    # -------------------------------------------------------
    # domain actions
    # -------------------------------------------------------

    @transaction.atomic
    def start_matching(self, triggered_by_user: User):

        updated = self.transition_to(
            self.Status.READY_FOR_MATCHING,
            triggered_by="staff",
            triggered_by_user=triggered_by_user,
        )

        MatchingAttemptEvent.objects.create(
            matching_attempt=updated,
            event_type=MatchingAttemptEvent.EventType.STARTED,
            triggered_by=MatchingAttemptEvent.TriggeredBy.STAFF,
            triggered_by_user=triggered_by_user,
        )

        # Keep the current in-memory instance in sync with the DB-updated
        # instance so callers that don't use the returned object observe the
        # new status.
        self.status = updated.status

        return updated

    # -------------------------------------------------------
    # queue helpers
    # -------------------------------------------------------

    def get_active_requests(self) -> List["RequestToCoach"]:
        return list(
            self.coach_requests.filter(
                status=RequestToCoach.Status.AWAITING_REPLY
            )
        )

    def get_next_request(self):

        return (
            self.coach_requests
            .filter(status=RequestToCoach.Status.IN_PREPARATION)
            .order_by("priority")
            .first()
        )

    def has_remaining_requests(self):

        return self.coach_requests.filter(
            status=RequestToCoach.Status.IN_PREPARATION
        ).exists()

    # -------------------------------------------------------

    def on_save(self, *args, **kwargs):
        from . import MatchingAttemptEvent
        
        super().on_save(*args, **kwargs)
        print("Is this being called when a new MatchingAttempt is created?")
        # if created
        if not self.pk:
            MatchingAttemptEvent.objects.create(
                matching_attempt=self,
                event_type=MatchingAttemptEvent.EventType.CREATED,
                triggered_by=MatchingAttemptEvent.TriggeredBy.SYSTEM,
            )
                
        
    def __str__(self):
        return (
            f"Matching für {self.participant} "
            f"- Status: {self.get_status_display()}"
        )
        
class MatchingAttemptTransition(models.Model):

    matching_attempt = models.ForeignKey(
        "MatchingAttempt",
        on_delete=models.CASCADE,
        related_name="transitions",
    )

    from_status = models.CharField(
        max_length=50,
        choices=MatchingAttempt.Status.choices,
    )

    to_status = models.CharField(
        max_length=50,
        choices=MatchingAttempt.Status.choices,
    )

    triggered_by = models.CharField(
        max_length=20,
        choices=[
            ("system", "System"),
            ("staff", "BL Mitarbeiter:in"),
            ("coach", "Coach"),
        ],
    )

    triggered_by_user = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text="Required if triggered_by is 'staff' or 'coach'.",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    note = models.TextField(
        blank=True,
        help_text="Optional explanation for manual or exceptional transitions.",
    )

    class Meta:

        ordering = ["created_at"]

        indexes = [
            models.Index(fields=["matching_attempt", "created_at"]),
        ]

        constraints = [

            # ensure actor consistency
            models.CheckConstraint(
                condition=(
                    Q(triggered_by="system", triggered_by_user__isnull=True)
                    |
                    Q(triggered_by__in=["staff", "coach"], triggered_by_user__isnull=False)
                ),
                name="matching_attempt_transition_actor_consistency",
            ),

            # prevent pointless transitions
            models.CheckConstraint(
                condition=~Q(from_status=models.F("to_status")),
                name="matching_attempt_transition_status_change",
            ),
        ]

    def clean(self):
        if self.triggered_by == "system" and self.triggered_by_user:
            raise ValidationError(
                "triggered_by_user must be empty when triggered_by is 'system'."
            )

        if self.triggered_by in {"staff", "coach"} and not self.triggered_by_user:
            raise ValidationError(
                "triggered_by_user must be set when triggered_by is 'staff' or 'coach'."
            )

        if self.triggered_by == "staff" and self.triggered_by_user:
            if not (self.triggered_by_user.is_staff or self.triggered_by_user.is_superuser):
                raise ValidationError(
                    "triggered_by_user must be a staff member or superuser when triggered_by is 'staff'."
                )

    def __str__(self):
        return f"{self.from_status} → {self.to_status} ({self.triggered_by})"
        

class MatchingAttemptEvent(models.Model):

    class EventType(models.TextChoices):

        # Lebenszyklus
        CREATED = "created", "Matching erstellt"
        STARTED = "started", "Matching gestartet"

        # Automatisierung
        AUTOMATION_ENABLED = "automation_enabled", "Automatisierung aktiviert"
        AUTOMATION_DISABLED = "automation_disabled", "Automatisierung deaktiviert"
        AUTOMATION_RUN = "automation_run", "Automatisierung ausgeführt"

        # Coach-Anfrage
        COACH_REQUEST_SENT = "coach_request_sent", "Coach-Anfrage versendet"

        # Antworten des Coaches
        COACH_ACCEPTED = "coach_accepted", "Coach hat akzeptiert"
        COACH_DECLINED = "coach_declined", "Coach hat abgelehnt"

        # Verspätete Antworten
        COACH_ACCEPTED_LATE = "coach_accepted_late", "Coach hat verspätet akzeptiert"
        COACH_DECLINED_LATE = "coach_declined_late", "Coach hat verspätet abgelehnt"

        # Ignorierte Antworten
        COACH_RESPONSE_IGNORED = "coach_response_ignored", "Coach-Antwort ignoriert"

        # Fristen
        REQUEST_DEADLINE_PASSED = "request_deadline_passed", "Antwortfrist des Coaches abgelaufen"

        # Chemiegespräch
        CHEMISTRY_CALL_REQUESTED = "chemistry_call_requested", "Chemiegespräch angefragt"
        CHEMISTRY_CALL_CONFIRMED = "chemistry_call_confirmed", "Chemiegespräch bestätigt"
        CHEMISTRY_CALL_DECLINED = "chemistry_call_declined", "Chemiegespräch abgelehnt"

        # Chemie-Fristen
        CHEMISTRY_CONFIRMATION_DEADLINE_PASSED = (
            "chemistry_confirmation_deadline_passed",
            "Frist zur Bestätigung des Chemiegesprächs abgelaufen",
        )
        CHEMISTRY_CALL_TIMEOUT = "chemistry_call_timeout", "Chemiegespräch-Frist überschritten"

        # Erinnerungen
        REMINDER_SENT = "reminder_sent", "Erinnerung versendet"

        # Manuelle Aktionen
        MANUAL_OVERRIDE = "manual_override", "Manuelle Entscheidung durch Mitarbeiter"
        STAFF_CANCELLED_REQUESTS = "staff_cancelled_requests", "Coach-Anfragen durch Mitarbeiter abgebrochen"

    matching_attempt = models.ForeignKey(
        "MatchingAttempt",
        on_delete=models.CASCADE,
        related_name="events",
    )

    coach = models.ForeignKey(
        Coach,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text="Coach, auf den sich das Ereignis bezieht (falls zutreffend)",
    )

    event_type = models.CharField(
        max_length=64,
        choices=EventType.choices,
    )

    class TriggeredBy(models.TextChoices):
        SYSTEM = "system", "System"
        STAFF = "staff", "BL Mitarbeiter:in"
        COACH = "coach", "Coach"

    # New canonical actor fields (align with RequestToCoachEvent)
    triggered_by = models.CharField(
        max_length=20,
        choices=TriggeredBy.choices,
        default=TriggeredBy.SYSTEM,
    )

    triggered_by_user = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text="Benutzer, der das Ereignis ausgelöst hat (nur bei staff oder coach)",
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Zusätzliche strukturierte Informationen zum Ereignis",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(triggered_by="system", triggered_by_user__isnull=True)
                    |
                    models.Q(triggered_by__in=["staff", "coach"], triggered_by_user__isnull=False)
                ),
                name="matching_attempt_event_valid_triggered_by_user",
            )
        ]

    def __str__(self):
        return f"{self.matching_attempt_id} - {self.get_event_type_display()} - {self.created_at}"

    def clean(self):
        if self.triggered_by == self.TriggeredBy.SYSTEM and self.triggered_by_user:
            raise ValidationError(
                "triggered_by_user must be empty when triggered_by is 'system'."
            )

        if self.triggered_by in {self.TriggeredBy.STAFF, self.TriggeredBy.COACH} and not self.triggered_by_user:
            raise ValidationError(
                "triggered_by_user must be set when triggered_by is 'staff' or 'coach'."
            )

        if self.triggered_by == self.TriggeredBy.STAFF and self.triggered_by_user:
            if not (self.triggered_by_user.is_staff or self.triggered_by_user.is_superuser):
                raise ValidationError(
                    "triggered_by_user must be a staff member or superuser when triggered_by is 'staff'."
                )
    
class RequestToCoach(models.Model):

    class Status(models.TextChoices):
        IN_PREPARATION = "in_preparation", "In Vorbereitung"
        AWAITING_REPLY = "awaiting_reply", "Warten auf Antwort"
        ACCEPTED_ON_TIME = "accepted_on_time", "Akzeptiert (rechtzeitig)"
        ACCEPTED_LATE = "accepted_late", "Akzeptiert (verspätet)"
        REJECTED_ON_TIME = "rejected_on_time", "Abgelehnt (rechtzeitig)"
        REJECTED_LATE = "rejected_late", "Abgelehnt (verspätet)"
        NO_RESPONSE_UNTIL_DEADLINE = "no_response_until_deadline", "Keine Rückmeldung"
        CANCELLED = "cancelled", "Anfrage abgebrochen"

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

    priority = models.PositiveIntegerField(
        help_text="Kleiner Wert = höhere Priorität."
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
        help_text="Frist für rechtzeitige Antwort",
    )

    # -------------------------------------------------------------
    # State Machine Helpers
    # -------------------------------------------------------------

    @property
    def allowed_transitions(self):
        return self.ALLOWED_COACH_REQUEST_TRANSITIONS.get(self.status, frozenset())

    def can_send_request(self):
        return (
            self.status == self.Status.IN_PREPARATION and self.requests_sent < 1
        )

    def can_send_reminder(self):
        return (
            self.status == self.Status.AWAITING_REPLY
            and not self.is_deadline_passed()
            and self.requests_sent < self.max_number_of_requests
            and self.requests_sent > 0
            and self.first_sent_at is not None
        )

    def can_transition_to(self, new_status):
        return new_status in self.allowed_transitions

    def _validate_transition(self, new_status):
        if not self.can_transition_to(new_status):
            raise ValidationError(
                f"Transition {self.status} → {new_status} not allowed."
            )

    # -------------------------------------------------------------
    # Transition Method
    # -------------------------------------------------------------

    @transaction.atomic
    def transition_to(self, new_status, triggered_by="system", triggered_by_user: User = None):

        from .locks import _get_locked_request_to_coach

        if triggered_by not in ["system", "staff", "coach"]:
            raise ValueError("triggered_by must be 'system', 'staff', or 'coach'")

        if triggered_by_user and triggered_by not in ["staff", "coach"]:
            raise ValueError("triggered_by_user only allowed for staff or coach")

        if triggered_by == "staff" and triggered_by_user is not None:
            if not (triggered_by_user.is_staff or triggered_by_user.is_superuser):
                raise ValidationError(
                    "triggered_by_user must be a staff member or superuser when triggered_by is 'staff'."
                )

        locked = _get_locked_request_to_coach(self)

        locked._validate_transition(new_status)

        old_status = locked.status
        locked.status = new_status
        locked.save(update_fields=["status"])

        RequestToCoachTransition.objects.create(
            request=locked,
            from_status=old_status,
            to_status=new_status,
            triggered_by=triggered_by,
            triggered_by_user=triggered_by_user,
        )

        return locked

    # -------------------------------------------------------------
    # Convenience Helpers
    # -------------------------------------------------------------

    def is_deadline_passed(self):
        if not self.deadline_at:
            return False
        return timezone.now() > self.deadline_at

    def mark_responded(self):
        RequestToCoach.objects.filter(
            pk=self.pk,
            responded_at__isnull=True
        ).update(responded_at=timezone.now())

    # -------------------------------------------------------------
    # Domain Actions
    # -------------------------------------------------------------

    def send_request(self):

        if not self.can_send_request():
            raise ValidationError("Maximum number of requests reached")

        now = timezone.now()

        if self.first_sent_at is None:
            self.first_sent_at = now

        self.last_sent_at = now
        self.requests_sent += 1

        if self.status == self.Status.IN_PREPARATION:
            self.transition_to(self.Status.AWAITING_REPLY)

        self.save(update_fields=[
            "first_sent_at",
            "last_sent_at",
            "requests_sent",
        ])

        RequestToCoachEvent.objects.create(
            request=self,
            event_type=RequestToCoachEvent.EventType.REQUEST_SENT,
            triggered_by=RequestToCoachEvent.TriggeredBy.SYSTEM,
        )

    def send_reminder(self):

        if not self.can_send_reminder():
            raise ValidationError("Reminder cannot be sent")

        self.last_sent_at = timezone.now()
        self.requests_sent += 1

        self.save(update_fields=["last_sent_at", "requests_sent"])

        RequestToCoachEvent.objects.create(
            request=self,
            event_type=RequestToCoachEvent.EventType.REMINDER_SENT,
            triggered_by=RequestToCoachEvent.TriggeredBy.SYSTEM,
        )

    def mark_deadline_passed(self):

        if self.status != self.Status.AWAITING_REPLY:
            return

        if not self.is_deadline_passed():
            return

        updated = self.transition_to(self.Status.NO_RESPONSE_UNTIL_DEADLINE)

        RequestToCoachEvent.objects.create(
            request=updated,
            event_type=RequestToCoachEvent.EventType.TIMED_OUT,
            triggered_by=RequestToCoachEvent.TriggeredBy.SYSTEM,
        )

    def accept(self, triggered_by="coach", triggered_by_user=None):

        if self.status != self.Status.AWAITING_REPLY:
            raise ValidationError("Cannot accept request in this state")

        if triggered_by == "coach" and triggered_by_user is None:
            triggered_by_user = self.coach.user

        now = timezone.now()

        if self.deadline_at and now > self.deadline_at:
            new_status = self.Status.ACCEPTED_LATE
        else:
            new_status = self.Status.ACCEPTED_ON_TIME

        updated = self.transition_to(new_status, triggered_by=triggered_by, triggered_by_user=triggered_by_user)

        updated.mark_responded()

        RequestToCoachEvent.objects.create(
            request=updated,
            event_type=RequestToCoachEvent.EventType.ACCEPTED,
            triggered_by=triggered_by,
            triggered_by_user=triggered_by_user,
        )

        return updated

    def reject(self, triggered_by="coach", triggered_by_user=None):

        if self.status != self.Status.AWAITING_REPLY:
            raise ValidationError("Cannot reject request in this state")

        if triggered_by == "coach" and triggered_by_user is None:
            triggered_by_user = self.coach.user

        now = timezone.now()

        if self.deadline_at and now > self.deadline_at:
            new_status = self.Status.REJECTED_LATE
        else:
            new_status = self.Status.REJECTED_ON_TIME

        updated = self.transition_to(new_status, triggered_by=triggered_by, triggered_by_user=triggered_by_user)

        updated.mark_responded()

        RequestToCoachEvent.objects.create(
            request=updated,
            event_type=RequestToCoachEvent.EventType.REJECTED,
            triggered_by=triggered_by,
            triggered_by_user=triggered_by_user,
        )

        return updated

    # -------------------------------------------------------------
    # Django Metadata
    # -------------------------------------------------------------

    class Meta:
        ordering = ["priority"]
        verbose_name = "Matching-Anfrage an Coach"
        verbose_name_plural = "Matching-Anfragen an Coaches"

        constraints = [
            models.UniqueConstraint(
                fields=["matching_attempt", "coach"],
                name="unique_coach_per_matching_attempt",
            ),
            models.UniqueConstraint(
                fields=["matching_attempt", "priority"],
                name="unique_priority_for_requests_to_coaches",
            ),
            models.UniqueConstraint(
                fields=["matching_attempt"],
                condition=Q(status="awaiting_reply"),
                name="one_request_awaiting_reply_per_attempt",
            ),
        ]

        indexes = [
            models.Index(fields=["matching_attempt", "status"])
        ]

    def __str__(self):
        return (
            f"Matching-Anfrage an {self.coach} "
            f"für Coaching mit {self.matching_attempt.participant} "
            f"- Status: {self.get_status_display()}"
        )

class RequestToCoachTransition(models.Model):

    class TriggeredBy(models.TextChoices):
        SYSTEM = "system", "System"
        STAFF = "staff", "BL Mitarbeiter:in"
        COACH = "coach", "Coach"

    request = models.ForeignKey(
        RequestToCoach,
        on_delete=models.CASCADE,
        related_name="transitions",
    )

    from_status = models.CharField(
        max_length=50,
        choices=RequestToCoach.Status.choices,
        db_index=True,
    )

    to_status = models.CharField(
        max_length=50,
        choices=RequestToCoach.Status.choices,
        db_index=True,
    )

    triggered_by = models.CharField(
        max_length=20,
        choices=TriggeredBy.choices,
    )

    triggered_by_user = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text="Benutzer, der die Transition ausgelöst hat (nur bei staff oder coach)",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    note = models.TextField(
        blank=True,
        help_text="Optionaler Kommentar zur Transition (z.B. Begründung bei manuellen Eingriffen)",
    )

    class Meta:
        ordering = ["created_at"]

        indexes = [
            models.Index(fields=["request", "created_at"]),
            models.Index(fields=["from_status"]),
            models.Index(fields=["to_status"]),
        ]

        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(triggered_by="system", triggered_by_user__isnull=True)
                    |
                    models.Q(triggered_by__in=["staff", "coach"], triggered_by_user__isnull=False)
                ),
                name="rtc_transition_valid_triggered_by_user",
            )
        ]

    def clean(self):
        """
        Application-level validation for clearer error messages.
        """
        if self.triggered_by == self.TriggeredBy.SYSTEM and self.triggered_by_user:
            raise ValidationError(
                "triggered_by_user must be empty when triggered_by is 'system'."
            )

        if self.triggered_by in {self.TriggeredBy.STAFF, self.TriggeredBy.COACH} and not self.triggered_by_user:
            raise ValidationError(
                "triggered_by_user must be set when triggered_by is 'staff' or 'coach'."
            )

        if self.triggered_by == self.TriggeredBy.STAFF and self.triggered_by_user:
            if not (self.triggered_by_user.is_staff or self.triggered_by_user.is_superuser):
                raise ValidationError(
                    "triggered_by_user must be a staff member or superuser when triggered_by is 'staff'."
                )

    def __str__(self):
        return (
            f"Request {self.request_id}: "
            f"{self.from_status} → {self.to_status} "
            f"({self.get_triggered_by_display()})"
        )


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
        CREATED = "created", "Matching-Anfrage erstellt"
        REQUEST_SENT = "request_sent", "Matching-Anfrage gesendet"
        REMINDER_SENT = "reminder_sent", "Reminder gesendet"
        ACCEPTED = "accepted", "Matching-Anfrage akzeptiert"
        REJECTED = "rejected", "Matching-Anfrage abgelehnt"
        TIMED_OUT = "timed_out", "Deadline überschritten"
        CANCELLED = "cancelled", "Abgebrochen"

    class TriggeredBy(models.TextChoices):
        SYSTEM = "system", "System"
        STAFF = "staff", "BL Mitarbeiter:in"
        COACH = "coach", "Coach"

    request = models.ForeignKey(
        "RequestToCoach",
        on_delete=models.CASCADE,
        related_name="events",
    )

    event_type = models.CharField(
        max_length=30,
        choices=EventType.choices,
        db_index=True,
    )

    triggered_by = models.CharField(
        max_length=20,
        choices=TriggeredBy.choices,
    )

    triggered_by_user = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text="Benutzer, der das Ereignis ausgelöst hat (nur bei staff oder coach)",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    note = models.TextField(
        blank=True,
        help_text="Optionaler Kommentar zum Ereignis"
    )

    metadata = models.JSONField(
        blank=True,
        default=dict,
        help_text="Zusätzliche strukturierte Informationen (z.B. Reminder-Typ, Deadline, etc.)",
    )

    class Meta:
        ordering = ["created_at"]

        indexes = [
            models.Index(fields=["request", "created_at"]),
            models.Index(fields=["event_type"]),
        ]

        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(triggered_by="system", triggered_by_user__isnull=True)
                    |
                    models.Q(triggered_by__in=["staff", "coach"], triggered_by_user__isnull=False)
                ),
                name="rtc_event_valid_triggered_by_user",
            )
        ]

    def clean(self):
        """
        Application-level validation to provide better error messages.
        """
        if self.triggered_by == self.TriggeredBy.SYSTEM and self.triggered_by_user:
            raise ValidationError(
                "triggered_by_user must be empty when triggered_by is 'system'."
            )

        if self.triggered_by in {self.TriggeredBy.STAFF, self.TriggeredBy.COACH} and not self.triggered_by_user:
            raise ValidationError(
                "triggered_by_user must be set when triggered_by is 'staff' or 'coach'."
            )

        if self.triggered_by == self.TriggeredBy.STAFF and self.triggered_by_user:
            if not (self.triggered_by_user.is_staff or self.triggered_by_user.is_superuser):
                raise ValidationError(
                    "triggered_by_user must be a staff member or superuser when triggered_by is 'staff'."
                )

    def __str__(self):
        return (
            f"Request {self.request_id}: "
            f"{self.get_event_type_display()} "
            f"({self.get_triggered_by_display()})"
        )


# Ensure that deleting a user does not leave events in a state that violates
# the check constraint (triggered_by in {staff,coach} requires a user).
# Before a User is deleted, set related event rows to be SYSTEM-triggered
# and clear the user reference so the DB constraint remains satisfied.
@receiver(pre_delete, sender=User)
def _nullify_user_on_related_events(sender, instance, using, **kwargs):
    MatchingAttemptEvent.objects.filter(triggered_by_user=instance).update(
        triggered_by=MatchingAttemptEvent.TriggeredBy.SYSTEM,
        triggered_by_user=None,
    )

    RequestToCoachEvent.objects.filter(triggered_by_user=instance).update(
        triggered_by=RequestToCoachEvent.TriggeredBy.SYSTEM,
        triggered_by_user=None,
    )