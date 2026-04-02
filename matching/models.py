from enum import Enum
import logging
from typing import List
import uuid



from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from django.core.validators import MinValueValidator

from django_fsm import FSMField, transition
from django.urls import reverse

from accounts.models import User
from .locks import _get_locked_matching_attempt
from matching import services
from .utils import get_deadline

from profiles.models import Participant, Coach, BeginnerLuftStaff

logger = logging.getLogger(__name__)

class TriggeredByOptions(models.TextChoices):
    SYSTEM = "system", "System"
    STAFF = "staff", "BeginnerLuft"
    COACH = "coach", "Coach"
    PARTICIPANT = "participant", "Teilnehmer:in"

class MatchingAttemptQuerySet(models.QuerySet):

        
    def eligible_for_start_info_notification(self):
        return self.filter(
            state=MatchingAttempt.State.READY_FOR_START_NOTIFICATION,
            coaching_start_info_sent_at__isnull=True,
            automation_enabled=True,
        )

class MatchingAttempt(models.Model):
    class State(models.TextChoices):
        IN_PREPARATION = "in_preparation", "In Vorbereitung"
        AWAITING_RTC_REPLY = "awaiting_rtc_reply", "Warten auf Coach-Antwort zu Matching-Anfrage"
        AWAITING_INTRO_CALL_FEEDBACK_FROM_COACH = "awaiting_intro_call_feedback_from_coach", "Warten auf Coach-Antwort zu Intro-Call Anfrage"
        AWAITING_INTRO_CALL_FEEDBACK_FROM_PARTICIPANT = "awaiting_intro_call_feedback_from_participant", "Warten auf TN-Antwort zu Intro-Call"
        CLARIFICATION_WITH_PARTICIPANT_NEEDED = "clarification_with_participant_needed", "Klärung mit TN nötig"
        READY_FOR_START_NOTIFICATION = "ready_for_start_notification", "Bereit für Coaching-Start-Benachrichtigung"
        MATCHING_COMPLETED = "matching_completed", "Matching abgeschlossen"
        FAILED = "failed", "Keinen Coach gefunden"
        CANCELLED = "cancelled", "Matching abgebrochen"

    # List of states considered 'active' (not terminal)
    ACTIVESTATES = [
        State.IN_PREPARATION,
        State.AWAITING_RTC_REPLY,
        State.AWAITING_INTRO_CALL_FEEDBACK_FROM_COACH,
        State.AWAITING_INTRO_CALL_FEEDBACK_FROM_PARTICIPANT,
        State.CLARIFICATION_WITH_PARTICIPANT_NEEDED,
        State.READY_FOR_START_NOTIFICATION,
    ]

    TERMINAL_STATES = [
        State.MATCHING_COMPLETED,
        State.CANCELLED,
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    participant = models.ForeignKey(
        Participant,
        on_delete=models.CASCADE,
        related_name="matching_attempts",
        verbose_name="Teilnehmer:in",
    )
    
    bl_contact = models.ForeignKey(
        BeginnerLuftStaff,
        on_delete=models.SET_NULL,
        related_name="matching_attempts",
        verbose_name="BL-Kontakt",
        null=True,
    )
    
    ue = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        help_text='Anzahl der genehmigten Unterrichtseinheiten.', 
        verbose_name='Unterrichtseinheiten'
    )

    created_at = models.DateTimeField(auto_now_add=True)

    created_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_matching_attempts",
    )
    
    state = FSMField(
        choices=State.choices,
        default=State.IN_PREPARATION,
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
        return self.state in self.ACTIVESTATES or self.state == self.State.FAILED

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
    
    @property
    def is_active(self):
        return self.state in self.ACTIVESTATES

    class Meta:

        ordering = ["-created_at"]
        verbose_name = "Matching"
        verbose_name_plural = "Matchings"

        indexes = [
            models.Index(fields=["participant", "created_at"]),
        ]


    # -------------------------------------------------------
    # automation control
    # -------------------------------------------------------

    def enable_automation(self, triggered_by_user: User):

        if self.automation_enabled:
            return

        if not self.automation_is_allowed:
            raise ValidationError("Automation cannot be enabled in the current state.")

        self.automation_enabled = True
        self.save(update_fields=["automation_enabled"])

        services.create_matching_event(
            matching_attempt=self,
            event_type=MatchingEvent.EventType.AUTOMATION_ENABLED,
            triggered_by=TriggeredByOptions.STAFF,
            triggered_by_user=triggered_by_user,
        )

    def disable_automation(self, triggered_by_user: User=None, triggered_by: TriggeredByOptions=TriggeredByOptions.STAFF):

        if not self.automation_enabled:
            return
        
        # If triggered_by is STAFF then triggering user must be provided, otherwise it can be null
        if triggered_by == TriggeredByOptions.STAFF and not triggered_by_user:
            raise ValidationError("triggered_by_user must be provided when triggered_by is STAFF.")
        
        # Triggered by cannot be coach or participant
        if triggered_by in [TriggeredByOptions.COACH, TriggeredByOptions.PARTICIPANT]:
            raise ValidationError("triggered_by cannot be COACH or PARTICIPANT. Must be STAFF or SYSTEM.")

        self.automation_enabled = False
        self.save(update_fields=["automation_enabled"])

        services.create_matching_event(
            matching_attempt=self,
            event_type=MatchingEvent.EventType.AUTOMATION_DISABLED,
            triggered_by=triggered_by,
            triggered_by_user=triggered_by_user,
        )

    # -------------------------------------------------------
    # domain actions
    # -------------------------------------------------------
        
    @transition(field=state, source=State.IN_PREPARATION, target=State.AWAITING_RTC_REPLY)
    def start_matching(self, triggered_by_user: User):
        
        services.trigger_start_matching(self, triggered_by_user)
        
    @transition(field=state, source=State.FAILED, target=State.AWAITING_RTC_REPLY)
    def resume_matching(self, triggered_by_user: User):  
        services.trigger_resume_matching(self, triggered_by_user)
    
    @transition(field=state, source=State.AWAITING_RTC_REPLY, target=State.AWAITING_INTRO_CALL_FEEDBACK_FROM_COACH)
    def send_intro_call_notifications(self):
        pass
    
    @transition(field=state, source=State.AWAITING_INTRO_CALL_FEEDBACK_FROM_COACH, target=State.AWAITING_INTRO_CALL_FEEDBACK_FROM_PARTICIPANT)
    def send_request_for_intro_call_feedback_to_participant(self):
        pass
    
    @transition(field=state, source=State.AWAITING_INTRO_CALL_FEEDBACK_FROM_PARTICIPANT, target=State.MATCHING_COMPLETED)
    def complete_matching(self):
        pass
    
    @transition(field=state, source=State.AWAITING_INTRO_CALL_FEEDBACK_FROM_PARTICIPANT, target=State.CLARIFICATION_WITH_PARTICIPANT_NEEDED)
    def clarify_matching_with_participant(self):
        pass
    
    @transition(field=state, source=State.AWAITING_RTC_REPLY, target=State.FAILED)
    def run_out_of_matching_requests_to_coaches(self):
        pass
    # transition to cancel and allow from any state
    
    @transition(field=state, source="*", target=State.CANCELLED)
    def cancel_matching(self):
        pass
    
    @transition(field=state, source="*", target=State.MATCHING_COMPLETED)
    def manually_match_with_coach(self, coach: Coach):
        self.matched_coach = coach
        

    # -------------------------------------------------------
    # queue helpers
    # -------------------------------------------------------

    def get_active_requests(self) -> List["RequestToCoach"]:
        return list(
            self.coach_requests.filter(
                state=RequestToCoach.State.AWAITING_REPLY
            )
        )

    def get_next_request(self) -> "RequestToCoach":

        return (
            self.coach_requests
            .filter(state=RequestToCoach.State.IN_PREPARATION)
            .order_by("priority")
            .first()
        )

    def has_remaining_requests(self):

        return self.coach_requests.filter(
            state=RequestToCoach.State.IN_PREPARATION
        ).exists()

    # -------------------------------------------------------

            
    def get_absolute_url(self):
        return reverse('matching_attempt_detail', kwargs={'pk': self.pk})
                
        
    def __str__(self):
        return (
            f"Matching für {self.participant} "
            f"- State: {self.get_state_display()}"
        )
   
      


    
class RequestToCoachQuerySet(models.QuerySet):
        
    def eligible_for_reminder(self):
        return self.filter(
            state=RequestToCoach.State.AWAITING_REPLY,
            requests_sent__gt=0,
            requests_sent__lt=models.F("max_number_of_requests"),
            matching_attempt__automation_enabled=True,
            matching_attempt__state__in=[
                MatchingAttempt.State.AWAITING_RTC_REPLY,
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
        NO_RESPONSE_UNTIL_DEADLINE = "no_response_until_deadline", "Keine Antwort bis Deadline"
        CANCELLED = "cancelled", "Anfrage abgebrochen"
        

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
    # Convenience Helpers
    # -------------------------------------------------------------

    def get_last_sent_event(self):
        return (
            self.matching_attempt.matching_events
            .filter(
                event_type__in=MatchingEvent.RTQ_SENT_EVENTS,
                payload__rtc_id=str(self.id),
            )
            .order_by("-created_at")
            .first()
        )
        
    def get_sent_count(self):
        return (
            self.matching_attempt.matching_events
            .filter(
                event_type__in=MatchingEvent.RTQ_SENT_EVENTS,
                payload__rtc_id=str(self.id),
            )
            .count()
        )
    
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
    def send_first_request(self):
        """Transitions the RTC to AWAITING_REPLY and sets the initial deadline for the coach response. Should only be called once per RTC."""
        
        if self.deadline_at is None:
            self.deadline_at = get_deadline(
                timezone.now(),
                settings.COACH_REQUEST_DEFAULT_DEADLINE_HOURS,
            )
        
        
        
        

    
    def send_reminder(self, triggered_by: TriggeredByOptions=TriggeredByOptions.SYSTEM, triggered_by_user: User=None):
        from matching import services

        services.create_matching_event(
            matching_attempt=self.matching_attempt,
            event_type=MatchingEvent.EventType.RTC_REMINDER_SENT_TO_COACH,
            triggered_by=triggered_by,
            triggered_by_user=triggered_by_user,
            payload={
                "rtc_id": str(self.id),
                "coach_id": str(self.coach_id) if self.coach_id is not None else None,
                "deadline_at": self.deadline_at.isoformat(),
            }
        )


    @transition(field=state, source=State.AWAITING_REPLY, target=State.NO_RESPONSE_UNTIL_DEADLINE)
    def mark_deadline_as_passed(self):
        pass
        

    @transition(field=state, source=State.AWAITING_REPLY, target=State.ACCEPTED)
    def accept(self, on_time: bool) -> "RequestToCoach":
        if on_time:
            self.matching_attempt.matched_coach = self.coach
            
        return self


    @transition(field=state, source=State.AWAITING_REPLY, target=State.REJECTED)
    def reject(self):
        pass

    
    @transition(field=state, source=[State.AWAITING_REPLY, State.NO_RESPONSE_UNTIL_DEADLINE, State.REJECTED, State.IN_PREPARATION], target=State.CANCELLED)
    def _cancel(self, triggered_by, triggered_by_user=None):
        from matching import services

        services.create_matching_event(
            matching_attempt=self.matching_attempt,
            event_type=MatchingEvent.EventType.RTC_CANCELLED,
            triggered_by=triggered_by,
            triggered_by_user=triggered_by_user,
            payload={
                "rtc_id": str(self.id),
                "coach_id": str(self.coach_id) if self.coach_id is not None else None,
                "deadline_at": self.deadline_at.isoformat(),
            }
        )

    @transaction.atomic
    def trigger_cancel(self, triggered_by: TriggeredByOptions=TriggeredByOptions.STAFF, triggered_by_user: User=None):
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
                condition=Q(state="awaiting_reply"),
                name="one_request_awaiting_reply_per_attempt",
            ),
        ]

        indexes = [
            models.Index(fields=["matching_attempt", "state"])
        ]

    def __str__(self):
        return (
            f"Matching-Anfrage an {self.coach} "
            f"für Coaching mit {self.matching_attempt.participant} "
            f"- State: {self.get_state_display()}"
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
        
class ParticipantActionToken(models.Model):
    """Model to represent action tokens for participants, such as confirming the start of a coaching or requesting clarification.
    These tokens are generated when a request is sent to a participant and are used to securely identify the participant's response when they click on links in emails.
    """

    class Action(models.TextChoices):
        START_COACHING = 'start_coaching', 'Coaching starten'
        CLARIFICATION_NEEDED = 'clarification_needed', 'Klärung benötigt'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    token = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        verbose_name='Token',
        help_text='URL-safe random string generated by secrets.token_urlsafe(48).',
    )
    matching_attempt = models.ForeignKey(
        MatchingAttempt,
        on_delete=models.CASCADE,
        related_name='participant_action_tokens',
        verbose_name='Matching',
        blank=True,
        null=True,
        help_text='Das Matching, auf das sich dieser Token bezieht.'
    )

    action = models.CharField(
        max_length=30,
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
        verbose_name = 'Teilnehmer-Aktions-Token'
        verbose_name_plural = 'Teilnehmer-Aktions-Tokens'
        
        indexes = [
            models.Index(fields=["matching_attempt", "used_at"]),
        ]

    def __str__(self):
        used = 'verwendet' if self.used_at else 'offen'
        return (
            f"{self.get_action_display()}-Token für "
            f"{self.matching_attempt} ({used})"
        )
        
  
class MatchingEvent(models.Model):
    

    
    class EventType(models.TextChoices):

        # =========================================================
        # 1. MATCHING LIFECYCLE (high-level state transitions)
        # =========================================================
        CREATED = "created", "Matching erstellt"
        STARTED = "started", "Matching gestartet"
        RESUMED = "resumed", "Matching fortgesetzt"

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
        RTC_ACCEPTED = "rtc_accepted", "Matching-Anfrage akzeptiert"
        RTC_DECLINED = "rtc_declined", "Matching-Anfrage abgelehnt"
        RTC_TIMED_OUT = "rtc_timed_out", "Keine Antwort (Timeout)"
        RTC_CANCELLED = "rtc_cancelled", "Matching-Anfrage abgebrochen"
        
        RESPONDED_LATE_TO_RTC = "responded_late_to_rtc", "Antwort nach Deadline"

        RTC_DELETED = "rtc_deleted", "Matching-Anfrage gelöscht"
        
        ALL_RTCS_DECLINED = "all_rtcs_declined", "Alle Matching-Anfragen abgelehnt"


        # =========================================================
        # 4. INTRO CALL PROCESS
        # (after a coach shows interest)
        # =========================================================
        INTRO_CALL_REQUEST_SENT_TO_COACH = "intro_call_request_sent_to_coach", "Intro-Call Anfrage an Coach versendet"
        INTRO_CALL_REMINDER_SENT_TO_COACH = "intro_call_reminder_sent_to_coach", "Reminder für Intro-Call Anfrage"

        INTRO_CALL_FEEDBACK_RECEIVED_FROM_COACH = "intro_call_feedback_received_from_coach", "Feedback zum Intro-Call von Coach erhalten"
        
        INTRO_CALL_INFO_SENT_TO_PARTICIPANT = "intro_call_info_sent_to_participant", "Intro-Call Informationen an TN versendet"
        
        INTRO_CALL_FEEDBACK_REQUESTED_FROM_PARTICIPANT = "intro_call_feedback_requested_from_participant", "Feedback zum Intro-Call bei TN angefragt"
        
        COACHING_CAN_START_FEEDBACK_RECEIVED_FROM_PARTICIPANT = "coaching_can_start_feedback_received_from_participant", "Positives Feedback zum Intro-Call von TN erhalten"
        
        CLARIFICATION_NEEEDED_FEEDBACK_RECEIVED_FROM_PARTICIPANT = "clarification_needed_feedback_received_from_participant", "TN hat nach Intro-Call um Klärung gebeten"
        
        ESCALATION_NOTIFICATION_SENT_TO_STAFF = "escalation_notification_sent_to_staff", "BeginnerLuft über notwendige Klärung informiert"
        
        INFORMATION_ABOUT_CLARIFICATION_SENT_TO_COACH = "information_about_clarification_sent_to_coach", "Coach über notwendige Klärung informiert"


        # =========================================================
        # 5. COACHING START COMMUNICATION
        # =========================================================
        COACHING_START_INFO_SENT_TO_PARTICIPANT = "coaching_start_info_sent_to_participant", "Start-Info an TN versendet"
        COACHING_START_INFO_SENT_TO_COACH = "coaching_start_info_sent_to_coach", "Start-Info an Coach versendet"
        
        # =========================================================
        # 6. MANUAL INTERVENTIONS
        # =========================================================
        MANUALLY_MATCHED_TO_COACH = "manually_matched_to_coach", "Manuell mit Coach gematcht"

    RTQ_SENT_EVENTS = [
        EventType.RTC_SENT_TO_COACH,
        EventType.RTC_REMINDER_SENT_TO_COACH,
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    matching_attempt = models.ForeignKey(
        MatchingAttempt,
        on_delete=models.CASCADE,
        related_name="matching_events",
    )
    
    request_to_coach = models.ForeignKey(
        RequestToCoach,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="events",
    )
        
    event_type = models.CharField(
        max_length=100,
        choices=EventType.choices,
    )

    triggered_by = models.CharField(
        max_length=20,
        choices=TriggeredByOptions.choices,
        default=TriggeredByOptions.SYSTEM,
    )

    triggered_by_user = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text="Benutzer, der das Ereignis ausgelöst hat (nur bei staff oder coach)",
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
        
    def get_absolute_url(self):
        return reverse('matching_event_detail', kwargs={'pk': self.pk})
        
    def __str__(self):
         return f"{self.get_event_type_display()} - {self.matching_attempt} - {self.created_at}"