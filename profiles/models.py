import uuid
from django.db import models
from django.conf import settings


class Language(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Sprache'
        verbose_name_plural = 'Sprachen'

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
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='coach_profile',
    )
    city = models.CharField(max_length=100, verbose_name='Stadt')
    languages = models.ManyToManyField(
        Language, related_name='coaches', blank=True, verbose_name='Sprachen'
    )
    bio = models.TextField(blank=True, verbose_name='Biografie')
    coaching_style = models.TextField(blank=True, verbose_name='Coaching-Stil', help_text='Coaching-Stil')
    linkedin_url = models.URLField(blank=True, verbose_name='LinkedIn Profil')
    profile_photo = models.ImageField(upload_to='coach_photos/', blank=True, null=True, verbose_name='Profilfoto')
    
    coaching_format_online = models.BooleanField(default=False, verbose_name='Online')
    coaching_format_presence = models.BooleanField(default=False, verbose_name='Präsenz')
    coaching_format_hybrid = models.BooleanField(default=False, verbose_name='Hybrid')
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
        return f"{self.user.first_name} {self.user.last_name}"
    
    @property
    def email(self):
        return self.user.email
    
    @property
    def first_name(self):
        return self.user.first_name
    
    @property
    def last_name(self):
        return self.user.last_name

    class Meta:
        ordering = ['user__last_name', 'user__first_name']
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
    created_at = models.DateTimeField(auto_now_add=True)
    background_information = models.TextField(blank=True, verbose_name='Hintergrundinformationen')
    coaching_target = models.TextField(blank=True, verbose_name='Coaching-Ziel')
    avgs_data_docs_available = models.BooleanField(default=False, verbose_name='AVGS-Daten verfügbar', help_text='Liegen alle notwendigen AVGS-Daten vor, um mit dem Matching zu starten?')

    class Meta:
        ordering = ['last_name', 'first_name']
        verbose_name = 'Teilnehmer:in'
        verbose_name_plural = 'Teilnehmer:innen'

    def __str__(self):
        return f"{self.first_name} {self.last_name}"
