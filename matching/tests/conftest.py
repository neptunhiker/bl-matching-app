import datetime
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
        start_date=datetime.date(2026, 11, 22)
    )
    
@pytest.fixture
def participant_2(db):
    return Participant.objects.create(
        first_name="Jim",
        last_name="Doe",
        email="jim_doe@example.com",
        city="Hamburg",
        start_date=datetime.date(2026, 6, 11)

    )


@pytest.fixture
def staff_user(db):
    return User.objects.create_user(
        email="staff_member@example.com",
        password="testpass123",
        first_name="Staff",
        last_name="Member",
        is_staff=True,
    )
    
@pytest.fixture
def superuser(db):
    return User.objects.create_user(
        email="superuser@example.com",
        password="testpass123",
        first_name="Super",
        last_name="User",
        is_superuser=True,
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
def coach_user_3(db):
    return User.objects.create_user(
        email="paul_mazzes@example.com",
        password="testpass123",
        first_name="Paul",
        last_name="Mazzes",
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
def coach_3(db, coach_user_3):
    return Coach.objects.create(
        user=coach_user_3,
        city="Hamburg",
    )

@pytest.fixture
def matching_attempt(db, participant):
    return MatchingAttempt.objects.create(
        participant=participant,
        ue=48,
    )
    


@pytest.fixture
def rtc(db, matching_attempt, coach):
    return RequestToCoach.objects.create(
        matching_attempt=matching_attempt,
        coach=coach,
        priority=20,
        ue=40,
    )
    
@pytest.fixture
def rtc_high_priority(db, matching_attempt, coach_2):
    return RequestToCoach.objects.create(
        matching_attempt=matching_attempt,
        coach=coach_2,
        priority=1,
    )


@pytest.fixture
def matching_event(db, matching_attempt, staff_user):
    from matching.models import MatchingEvent, TriggeredByOptions
    return MatchingEvent.objects.create(
        matching_attempt=matching_attempt,
        event_type=MatchingEvent.EventType.CREATED,
        triggered_by=TriggeredByOptions.STAFF,
        triggered_by_user=staff_user,
    )


@pytest.fixture
def bl_staff(db, staff_user):
    from profiles.models import BeginnerLuftStaff
    return BeginnerLuftStaff.objects.create(
        user=staff_user,
        slack_user_id='U12345678',
    )


# ── Phase 3: token fixtures ──────────────────────────────────────────────────

@pytest.fixture
def matching_attempt_with_coach(db, matching_attempt, coach):
    matching_attempt.matched_coach = coach
    matching_attempt.save()
    return matching_attempt


@pytest.fixture
def coach_action_token_accept(db, rtc):
    from matching.models import CoachActionToken
    from matching.tokens import generate_secure_token
    return CoachActionToken.objects.create(
        request_to_coach=rtc,
        action=CoachActionToken.Action.ACCEPT,
        token=generate_secure_token(),
    )


@pytest.fixture
def coach_action_token_decline(db, rtc):
    from matching.models import CoachActionToken
    from matching.tokens import generate_secure_token
    return CoachActionToken.objects.create(
        request_to_coach=rtc,
        action=CoachActionToken.Action.DECLINE,
        token=generate_secure_token(),
    )


@pytest.fixture
def coach_action_token_confirm_intro_call(db, matching_attempt_with_coach):
    from matching.models import CoachActionToken
    from matching.tokens import generate_secure_token
    return CoachActionToken.objects.create(
        matching_attempt=matching_attempt_with_coach,
        action=CoachActionToken.Action.CONFIRM_INTRO_CALL,
        token=generate_secure_token(),
    )


@pytest.fixture
def participant_action_token_start(db, matching_attempt_with_coach):
    from matching.models import ParticipantActionToken
    from matching.tokens import generate_secure_token
    return ParticipantActionToken.objects.create(
        matching_attempt=matching_attempt_with_coach,
        action=ParticipantActionToken.Action.START_COACHING,
        token=generate_secure_token(),
    )


@pytest.fixture
def participant_action_token_clarify(db, matching_attempt_with_coach):
    from matching.models import ParticipantActionToken
    from matching.tokens import generate_secure_token
    return ParticipantActionToken.objects.create(
        matching_attempt=matching_attempt_with_coach,
        action=ParticipantActionToken.Action.CLARIFICATION_NEEDED,
        token=generate_secure_token(),
    )