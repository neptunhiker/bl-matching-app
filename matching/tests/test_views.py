"""
Auth-gating tests for all login-required views, plus CoachRespondView.

Covers for each protected URL:
  1. Unauthenticated request  → 302 redirect to the login page
  2. Authenticated request    → 200 OK

Additionally, for MatchingAttemptCreateView (staff-only):
  3. Non-staff authenticated  → 403 Forbidden
  4. Staff authenticated      → 200 OK

CoachRespondView (public, token-gated):
  - Invalid token         → invalid template
  - Accept on time        → ACCEPTED_ON_TIME + success template
  - Accept late           → ACCEPTED_LATE + success template
  - Decline on time       → REJECTED_ON_TIME + success template
  - Token already used    → already-used template, status unchanged
  - Terminal status guard → already-used template (cross-email scenario)
  - No deadline           → treated as on-time
"""
import secrets
from datetime import timedelta

import pytest
from django.utils import timezone

from accounts.models import User
from matching.models import CoachActionToken, MatchingAttempt, RequestToCoach
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
        priority=10,
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


# ── CoachRespondView (/matching/response_coach/<token>/) ──────────────────────

@pytest.mark.django_db
class TestCoachRespondView:

    def _make_token(self, request_to_coach, action, used_at=None):
        return CoachActionToken.objects.create(
            token=secrets.token_urlsafe(48),
            request_to_coach=request_to_coach,
            action=action,
            used_at=used_at,
        )

    def _url(self, token_str):
        return f'/matching/response_coach/{token_str}/'

    # ── Invalid token ─────────────────────────────────────────────────────────

    def test_invalid_token_renders_invalid_template(self, client):
        response = client.get(self._url('notavalidtoken'))
        assert response.status_code == 200
        assert 'matching/coach_response_invalid.html' in [t.name for t in response.templates]

    # ── Accept / Decline — on time ────────────────────────────────────────────

    def test_accept_on_time(self, client, request_to_coach):
        request_to_coach.deadline_at = timezone.now() + timedelta(hours=1)
        request_to_coach.save()
        token = self._make_token(request_to_coach, CoachActionToken.Action.ACCEPT)

        response = client.get(self._url(token.token))

        assert response.status_code == 200
        assert 'matching/coach_response_success.html' in [t.name for t in response.templates]
        request_to_coach.refresh_from_db()
        assert request_to_coach.status == RequestToCoach.Status.ACCEPTED_ON_TIME

    def test_decline_on_time(self, client, request_to_coach):
        request_to_coach.deadline_at = timezone.now() + timedelta(hours=1)
        request_to_coach.save()
        token = self._make_token(request_to_coach, CoachActionToken.Action.DECLINE)

        response = client.get(self._url(token.token))

        assert response.status_code == 200
        assert 'matching/coach_response_success.html' in [t.name for t in response.templates]
        request_to_coach.refresh_from_db()
        assert request_to_coach.status == RequestToCoach.Status.REJECTED_ON_TIME

    # ── Accept / Decline — late ───────────────────────────────────────────────

    def test_accept_late(self, client, request_to_coach):
        request_to_coach.deadline_at = timezone.now() - timedelta(hours=1)
        request_to_coach.save()
        token = self._make_token(request_to_coach, CoachActionToken.Action.ACCEPT)

        response = client.get(self._url(token.token))

        assert response.status_code == 200
        request_to_coach.refresh_from_db()
        assert request_to_coach.status == RequestToCoach.Status.ACCEPTED_LATE

    def test_decline_late(self, client, request_to_coach):
        request_to_coach.deadline_at = timezone.now() - timedelta(hours=1)
        request_to_coach.save()
        token = self._make_token(request_to_coach, CoachActionToken.Action.DECLINE)

        response = client.get(self._url(token.token))

        assert response.status_code == 200
        request_to_coach.refresh_from_db()
        assert request_to_coach.status == RequestToCoach.Status.REJECTED_LATE

    # ── No deadline → on time ─────────────────────────────────────────────────

    def test_no_deadline_treated_as_on_time(self, client, request_to_coach):
        assert request_to_coach.deadline_at is None
        token = self._make_token(request_to_coach, CoachActionToken.Action.ACCEPT)

        response = client.get(self._url(token.token))

        assert response.status_code == 200
        request_to_coach.refresh_from_db()
        assert request_to_coach.status == RequestToCoach.Status.ACCEPTED_ON_TIME

    # ── Already-used token ────────────────────────────────────────────────────

    def test_already_used_token_shows_already_used_template(self, client, request_to_coach):
        token = self._make_token(
            request_to_coach,
            CoachActionToken.Action.ACCEPT,
            used_at=timezone.now() - timedelta(minutes=5),
        )

        response = client.get(self._url(token.token))

        assert response.status_code == 200
        assert 'matching/coach_response_already_used.html' in [t.name for t in response.templates]

    def test_already_used_token_does_not_change_status(self, client, request_to_coach):
        token = self._make_token(
            request_to_coach,
            CoachActionToken.Action.ACCEPT,
            used_at=timezone.now() - timedelta(minutes=5),
        )
        original_status = request_to_coach.status

        client.get(self._url(token.token))

        request_to_coach.refresh_from_db()
        assert request_to_coach.status == original_status

    # ── Terminal status guard (cross-email scenario) ──────────────────────────

    def test_terminal_status_shows_already_used_template(self, client, request_to_coach):
        # Coach already responded via a different token; this new (unused) token
        # should still land on already-used because the RTC is resolved.
        request_to_coach.status = RequestToCoach.Status.ACCEPTED_ON_TIME
        request_to_coach.save()
        token = self._make_token(request_to_coach, CoachActionToken.Action.DECLINE)

        response = client.get(self._url(token.token))

        assert response.status_code == 200
        assert 'matching/coach_response_already_used.html' in [t.name for t in response.templates]

    def test_terminal_status_does_not_change_status(self, client, request_to_coach):
        request_to_coach.status = RequestToCoach.Status.REJECTED_ON_TIME
        request_to_coach.save()
        token = self._make_token(request_to_coach, CoachActionToken.Action.ACCEPT)

        client.get(self._url(token.token))

        request_to_coach.refresh_from_db()
        assert request_to_coach.status == RequestToCoach.Status.REJECTED_ON_TIME
