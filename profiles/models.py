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


class CoachProfile(models.Model):
    class Status(models.TextChoices):
        VERFUEGBAR = 'verfuegbar', 'Verfügbar'
        AUSGEBUCHT = 'ausgebucht', 'Ausgebucht'
        PAUSIERT = 'pausiert', 'Pausiert'
        IM_ONBOARDING = 'im_onboarding', 'Im Onboarding'
        INAKTIV = 'inaktiv', 'Inaktiv'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='coach_profile',
    )
    first_name = models.CharField(max_length=150, verbose_name='Vorname')
    last_name = models.CharField(max_length=150, verbose_name='Nachname')
    city = models.CharField(max_length=100, verbose_name='Stadt')
    languages = models.ManyToManyField(
        Language, related_name='coaches', blank=True, verbose_name='Sprachen'
    )
    coaching_format_online = models.BooleanField(default=False, verbose_name='Online')
    coaching_format_presence = models.BooleanField(default=False, verbose_name='Präsenz')
    coaching_format_hybrid = models.BooleanField(default=False, verbose_name='Hybrid')
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.IM_ONBOARDING,
        verbose_name='Status',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['last_name', 'first_name']
        verbose_name = 'Coach-Profil'
        verbose_name_plural = 'Coach-Profile'

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class CoacheeProfile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    first_name = models.CharField(max_length=150, verbose_name='Vorname')
    last_name = models.CharField(max_length=150, verbose_name='Nachname')
    email = models.EmailField(unique=True, verbose_name='E-Mail')
    city = models.CharField(max_length=100, verbose_name='Stadt')
    languages = models.ManyToManyField(
        Language, related_name='coachees', blank=True, verbose_name='Sprachen'
    )
    coaching_format_online = models.BooleanField(default=False, verbose_name='Online')
    coaching_format_presence = models.BooleanField(default=False, verbose_name='Präsenz')
    coaching_format_hybrid = models.BooleanField(default=False, verbose_name='Hybrid')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['last_name', 'first_name']
        verbose_name = 'Teilnehmer-Profil'
        verbose_name_plural = 'Teilnehmer-Profile'

    def __str__(self):
        return f"{self.first_name} {self.last_name}"
