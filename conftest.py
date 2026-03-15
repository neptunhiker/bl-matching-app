import datetime
import pytest
from django.core import mail

from profiles.models import Coach, Participant
from accounts.models import User
from matching.models import MatchingAttempt, RequestToCoach

@pytest.fixture(autouse=True)
def use_anymail_test_backend(settings):
    """
    Override the email backend for every test in the project.

    - Prevents any real HTTP calls to the Brevo API.
    - anymail.test.EmailBackend populates django.core.mail.outbox with
        AnymailMessage instances, so tests can inspect .tags, .to, .bcc, etc.
    - mail.outbox is reset to [] before each test so outbox state never leaks
        between tests.
    - The settings fixture from pytest-django scopes all overrides to the
        current test; they are reverted automatically after each test.
    """
    settings.EMAIL_BACKEND = 'anymail.backends.test.EmailBackend'
    settings.ANYMAIL = {'BREVO_API_KEY': 'test-key'}
    mail.outbox = []
    

@pytest.fixture
def staff_user():
    return User.objects.create_user(
        email="staff_member@example.com",
        password="testpass123",
        first_name="Staff",
        last_name="Member",
        is_staff=True,
    )
    
@pytest.fixture
def superuser():
    return User.objects.create_user(
        email="superuser@example.com",
        password="testpass123",
        first_name="Super",
        last_name="User",
        is_superuser=True,
    )
    
@pytest.fixture()
def coach_user_1():
    return User.objects.create_user(
        email="coach@example.com",
        password="testpass123",
        first_name="Chris",
        last_name="Coach",
    )
    
@pytest.fixture()
def coach_user_2():
    return User.objects.create_user(
        email="coach2@example.com",
        password="testpass123",
        first_name="Chloe",
        last_name="Koch",
    )
    
@pytest.fixture
def coach_1(coach_user_1):
    return Coach.objects.create(
        user=coach_user_1,
        city="Berlin",
    )
    
@pytest.fixture
def coach_2(coach_user_2):
    return Coach.objects.create(
        user=coach_user_2,
        city="Hamburg",
    )
    
@pytest.fixture()
def participant(db):
    return Participant.objects.create(
        first_name="Patricia",
        last_name="Participant",
        email="patricia_participant@example.com",
        city="Berlin",
        start_date=datetime.date(2026, 11, 22)
    )
    
@pytest.fixture
def matching_attempt(participant):
    return MatchingAttempt.objects.create(
        participant=participant,
        ue=48,
    )
    
@pytest.fixture
def rtc(matching_attempt, coach_1):
    return RequestToCoach.objects.create(
        matching_attempt=matching_attempt,
        coach=coach_1,
        priority=20,
        ue=40,
    )