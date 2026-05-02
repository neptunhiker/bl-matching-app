import uuid
from django.conf import settings
from django.db import models
from django.core.exceptions import ValidationError


class Language(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Sprache'
        verbose_name_plural = 'Sprachen'

    def __str__(self):
        return self.name


class City(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Stadt'
        verbose_name_plural = 'Städte'

    def __str__(self):
        return self.name


class Industry(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Branche'
        verbose_name_plural = 'Branchen'

    def __str__(self):
        return self.name


class CoachQuerySet(models.QuerySet):

    def available(self):
        return self.filter(status=Coach.Status.AVAILABLE)
    
    

class Coach(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = 'available', 'Verfügbar'
        PAUSED = 'paused', 'Pausiert'
        ONBOARDING = 'onboarding', 'Im Onboarding'
        INACTIVE = 'inactive', 'Inaktiv'
        
    class CommunicationChannel(models.TextChoices):
        EMAIL = "email", "Email"
        SLACK = "slack", "Slack"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    coaching_hub_id = models.UUIDField(
        unique=True, null=True, blank=True,
        verbose_name='Coaching Hub ID',
        help_text='Externe UUID aus dem Coaching Hub API.',
    )
    first_name = models.CharField(max_length=150, verbose_name='Vorname')
    last_name = models.CharField(max_length=150, verbose_name='Nachname')
    email = models.EmailField(unique=True, verbose_name='E-Mail')
    updated = models.DateTimeField(null=True, blank=True, verbose_name='Zuletzt aktualisiert (extern)')

    summary = models.TextField(blank=True, verbose_name='Zusammenfassung')
    own_coaching_room = models.BooleanField(default=False, verbose_name='Eigener Coaching-Raum')
    preferred_coaching_location = models.CharField(max_length=100, blank=True, verbose_name='Bevorzugter Coaching-Ort')
    coaching_focus = models.TextField(blank=True, verbose_name='Coaching-Fokus')
    coaching_qualification = models.TextField(blank=True, verbose_name='Coaching-Qualifikation')
    coaching_methods = models.TextField(blank=True, verbose_name='Coaching-Methoden')
    education = models.TextField(blank=True, verbose_name='Ausbildung')
    work_experience = models.TextField(blank=True, verbose_name='Berufserfahrung')

    languages = models.ManyToManyField(
        Language, related_name='coaches', blank=True, verbose_name='Sprachen'
    )
    coaching_cities = models.ManyToManyField(
        City, related_name='coaches', blank=True, verbose_name='Coaching-Städte'
    )
    industry_experience = models.ManyToManyField(
        Industry, related_name='coaches', blank=True, verbose_name='Branchenerfahrung'
    )

    expert_for_job_applications = models.BooleanField(default=False, verbose_name='Job-Bewerbungen')
    leadership_coaching = models.BooleanField(default=False, verbose_name='Führungscoaching')
    intercultural_coaching = models.BooleanField(default=False, verbose_name='Interkulturelles Coaching')
    high_profile_coaching = models.BooleanField(default=False, verbose_name='High-Profile Coaching')
    coaching_with_language_barriers = models.BooleanField(default=False, verbose_name='Sprachbarrieren')
    hr_experience = models.BooleanField(default=False, verbose_name='HR-Erfahrung')
    therapeutic_experience = models.BooleanField(default=False, verbose_name='Therapeutische Erfahrung')
    adhs_coaching = models.BooleanField(default=False, verbose_name='ADHS-Coaching')
    lgbtq_coaching = models.BooleanField(default=False, verbose_name='LGBTQ+ Coaching')

    linkedin_url = models.URLField(blank=True, verbose_name='LinkedIn Profil')
    website_url = models.URLField(blank=True, verbose_name='BeginnerLuft Website Profil')

    preferred_communication_channel = models.CharField(
        max_length=20,
        choices=CommunicationChannel.choices,
        default=CommunicationChannel.SLACK,
        verbose_name='Bevorzugter Kommunikationskanal',
    )

    slack_user_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="ID des Slack-Benutzers, z.B. U12345678. Nur erforderlich, wenn der bevorzugte Kommunikationskanal Slack ist.",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ONBOARDING,
        verbose_name='Status',
    )

    status_notes = models.TextField(blank=True, verbose_name='Status-Kommentar', help_text='Kommentar zum Status')

    maximum_capacity = models.PositiveIntegerField(verbose_name='Maximale Kapazität', help_text='Maximale Anzahl von Teilnehmer:innen, die gleichzeitig betreut werden können', blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    
    objects = CoachQuerySet.as_manager()

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('coach_detail', kwargs={'pk': self.pk})

    class Meta:
        ordering = ['last_name', 'first_name']
        verbose_name = 'Coach'
        verbose_name_plural = 'Coaches'

    def __str__(self):
        return self.full_name


class Participant(models.Model):
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    first_name = models.CharField(max_length=150, verbose_name='Vorname')
    last_name = models.CharField(max_length=150, verbose_name='Nachname')
    email = models.EmailField(unique=True, verbose_name='E-Mail')
    city = models.CharField(max_length=100, verbose_name='Stadt')
    languages = models.ManyToManyField(
        Language, related_name='participants', blank=True, verbose_name='Sprachen'
    )
    coaching_format_online = models.BooleanField(default=False, verbose_name='Online')
    coaching_format_presence = models.BooleanField(default=False, verbose_name='Präsenz')
    coaching_format_hybrid = models.BooleanField(default=False, verbose_name='Hybrid')
    start_date = models.DateField(verbose_name='Gewünschtes Startdatum', help_text='Wann soll das Coaching idealerweise starten?')
    end_date = models.DateField(verbose_name='Gewünschtes Enddatum', help_text='Wann soll das Coaching idealerweise enden?', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    background_information = models.TextField(blank=True, verbose_name='Hintergrundinformationen')
    coaching_target = models.TextField(blank=True, verbose_name='Coaching-Ziel')
    notes = models.TextField(blank=True, verbose_name='Notizen')
    avgs_data_docs_available = models.BooleanField(default=False, verbose_name='AVGS-Daten verfügbar', help_text='Liegen BeginnerLuft alle notwendigen AVGS-Daten vor, um mit dem Matching zu starten?')
    calendly_booking = models.OneToOneField(
        "bookings.CalendlyBooking",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="participant",
        verbose_name="Calendly-Buchung",
    )
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('participant_detail', kwargs={'pk': self.pk})
    
    class Meta:
        ordering = ['last_name', 'first_name']
        verbose_name = 'Teilnehmer:in'
        verbose_name_plural = 'Teilnehmer:innen'

    def __str__(self):
        return f"{self.first_name} {self.last_name}"
    
class BeginnerLuftStaff(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='staff_profile',
    )
    
    slack_user_id = models.CharField(
        max_length=100,
        help_text="ID des Slack-Benutzers, z.B. U12345678.",
    )
    
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if not self.user.is_staff:
            raise ValidationError("Der zugeordnete User muss ein Mitarbeiter:in sein (is_staff=True).")
        
    class Meta:
        verbose_name = 'BeginnLuft Mitarbeiter:in'
        verbose_name_plural = 'BeginnLuft Mitarbeiter:innen'

    def __str__(self):
        return f"{self.user.first_name} {self.user.last_name}"
