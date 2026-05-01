from django.db import models
import uuid
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.utils import timezone


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True')

        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    class SexChoices(models.TextChoices):
        DIVERS = "divers", "Divers"
        FEMALE = "frau", "Frau"
        MALE = "herr", "Herr"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    sex = models.CharField(
        max_length=10,
        choices=SexChoices.choices,
        blank=True,
        verbose_name="Anrede",
        help_text="Anrede für den Benutzer (Herr, Frau, Divers). Wichtig, um die Person korrekt ansprechen zu können.",
    )
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    nickname = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Spitzname",
        help_text="Optionaler Spitzname, mit dem der Chatbot die Person anspricht.",
    )
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []
    
    # property
    @property
    def display_name(self) -> str:
        """Name the chatbot uses to address this user. Falls back to first_name."""
        return self.nickname or self.first_name

    @property
    def german_article(self):
        if self.sex in [self.SexChoices.DIVERS, self.SexChoices.FEMALE]:
            return "die"
        else:
            return "der"


    def __str__(self):
        return f"{self.first_name} {self.last_name}".strip() or self.email
