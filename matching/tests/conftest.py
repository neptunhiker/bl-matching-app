import pytest
from accounts.models import User
from profiles.models import Coach, Participant
from matching.models import MatchingAttempt, RequestToCoach


@pytest.fixture
def participant(db):
    return Participant.objects.create(
        first_name="Peter",
        last_name="Participant",
        email="peter_participant@example.com",
        city="Berlin",
    )
    
@pytest.fixture
def participant_2(db):
    return Participant.objects.create(
        first_name="Jim",
        last_name="Doe",
        email="jim_doe@example.com",
        city="Hamburg",
    )


@pytest.fixture
def coach_user(db):
    return User.objects.create_user(
        email="carl_coach@example.com",
        password="testpass123",
        first_name="Carl",
        last_name="Coach",
    )
    
@pytest.fixture
def coach_user_2(db):
    return User.objects.create_user(
        email="carla_coacheressa@example.com",
        password="testpass123",
        first_name="Carla",
        last_name="Coacheressa",
    )


@pytest.fixture
def coach(db, coach_user):
    return Coach.objects.create(
        user=coach_user,
        city="Berlin",
    )
    

@pytest.fixture
def coach_2(db, coach_user_2):
    return Coach.objects.create(
        user=coach_user_2,
        city="Milano",
    )

@pytest.fixture
def matching_attempt(db, participant):
    return MatchingAttempt.objects.create(
        participant=participant,
    )
    


@pytest.fixture
def rtc(db, matching_attempt, coach):
    return RequestToCoach.objects.create(
        matching_attempt=matching_attempt,
        coach=coach,
        priority=20,
    )
    
@pytest.fixture
def rtc_high_priority(db, matching_attempt, coach_2):
    return RequestToCoach.objects.create(
        matching_attempt=matching_attempt,
        coach=coach_2,
        priority=1,
    )