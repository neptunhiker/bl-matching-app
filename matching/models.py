from typing import List
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from django_fsm import FSMField, transition

from accounts.models import User
from .locks import _get_locked_matching_attempt
from .utils import add_business_hours
from profiles.models import Participant, Coach


class MatchingAttemptQuerySet(models.QuerySet):

    def eligible_for_intro_call_request(self):
        return self.filter(
            status=MatchingAttempt.Status.READY_FOR_INTRO_CALL,
            intro_call_requested_at__isnull=True,
            automation_enabled=True,
            matched_coach__status__in=[
                Coach.Status.AVAILABLE,
            ]
        )
        
    def eligible_for_start_info_notification(self):
        return self.filter(
            status=MatchingAttempt.Status.READY_FOR_START_EMAIL,
            coaching_start_info_sent_at__isnull=True,
            automation_enabled=True,
        )

class MatchingAttempt(models.Model):

    class State(models.TextChoices):
        IN_PREPARATION = "in_preparation", "In Vorbereitung"
        READY_FOR_FIRST_COACH_REQUEST= "ready_for_first_coach_request", "Bereit für erste Coach-Anfrage"
        AWAITING_RTC_REPLY = "awaiting_rtc_reply", "Warten auf Coach-Antwort zu Matching-Anfrage"
        READY_FOR_INTRO_CALL_REQUEST = "ready_for_intro_call_request", "Bereit für Intro-Call Anfrage"
        AWAITING_INTRO_CALL_REPLY = "awaiting_intro_call_reply", "Warten auf Coach-Antwort zu Intro-Call Anfrage"
        READY_FOR_START_NOTIFICATION = "ready_for_start_notification", "Bereit für Coaching-Start-Benachrichtigung"
        MATCHING_COMPLETED = "matching_completed", "Matching abgeschlossen"
        FAILED = "failed", "Kein Coach gefunden"
        CANCELLED = "cancelled", "Matching abgebrochen"
        
    class Status(models.TextChoices):
        IN_PREPARATION = "in_preparation", "In Vorbereitung"
        READY_FOR_MATCHING = "ready_for_matching", "Bereit für Matching"
        MATCHING_ONGOING= "matching_ongoing", "Matching läuft"
        MATCHING_CONFIRMED = "matching_confirmed", "Matching bestätigt"
        READY_FOR_INTRO_CALL = "ready_for_intro_call", "Bereit für Intro-Call"
        AWAITING_INTRO_CALL_FEEDBACK = "awaiting_intro_call_feedback", "Warten auf Intro-Call Rückmeldung"
        INTRO_CALL_CONFIRMED = "intro_call_confirmed", "Intro-Call bestätigt"
        READY_FOR_START_EMAIL = "ready_for_start_email", "Bereit für Start-E-Mail"
        MATCHING_COMPLETED = "matching_completed", "Matching abgeschlossen"
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
            Status.MATCHING_CONFIRMED,
            Status.FAILED,
            Status.CANCELLED,
        }),

        Status.MATCHING_CONFIRMED: frozenset({
            Status.READY_FOR_INTRO_CALL,
            Status.FAILED,
            Status.CANCELLED,
        }),
        
        Status.READY_FOR_INTRO_CALL: frozenset({
            Status.AWAITING_INTRO_CALL_FEEDBACK,
            Status.FAILED,
            Status.CANCELLED,
        }),
        
        Status.AWAITING_INTRO_CALL_FEEDBACK: frozenset({
            Status.INTRO_CALL_CONFIRMED,
            Status.FAILED,
            Status.CANCELLED,
        }),
        
        Status.INTRO_CALL_CONFIRMED: frozenset({
            Status.READY_FOR_START_EMAIL,
            Status.FAILED,
            Status.CANCELLED,
        }),
        
        Status.READY_FOR_START_EMAIL: frozenset({
            Status.MATCHING_COMPLETED,
            Status.FAILED,
            Status.CANCELLED,
        }),

        Status.FAILED: frozenset(),

        Status.CANCELLED: frozenset(),
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    participant = models.ForeignKey(
        Participant,
        on_delete=models.CASCADE,
        related_name="matching_attempts",
        verbose_name="Teilnehmer:in",
    )
    
    ue = models.PositiveIntegerField(
        help_text='Anzahl der genehmigten Unterrichtseinheiten.', 
        verbose_name='Unterrichtseinheiten')

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
    
    state = FSMField(
        choices=State.choices,
        default=Status.IN_PREPARATION,
        protected=True,
        db_index=True,
    )
    

    # automation
    automation_enabled = models.BooleanField(
        default=False,
        help_text="Automatisches Versenden von Coach-Anfragen und Erinnerungen."
    )

    @property
    def automation_is_allowed(self):
        return self.status in {
            self.Status.IN_PREPARATION,
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
    
    intro_call_requested_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Zeitpunkt, zu dem der Coach erstmals gebeten wurde, einen Intro-Call mit dem(r) Teilnehmer:in zu organisieren."
    )
    
    intro_call_confirmed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Zeitpunkt, zu dem der Coach das Intro-Gespräch bestätigt hat."
    )

    intro_call_info_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Zeitpunkt, zu dem der/die Teilnehmer:in und der Coach Infos für ein Kennenlerngespräch (Intro-Call) erhalten haben."
    )
    
    coaching_start_info_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Zeitpunkt, zu dem der/die Teilnehmer:in und der Coach eine Info zum Start des Coachings erhalten haben."
    )
    
    cancelled_at = models.DateTimeField(null=True, blank=True)
    
    objects = MatchingAttemptQuerySet.as_manager()

    class Meta:

        ordering = ["-created_at"]
        verbose_name = "Matching"
        verbose_name_plural = "Matchings"

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
    def transition_to(self, new_status):
        """
        Transition the MatchingAttempt to a new status and record the transition.
        """

        from .locks import _get_locked_request_to_coach

        locked = _get_locked_matching_attempt(self)

        locked._validate_transition(new_status)

        old_status = locked.status
        locked.status = new_status
        locked.save(update_fields=["status"])

        # record transition
        MatchingAttemptTransition.objects.create(
            matching_attempt=locked,
            from_status=old_status,
            to_status=new_status,
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

        self.save(update_fields=["automation_enabled"])

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

    def _validate_start_matching(self, triggered_by_user: User):
        if self.status != self.Status.IN_PREPARATION:
            raise ValidationError("Matching attempt is not in preparation.")
        
        if not self.coach_requests.filter(status=RequestToCoach.Status.IN_PREPARATION).exists():
            raise ValidationError("At least one coach request must be in preparation to start matching.")
        
        if not triggered_by_user.is_staff and not triggered_by_user.is_superuser:
            raise ValidationError("Only staff members can start the matching process.")
        
    @transaction.atomic
    def start_matching(self, triggered_by_user: User):

        self._validate_start_matching(triggered_by_user)
        
        updated = self.transition_to(
            self.Status.READY_FOR_MATCHING,
        )
        
        MatchingAttemptEvent.objects.create(
            matching_attempt=updated,
            event_type=MatchingAttemptEvent.EventType.STARTED,
            triggered_by=MatchingAttemptEvent.TriggeredBy.STAFF,
            triggered_by_user=triggered_by_user,
        )

        return updated
    
    @transition(field=state, source=State.READY_FOR_FIRST_COACH_REQUEST, target=State.AWAITING_RTC_REPLY)
    def _transition_to_awaiting_rtc_reply(self):
        pass

    def can_send_intro_call_request(self):
        return self.status == self.Status.READY_FOR_INTRO_CALL and not self.intro_call_requested_at and self.matched_coach and self.matched_coach.status == Coach.Status.AVAILABLE
    
    def send_intro_call_request(self, triggered_by="system", triggered_by_user=None) -> "MatchingAttempt":

        if not self.can_send_intro_call_request():
            raise ValidationError(f"Intro call cannot be requested in the current status: {self.get_status_display()}. It can only be requested when the status is {self.Status.READY_FOR_INTRO_CALL}.")

        if triggered_by == MatchingAttemptEvent.TriggeredBy.COACH:
            raise ValidationError("Coaches cannot trigger requesting intro calls")

        if triggered_by == MatchingAttemptEvent.TriggeredBy.STAFF and triggered_by_user is None:
            raise ValidationError(
                "triggered_by_user must be provided when triggered_by='staff'"
            )

        if triggered_by == MatchingAttemptEvent.TriggeredBy.SYSTEM and triggered_by_user is not None:
            raise ValidationError(
                "triggered_by_user must be None when triggered_by='system'"
            )

        with transaction.atomic():

            self = self.transition_to(self.Status.AWAITING_INTRO_CALL_FEEDBACK)

            MatchingAttemptEvent.objects.create(
                matching_attempt=self,
                event_type=MatchingAttemptEvent.EventType.INTRO_CALL_REQUESTED,
                triggered_by=triggered_by,
                triggered_by_user=triggered_by_user,
            )
            
            self.intro_call_requested_at = timezone.now()

            self.save()

        return self
    
    def can_send_intro_call_info_to_participant(self):
        return self.status == self.Status.AWAITING_INTRO_CALL_FEEDBACK and self.intro_call_requested_at and self.matched_coach and self.matched_coach.status == Coach.Status.AVAILABLE
    
    def send_intro_call_info_to_participant(self, triggered_by="system", triggered_by_user=None) -> "MatchingAttempt":

        if not self.can_send_intro_call_info_to_participant():
            raise ValidationError(f"Intro call info cannot be sent in the current status: {self.get_status_display()}. It can only be sent when the status is {self.Status.AWAITING_INTRO_CALL_FEEDBACK}.")

        if triggered_by == MatchingAttemptEvent.TriggeredBy.COACH:
            raise ValidationError("Coaches cannot trigger requesting intro calls")

        if triggered_by == MatchingAttemptEvent.TriggeredBy.STAFF and triggered_by_user is None:
            raise ValidationError(
                "triggered_by_user must be provided when triggered_by='staff'"
            )

        if triggered_by == MatchingAttemptEvent.TriggeredBy.SYSTEM and triggered_by_user is not None:
            raise ValidationError(
                "triggered_by_user must be None when triggered_by='system'"
            )

        with transaction.atomic():

            MatchingAttemptEvent.objects.create(
                matching_attempt=self,
                event_type=MatchingAttemptEvent.EventType.INTRO_CALL_INFO_SENT,
                triggered_by=triggered_by,
                triggered_by_user=triggered_by_user,
            )
            
            self.intro_call_info_sent_at = timezone.now()

            self.save()

        return self
    
    def can_send_coaching_start_info(self):
        return self.status == self.Status.READY_FOR_START_EMAIL and not self.coaching_start_info_sent_at and self.matched_coach 
    
    def send_coaching_start_info(self, triggered_by="system", triggered_by_user=None) -> "MatchingAttempt":

        if not self.can_send_coaching_start_info():
            raise ValidationError(f"Coaching start info cannot be sent in the current status: {self.get_status_display()}. It can only be sent when the status is {self.Status.READY_FOR_START_EMAIL}.")

        if triggered_by == MatchingAttemptEvent.TriggeredBy.COACH:
            raise ValidationError("Coaches cannot trigger sending coaching start info")

        if triggered_by == MatchingAttemptEvent.TriggeredBy.STAFF and triggered_by_user is None:
            raise ValidationError(
                "triggered_by_user must be provided when triggered_by='staff'"
            )

        if triggered_by == MatchingAttemptEvent.TriggeredBy.SYSTEM and triggered_by_user is not None:
            raise ValidationError(
                "triggered_by_user must be None when triggered_by='system'"
            )

        with transaction.atomic():

            self = self.transition_to(self.Status.MATCHING_COMPLETED)

            MatchingAttemptEvent.objects.create(
                matching_attempt=self,
                event_type=MatchingAttemptEvent.EventType.COACHING_START_INFO_SENT,
                triggered_by=triggered_by,
                triggered_by_user=triggered_by_user,
            )
            
            self.coaching_start_info_sent_at = timezone.now()

            self.save()

        return self

    
    def send_coaching_start_info_to_participant(self, triggered_by="system", triggered_by_user=None) -> "MatchingAttempt":

        if triggered_by == MatchingAttemptEvent.TriggeredBy.COACH:
            raise ValidationError("Coaches cannot trigger sending coaching start info")

        if triggered_by == MatchingAttemptEvent.TriggeredBy.STAFF and triggered_by_user is None:
            raise ValidationError(
                "triggered_by_user must be provided when triggered_by='staff'"
            )

        if triggered_by == MatchingAttemptEvent.TriggeredBy.SYSTEM and triggered_by_user is not None:
            raise ValidationError(
                "triggered_by_user must be None when triggered_by='system'"
            )

        with transaction.atomic():

            MatchingAttemptEvent.objects.create(
                matching_attempt=self,
                event_type=MatchingAttemptEvent.EventType.COACHING_START_INFO_SENT,
                triggered_by=triggered_by,
                triggered_by_user=triggered_by_user,
            )
            
            self.coaching_start_info_sent_at = timezone.now()

            self.save()

        return self

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

            
    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('matching_attempt_detail', kwargs={'pk': self.pk})
                
        
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

    created_at = models.DateTimeField(auto_now_add=True)

    note = models.TextField(
        blank=True,
        help_text="Optional explanation for manual or exceptional transitions.",
    )

    class Meta:

        ordering = ["created_at"]
        verbose_name = "Status Übergang Matching"
        verbose_name_plural = "Status Übergänge Matchings"

        indexes = [
            models.Index(fields=["matching_attempt", "created_at"]),
        ]

        constraints = [
            # prevent pointless transitions
            models.CheckConstraint(
                condition=~Q(from_status=models.F("to_status")),
                name="matching_attempt_transition_status_change",
            ),
        ]

    def __str__(self):
        return f"{self.from_status} → {self.to_status}"
        
class MatchingEvent(models.Model):
    
    class EventType(models.TextChoices):

        # =========================================================
        # 1. MATCHING LIFECYCLE (high-level state transitions)
        # =========================================================
        CREATED = "created", "Matching erstellt"
        STARTED = "started", "Matching gestartet"

        COMPLETED = "completed", "Matching erfolgreich abgeschlossen"
        FAILED = "failed", "Matching fehlgeschlagen / kein Coach gefunden"
        CANCELLED = "cancelled", "Matching abgebrochen"


        # =========================================================
        # 2. AUTOMATION CONTROL (system behavior)
        # =========================================================
        AUTOMATION_ENABLED = "automation_enabled", "Automatisierung aktiviert"
        AUTOMATION_DISABLED = "automation_disabled", "Automatisierung deaktiviert"


        # =========================================================
        # 3. REQUEST-TO-COACH (RTC) LIFECYCLE
        # one RTC = one attempt with a specific coach
        # =========================================================
        RTC_CREATED = "rtc_created", "Matching-Anfrage an Coach erstellt"
        RTC_SENT_TO_COACH = "rtc_sent_to_coach", "Matching-Anfrage an Coach versendet"
        RTC_REMINDER_SENT_TO_COACH = "rtc_reminder_sent_to_coach", "Erinnerung versendet"

        # Terminal states (important for automation logic!)
        RTC_ACCEPTED = "rtc_accepted", "Anfrage akzeptiert"
        RTC_DECLINED = "rtc_declined", "Anfrage abgelehnt"
        RTC_TIMED_OUT = "rtc_timed_out", "Keine Antwort (Timeout)"
        RTC_CANCELLED = "rtc_cancelled", "Anfrage abgebrochen"

        # Optional but useful for debugging / audit
        RTC_DELETED = "rtc_deleted", "Matching-Anfrage gelöscht"


        # =========================================================
        # 4. INTRO CALL PROCESS
        # (after a coach shows interest)
        # =========================================================
        INTRO_CALL_REQUEST_SENT_TO_COACH = "intro_call_request_sent_to_coach", "Intro-Call Anfrage an Coach versendet"
        INTRO_CALL_REMINDER_SENT_TO_COACH = "intro_call_reminder_sent_to_coach", "Reminder für Intro-Call Anfrage"

        INTRO_CALL_FEEDBACK_RECEIVED_FROM_COACH = "intro_call_feedback_received_from_coach", "Feedback vom Coach erhalten"


        # =========================================================
        # 5. COACHING START COMMUNICATION
        # =========================================================
        COACHING_START_INFO_SENT_TO_PARTICIPANT = "coaching_start_info_sent_to_participant", "Start-Info an Teilnehmer:in"
        COACHING_START_INFO_SENT_TO_COACH = "coaching_start_info_sent_to_coach", "Start-Info an Coach"


    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    matching_attempt = models.ForeignKey(
        MatchingAttempt,
        on_delete=models.CASCADE,
        related_name="matching_events",
    )
    
    event_type = models.CharField(
        max_length=50,
        choices=EventType.choices,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    
    payload = models.JSONField(
        default=dict,
        blank=True,
        help_text="Optionales JSON-Feld für zusätzliche Informationen zum Ereignis (z.B. Coach-ID bei RTC-bezogenen Ereignissen)",
    )
    
    class Meta:
        ordering = ["created_at"]
        verbose_name = "Matching Ereignis"
        verbose_name_plural = "Matching Ereignisse"
        
    def __str__(self):
         return f"{self.get_event_type_display()} - {self.matching_attempt} - {self.created_at}"


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

        # Ignored answers
        COACH_RESPONSE_IGNORED = "coach_response_ignored", "Coach-Antwort ignoriert"

        # Deadlines
        REQUEST_DEADLINE_PASSED = "request_deadline_passed", "Antwortfrist des Coaches abgelaufen"

        # Intro-Call Requests
        INTRO_CALL_REQUESTED = "intro_call_requested", "Intro-Call angefragt"
        INTRO_CALL_CONFIRMED = "intro_call_confirmed", "Intro-Call bestätigt"
        INTRO_CALL_DECLINED = "intro_call_declined", "Intro-Call abgelehnt"
        
        # Intro-Call Info to Participant
        INTRO_CALL_INFO_SENT = "intro_call_info_sent", "Intro-Call Info versendet"

        # Coaching Start Info
        COACHING_START_INFO_SENT = "coaching_start_info_sent", "Coaching-Start Info versendet"
        
        # Intro-Call Deadlines
        INTRO_CONFIRMATION_DEADLINE_PASSED = (
            "intro_confirmation_deadline_passed",
            "Frist zur Bestätigung des Intro-Calls abgelaufen",
        )
        INTRO_CALL_TIMEOUT = "intro_call_timeout", "Intro-Call-Frist überschritten"

        # Reminders
        REMINDER_SENT = "reminder_sent", "Erinnerung versendet"

        # Manual actions
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
        verbose_name = "Ereignis Matching"
        verbose_name_plural = "Ereignisse Matching"
        
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
    
class RequestToCoachQuerySet(models.QuerySet):

    def eligible_for_first_request(self):
        return self.filter(
            status=RequestToCoach.Status.IN_PREPARATION,
            first_sent_at__isnull=True,
            requests_sent__lte=1,
            matching_attempt__automation_enabled=True,
            matching_attempt__status__in=[
                MatchingAttempt.Status.READY_FOR_MATCHING,
                MatchingAttempt.Status.MATCHING_ONGOING,
            ],
            coach__status__in=[
                Coach.Status.AVAILABLE,
            ]
        )
        
    def eligible_for_reminder(self):
        return self.filter(
            status=RequestToCoach.Status.AWAITING_REPLY,
            requests_sent__gt=0,
            requests_sent__lt=models.F("max_number_of_requests"),
            first_sent_at__isnull=False,
            matching_attempt__automation_enabled=True,
            matching_attempt__status__in=[
                MatchingAttempt.Status.READY_FOR_MATCHING,
                MatchingAttempt.Status.MATCHING_ONGOING,
            ],
            coach__status__in=[
                Coach.Status.AVAILABLE,
            ]
        )
        
class RequestToCoach(models.Model):

    class State(models.TextChoices):
        IN_PREPARATION = "in_preparation", "In Vorbereitung"
        AWAITING_REPLY = "awaiting_reply", "Warten auf Antwort"
        ACCEPTED = "accepted", "Akzeptiert"
        REJECTED = "rejected", "Abgelehnt"
        NO_RESPONSE_UNTIL_DEADLINE = "no_response_until_deadline", "Keine Rückmeldung bis zur Deadline"
        CANCELLED = "cancelled", "Anfrage abgebrochen"
        
    class Status(models.TextChoices):
        IN_PREPARATION = "in_preparation", "In Vorbereitung"
        AWAITING_REPLY = "awaiting_reply", "Warten auf Antwort"
        ACCEPTED_MATCHING = "accepted_matching", "Matching akzeptiert"
        REJECTED_MATCHING = "rejected_matching", "Matching abgelehnt"
        NO_RESPONSE_UNTIL_DEADLINE = "no_response_until_deadline", "Keine Rückmeldung"
        CANCELLED = "cancelled", "Anfrage abgebrochen"

    ALLOWED_COACH_REQUEST_TRANSITIONS = {

        Status.IN_PREPARATION: frozenset({
            Status.AWAITING_REPLY,
            Status.CANCELLED,
        }),

        Status.AWAITING_REPLY: frozenset({
            Status.ACCEPTED_MATCHING,
            Status.REJECTED_MATCHING,
            Status.NO_RESPONSE_UNTIL_DEADLINE,
            Status.CANCELLED,
        }),

        Status.ACCEPTED_MATCHING: frozenset({
            Status.CANCELLED,
        }),

        Status.REJECTED_MATCHING: frozenset({
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
    
    ue = models.PositiveIntegerField(
        verbose_name="Unterrichtseinheiten",
        help_text="Anzahl der Unterrichtseinheiten, die der Coach übernehmen soll.",
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
    
    state = FSMField(
        max_length=50,
        choices=State.choices,
        default=State.IN_PREPARATION,
        protected=True,
        db_index=True,
    )

    deadline_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Antwortfrist",
        help_text="Frist für rechtzeitige Antwort",
    )
    
    objects = RequestToCoachQuerySet.as_manager()

    # -------------------------------------------------------------
    # State Machine Helpers
    # -------------------------------------------------------------

    @property
    def allowed_transitions(self):
        return self.ALLOWED_COACH_REQUEST_TRANSITIONS.get(self.status, frozenset())


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
    def transition_to(self, new_status):

        from .locks import _get_locked_request_to_coach

        locked = _get_locked_request_to_coach(self)

        locked._validate_transition(new_status)

        old_status = locked.status
        locked.status = new_status
        locked.save(update_fields=["status"])

        RequestToCoachTransition.objects.create(
            request=locked,
            from_status=old_status,
            to_status=new_status,
        )

        # Refresh original instance so callers that continue using `self`
        # don't accidentally overwrite the newly saved status when they
        # call `save()` later.
        try:
            self.refresh_from_db()
        except Exception:
            pass

        return locked

    # -------------------------------------------------------------
    # Convenience Helpers
    # -------------------------------------------------------------

    def is_deadline_passed(self):
        if not self.deadline_at:
            return False
        return timezone.now() > self.deadline_at

    def mark_responded(self):
        if not self.responded_at:
            self.responded_at = timezone.now()
            self.save(update_fields=["responded_at"])

    # -------------------------------------------------------------
    # Domain Actions
    # -------------------------------------------------------------

    @transition(field=state, source=State.IN_PREPARATION, target=State.AWAITING_REPLY)
    def _send_request(self, triggered_by="system", triggered_by_user=None) -> "RequestToCoach":

        # transition the matching attempt if needed
        if self.matching_attempt.status == MatchingAttempt.State.READY_FOR_FIRST_COACH_REQUEST:
            self.matching_attempt._transition_to_awaiting_rtc_reply()
        
        if self.deadline_at is None:
            self.deadline_at = add_business_hours(
                timezone.now(),
                settings.COACH_REQUEST_DEFAULT_DEADLINE_HOURS,
            )

        MatchingEvent.objects.create(
            matching_attempt=self.matching_attempt,
            event_type=MatchingEvent.EventType.RTC_SENT_TO_COACH,
            payload={
                "rtc_id": str(self.id),
                "coach_id": str(self.coach_id) if self.coach_id is not None else None,
                "deadline_at": self.deadline_at.isoformat(),
                "triggered_by": triggered_by,
                "triggered_by_user": str(triggered_by_user.id) if triggered_by_user else None,

            }
        )
        
        RequestToCoachEvent.objects.create(
            request=self,
            event_type=RequestToCoachEvent.EventType.REQUEST_SENT,
            triggered_by=triggered_by,
            triggered_by_user=triggered_by_user,
        )


    @transaction.atomic
    def trigger_send_request(self, triggered_by: str="staff", triggered_by_user: User=None) -> "RequestToCoach":
        self._send_request(triggered_by=triggered_by, triggered_by_user=triggered_by_user)
        self.save()
        return self
    
    def send_reminder(self, triggered_by="system", triggered_by_user=None):
        
        MatchingEvent.objects.create(
            matching_attempt=self.matching_attempt,
            event_type=MatchingEvent.EventType.RTC_REMINDER_SENT_TO_COACH,
            payload={
                "rtc_id": str(self.id),
                "coach_id": str(self.coach_id) if self.coach_id is not None else None,
                "deadline_at": self.deadline_at.isoformat(),
                "triggered_by": triggered_by,
                "triggered_by_user": str(triggered_by_user.id) if triggered_by_user else None,
            }
        )

        RequestToCoachEvent.objects.create(
            request=self,
            event_type=RequestToCoachEvent.EventType.REMINDER_SENT,
            triggered_by=triggered_by,
            triggered_by_user=triggered_by_user,
        )


    @transition(field=state, source=State.AWAITING_REPLY, target=State.NO_RESPONSE_UNTIL_DEADLINE)
    def mark_deadline_passed(self):
        

        MatchingEvent.objects.create(
            matching_attempt=self.matching_attempt,
            event_type=MatchingEvent.EventType.RTC_TIMED_OUT,
            payload={
                "rtc_id": str(self.id),
                "coach_id": str(self.coach_id) if self.coach_id is not None else None,
                "deadline_at": self.deadline_at.isoformat() if self.deadline_at else None,
            }
        )
        
        RequestToCoachEvent.objects.create(
            request=self,
            event_type=RequestToCoachEvent.EventType.TIMED_OUT,
            triggered_by=RequestToCoachEvent.TriggeredBy.SYSTEM,
        )
        
        self.save()

    @transition(field=state, source=State.AWAITING_REPLY, target=State.ACCEPTED)
    def _accept(self, triggered_by=str, triggered_by_user: User=None):
        
        self.matching_attempt.matched_coach = self.coach
        
        MatchingEvent.objects.create(
            matching_attempt=self.matching_attempt,
            event_type=MatchingEvent.EventType.RTC_ACCEPTED,
            payload={
                "rtc_id": str(self.id),
                "coach_id": str(self.coach_id) if self.coach_id is not None else None,
                "deadline_at": self.deadline_at.isoformat(),
                "triggered_by": triggered_by,
                "triggered_by_user": str(triggered_by_user.id) if triggered_by_user else None,
                
            }
        )
        
        RequestToCoachEvent.objects.create(
            request=self,
            event_type=RequestToCoachEvent.EventType.MATCHING_ACCEPTED,
            triggered_by=triggered_by,
            triggered_by_user=triggered_by_user,
        )


    @transaction.atomic
    def trigger_accept(self, triggered_by: str="coach", triggered_by_user: User=None):
        self._accept(triggered_by=triggered_by, triggered_by_user=triggered_by_user)
        self.save()
        return self


    @transition(field=state, source=State.AWAITING_REPLY, target=State.REJECTED)
    def _reject(self, triggered_by="coach", triggered_by_user=None):

        MatchingEvent.objects.create(
            matching_attempt=self.matching_attempt,
            event_type=MatchingEvent.EventType.RTC_DECLINED,
            payload={
                "rtc_id": str(self.id),
                "coach_id": str(self.coach_id) if self.coach_id is not None else None,
                "deadline_at": self.deadline_at.isoformat(),
                "triggered_by": triggered_by,
                "triggered_by_user": str(triggered_by_user.id) if triggered_by_user else None,
            }
        )
        
        RequestToCoachEvent.objects.create(
            request=self,
            event_type=RequestToCoachEvent.EventType.MATCHING_REJECTED,
            triggered_by=triggered_by,
            triggered_by_user=triggered_by_user,
        )
        
    @transaction.atomic
    def trigger_reject(self, triggered_by: str="coach", triggered_by_user: User=None):
        self._reject(triggered_by=triggered_by, triggered_by_user=triggered_by_user)
        self.save()
        return self
    
    @transition(field=state, source=[State.AWAITING_REPLY, State.NO_RESPONSE_UNTIL_DEADLINE, State.REJECTED, State.IN_PREPARATION], target=State.CANCELLED)
    def _cancel(self, triggered_by="staff", triggered_by_user=None):

        MatchingEvent.objects.create(
            matching_attempt=self.matching_attempt,
            event_type=MatchingEvent.EventType.RTC_CANCELLED,
            payload={
                "rtc_id": str(self.id),
                "coach_id": str(self.coach_id) if self.coach_id is not None else None,
                "deadline_at": self.deadline_at.isoformat(),
                "triggered_by": triggered_by,
                "triggered_by_user": str(triggered_by_user.id) if triggered_by_user else None,
            }
        )

    @transaction.atomic
    def trigger_cancel(self, triggered_by: str="coach", triggered_by_user: User=None):
        self._cancel(triggered_by=triggered_by, triggered_by_user=triggered_by_user)
        self.save()
        return self
        
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
            f"- Status: {self.get_state_display()}"
        )

class RequestToCoachTransition(models.Model):

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

    created_at = models.DateTimeField(auto_now_add=True)

    note = models.TextField(
        blank=True,
        help_text="Optionaler Kommentar zur Transition (z.B. Begründung bei manuellen Eingriffen)",
    )

    class Meta:
        ordering = ["created_at"]
        verbose_name = "Status Übergang einer Matching-Anfrage an Coach"
        verbose_name_plural = "Status Übergänge der Matching-Anfragen an Coaches"

        indexes = [
            models.Index(fields=["request", "created_at"]),
            models.Index(fields=["from_status"]),
            models.Index(fields=["to_status"]),
        ]


    def __str__(self):
        return (
            f"Request {self.request_id}: "
            f"{self.from_status} → {self.to_status} "
        )


        
class RequestToCoachEvent(models.Model):

    class EventType(models.TextChoices):
        CREATED = "created", "Matching-Anfrage erstellt"
        REQUEST_SENT = "request_sent", "Matching-Anfrage gesendet"
        REMINDER_SENT = "reminder_sent", "Reminder gesendet"
        MATCHING_ACCEPTED = "accepted", "Matching-Anfrage akzeptiert"
        MATCHING_REJECTED = "rejected", "Matching-Anfrage abgelehnt"
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
        verbose_name = "Ereignis Matching-Anfrage an Coach"
        verbose_name_plural = "Ereignisse Matching-Anfrage an Coaches"

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
    
    

class CoachActionToken(models.Model):
    """Model to represent action tokens for coaches, such as accepting or declining a match.
    These tokens are generated when a request is sent to a coach and are used to securely identify the coach's response when they click on links in emails.
    """

    class Action(models.TextChoices):
        ACCEPT = 'accept', 'Annehmen'
        DECLINE = 'decline', 'Ablehnen'
        CONFIRM_INTRO_CALL = 'confirm_intro_call', 'Intro-Call bestätigen'

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
        blank=True,
        null=True,
        help_text='Die Coach-Anfrage, auf die sich dieser Token bezieht.'
    )
    matching_attempt = models.ForeignKey(
        MatchingAttempt,
        on_delete=models.CASCADE,
        related_name='coach_action_tokens',
        verbose_name='Matching',
        blank=True,
        null=True,
        help_text='Das Matching, auf das sich dieser Token bezieht.'
    )
    action = models.CharField(
        max_length=18,
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
        
        # constraint only requestocoach or matchingattempt may be used, they cannot both be set or both be null. This ensures that the token is always linked to either a specific coach request (for accept/decline) or to the overall matching attempt (for intro call confirmation).
        constraints = [
            models.CheckConstraint(
                condition=(Q(request_to_coach__isnull=False) & Q(matching_attempt__isnull=True)) | (Q(request_to_coach__isnull=True) & Q(matching_attempt__isnull=False)),
                name='coach_action_token_linked_to_either_request_or_attempt'
            )
        ]

    def __str__(self):
        used = 'verwendet' if self.used_at else 'offen'
        return (
            f"{self.get_action_display()}-Token für "
            f"{self.request_to_coach} ({used})"
        )