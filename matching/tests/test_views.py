"""
Auth-gating tests for all login-required views.

Covers for each protected URL:
  1. Unauthenticated request  → 302 redirect to the login page
  2. Authenticated request    → 200 OK

Additionally, for MatchingAttemptCreateView (staff-only):
  3. Non-staff authenticated  → 403 Forbidden
  4. Staff authenticated      → 200 OK
"""
import pytest

from accounts.models import User
from matching.models import MatchingAttempt, RequestToCoach
from profiles.models import Coach, Participant

LOGIN_URL = '/accounts/login/'


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def user(db):
    return User.objects.create_user(email='user@test.com', password='testpass')


@pytest.fixture
def staff_user(db):
    return User.objects.create_user(
        email='staff@test.com', password='testpass', is_staff=True
    )


@pytest.fixture
def participant(db):
    return Participant.objects.create(
        first_name='Anna',
        last_name='Müller',
        email='anna@test.com',
        city='Berlin',
    )


@pytest.fixture
def coach_user(db):
    return User.objects.create_user(email='coach@test.com', password='testpass')


@pytest.fixture
def coach(db, coach_user):
    return Coach.objects.create(user=coach_user, city='München')


@pytest.fixture
def matching_attempt(db, participant):
    return MatchingAttempt.objects.create(participant=participant)


@pytest.fixture
def request_to_coach(db, matching_attempt, coach):
    return RequestToCoach.objects.create(
        matching_attempt=matching_attempt,
        coach=coach,
    )


# ── Helper ────────────────────────────────────────────────────────────────────

def assert_login_redirect(response):
    """Assert that an unauthenticated request is redirected to the login page."""
    assert response.status_code == 302
    assert response['Location'].startswith(LOGIN_URL)


# ── Landing page (/) ──────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestLandingView:
    url = '/'

    def test_unauthenticated_redirects_to_login(self, client):
        response = client.get(self.url)
        assert_login_redirect(response)

    def test_authenticated_gets_200(self, client, user):
        client.force_login(user)
        response = client.get(self.url)
        assert response.status_code == 200


# ── MatchingAttemptListView (/matching/matchings/) ────────────────────────────

@pytest.mark.django_db
class TestMatchingAttemptListView:
    url = '/matching/matchings/'

    def test_unauthenticated_redirects_to_login(self, client):
        response = client.get(self.url)
        assert_login_redirect(response)

    def test_authenticated_gets_200(self, client, user):
        client.force_login(user)
        response = client.get(self.url)
        assert response.status_code == 200


# ── MatchingAttemptCreateView (/matching/matchings/new/) ──────────────────────

@pytest.mark.django_db
class TestMatchingAttemptCreateView:
    url = '/matching/matchings/new/'

    def test_unauthenticated_redirects_to_login(self, client):
        response = client.get(self.url)
        assert_login_redirect(response)

    def test_non_staff_user_gets_403(self, client, user):
        client.force_login(user)
        response = client.get(self.url)
        assert response.status_code == 403

    def test_staff_user_gets_200(self, client, staff_user):
        client.force_login(staff_user)
        response = client.get(self.url)
        assert response.status_code == 200


# ── MatchingAttemptDetailView (/matching/matching-attempt/<pk>/) ──────────────

@pytest.mark.django_db
class TestMatchingAttemptDetailView:

    def test_unauthenticated_redirects_to_login(self, client, matching_attempt):
        url = f'/matching/matching/{matching_attempt.pk}/'
        response = client.get(url)
        assert_login_redirect(response)

    def test_authenticated_gets_200(self, client, user, matching_attempt):
        client.force_login(user)
        response = client.get(f'/matching/matching/{matching_attempt.pk}/')
        assert response.status_code == 200


# ── RequestToCoachDetailView (/matching/request-to-coach/<pk>/) ──────────────

@pytest.mark.django_db
class TestRequestToCoachDetailView:

    def test_unauthenticated_redirects_to_login(self, client, request_to_coach):
        url = f'/matching/request-to-coach/{request_to_coach.pk}/'
        response = client.get(url)
        assert_login_redirect(response)

    def test_authenticated_gets_200(self, client, user, request_to_coach):
        client.force_login(user)
        response = client.get(f'/matching/request-to-coach/{request_to_coach.pk}/')
        assert response.status_code == 200
