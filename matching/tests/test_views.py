import pytest

from django.contrib.messages import get_messages
from django.urls import reverse

from matching.models import MatchingAttempt
from profiles.models import Participant

@pytest.mark.django_db
def test_matching_attempts_access_anonymous(client):
    url = reverse('matching_attempts')
    r = client.get(url)
    assert r.status_code == 302


@pytest.mark.django_db
def test_matching_attempts_access_user(client, coach_user):
    client.force_login(coach_user)
    url = reverse('matching_attempts')
    r = client.get(url)
    assert r.status_code == 200


@pytest.mark.django_db
def test_matching_attempts_access_staff(client, staff_user):
    client.force_login(staff_user)
    url = reverse('matching_attempts')
    r = client.get(url)
    assert r.status_code == 200


@pytest.mark.django_db
def test_matching_attempts_access_superuser(client):
    from accounts.models import User
    su = User.objects.create_superuser(email='su@example.com', password='pw')
    client.force_login(su)
    url = reverse('matching_attempts')
    r = client.get(url)
    assert r.status_code == 200


@pytest.mark.django_db
def test_matching_attempt_create_access_anonymous(client):
    url = reverse('matching_attempt_create')
    r = client.get(url)
    assert r.status_code == 302


@pytest.mark.django_db
def test_matching_attempt_create_access_user(client, coach_user):
    client.force_login(coach_user)
    url = reverse('matching_attempt_create')
    r = client.get(url)
    assert r.status_code == 403


@pytest.mark.django_db
def test_matching_attempt_create_access_staff(client, staff_user):
    client.force_login(staff_user)
    url = reverse('matching_attempt_create')
    r = client.get(url)
    assert r.status_code == 200


@pytest.mark.django_db
def test_matching_attempt_create_access_superuser(client):
    from accounts.models import User
    su = User.objects.create_superuser(email='su2@example.com', password='pw')
    client.force_login(su)
    url = reverse('matching_attempt_create')
    r = client.get(url)
    assert r.status_code == 200


@pytest.mark.django_db
def test_matching_attempt_detail_access_anonymous(client, matching_attempt):
    url = reverse('matching_attempt_detail', kwargs={'pk': matching_attempt.pk})
    r = client.get(url)
    assert r.status_code == 302


@pytest.mark.django_db
def test_matching_attempt_detail_access_user(client, coach_user, matching_attempt):
    client.force_login(coach_user)
    url = reverse('matching_attempt_detail', kwargs={'pk': matching_attempt.pk})
    r = client.get(url)
    assert r.status_code == 200


@pytest.mark.django_db
def test_matching_attempt_detail_access_staff(client, staff_user, matching_attempt):
    client.force_login(staff_user)
    url = reverse('matching_attempt_detail', kwargs={'pk': matching_attempt.pk})
    r = client.get(url)
    assert r.status_code == 200


@pytest.mark.django_db
def test_matching_attempt_detail_access_superuser(client, matching_attempt):
    from accounts.models import User
    su = User.objects.create_superuser(email='su3@example.com', password='pw')
    client.force_login(su)
    url = reverse('matching_attempt_detail', kwargs={'pk': matching_attempt.pk})
    r = client.get(url)
    assert r.status_code == 200


@pytest.mark.django_db
def test_start_matching_access_anonymous(client, matching_attempt):
    url = reverse('matching_attempt_start', kwargs={'pk': matching_attempt.pk})
    r = client.post(url)
    assert r.status_code == 302


@pytest.mark.django_db
def test_start_matching_access_user(client, coach_user, matching_attempt):
    client.force_login(coach_user)
    url = reverse('matching_attempt_start', kwargs={'pk': matching_attempt.pk})
    r = client.post(url)
    assert r.status_code == 403


@pytest.mark.django_db
def test_start_matching_access_staff(client, staff_user, matching_attempt, monkeypatch):
    # avoid side-effects from actual start_matching implementation
    monkeypatch.setattr(MatchingAttempt, 'start_matching', lambda self, *a, **k: None)
    client.force_login(staff_user)
    url = reverse('matching_attempt_start', kwargs={'pk': matching_attempt.pk})
    r = client.post(url)
    assert r.status_code in (302, 200)


@pytest.mark.django_db
def test_start_matching_access_superuser(client, matching_attempt, monkeypatch):
    from accounts.models import User
    su = User.objects.create_superuser(email='su4@example.com', password='pw')
    monkeypatch.setattr(MatchingAttempt, 'start_matching', lambda self, *a, **k: None)
    client.force_login(su)
    url = reverse('matching_attempt_start', kwargs={'pk': matching_attempt.pk})
    r = client.post(url)
    assert r.status_code in (302, 200)


@pytest.mark.django_db
def test_toggle_automation_access_anonymous(client, matching_attempt):
    url = reverse('matching_attempt_automation', kwargs={'pk': matching_attempt.pk})
    r = client.post(url, data={'action': 'enable'})
    assert r.status_code == 302


@pytest.mark.django_db
def test_toggle_automation_access_user(client, coach_user, matching_attempt):
    client.force_login(coach_user)
    url = reverse('matching_attempt_automation', kwargs={'pk': matching_attempt.pk})
    r = client.post(url, data={'action': 'enable'})
    assert r.status_code == 403


@pytest.mark.django_db
def test_toggle_automation_access_staff(client, staff_user, matching_attempt, monkeypatch):
    monkeypatch.setattr(MatchingAttempt, 'enable_automation', lambda self, *a, **k: None)
    monkeypatch.setattr(MatchingAttempt, 'disable_automation', lambda self, *a, **k: None)
    client.force_login(staff_user)
    url = reverse('matching_attempt_automation', kwargs={'pk': matching_attempt.pk})
    r = client.post(url, data={'action': 'enable'})
    assert r.status_code in (302, 200)


@pytest.mark.django_db
def test_toggle_automation_access_superuser(client, matching_attempt, monkeypatch):
    from accounts.models import User
    su = User.objects.create_superuser(email='su5@example.com', password='pw')
    monkeypatch.setattr(MatchingAttempt, 'enable_automation', lambda self, *a, **k: None)
    client.force_login(su)
    url = reverse('matching_attempt_automation', kwargs={'pk': matching_attempt.pk})
    r = client.post(url, data={'action': 'enable'})
    assert r.status_code in (302, 200)


@pytest.mark.django_db
def test_request_to_coach_create_access_anonymous(client, matching_attempt):
    url = reverse('request_to_coach_create', kwargs={'pk': matching_attempt.pk})
    r = client.get(url)
    assert r.status_code == 302


@pytest.mark.django_db
def test_request_to_coach_create_access_user(client, coach_user, matching_attempt):
    client.force_login(coach_user)
    url = reverse('request_to_coach_create', kwargs={'pk': matching_attempt.pk})
    r = client.get(url)
    assert r.status_code == 403


@pytest.mark.django_db
def test_request_to_coach_create_access_staff(client, staff_user, matching_attempt):
    client.force_login(staff_user)
    url = reverse('request_to_coach_create', kwargs={'pk': matching_attempt.pk})
    r = client.get(url)
    assert r.status_code == 200


@pytest.mark.django_db
def test_request_to_coach_create_access_superuser(client, matching_attempt):
    from accounts.models import User
    su = User.objects.create_superuser(email='su6@example.com', password='pw')
    client.force_login(su)
    url = reverse('request_to_coach_create', kwargs={'pk': matching_attempt.pk})
    r = client.get(url)
    assert r.status_code == 200


@pytest.mark.django_db
def test_coach_autocomplete_access_anonymous(client):
    url = reverse('coach_autocomplete')
    r = client.get(url)
    assert r.status_code == 302


@pytest.mark.django_db
def test_coach_autocomplete_access_user(client, coach_user):
    client.force_login(coach_user)
    url = reverse('coach_autocomplete')
    r = client.get(url)
    assert r.status_code == 403


@pytest.mark.django_db
def test_coach_autocomplete_access_staff(client, staff_user):
    client.force_login(staff_user)
    url = reverse('coach_autocomplete')
    r = client.get(url)
    assert r.status_code == 200


@pytest.mark.django_db
def test_coach_autocomplete_access_superuser(client):
    from accounts.models import User
    su = User.objects.create_superuser(email='su7@example.com', password='pw')
    client.force_login(su)
    url = reverse('coach_autocomplete')
    r = client.get(url)
    assert r.status_code == 200


@pytest.mark.django_db
def test_request_to_coach_detail_access_anonymous(client, rtc):
    url = reverse('request_to_coach_detail', kwargs={'pk': rtc.pk})
    r = client.get(url)
    assert r.status_code == 302


@pytest.mark.django_db
def test_request_to_coach_detail_access_user(client, coach_user, rtc):
    client.force_login(coach_user)
    url = reverse('request_to_coach_detail', kwargs={'pk': rtc.pk})
    r = client.get(url)
    assert r.status_code == 200


@pytest.mark.django_db
def test_request_to_coach_detail_access_staff(client, staff_user, rtc):
    client.force_login(staff_user)
    url = reverse('request_to_coach_detail', kwargs={'pk': rtc.pk})
    r = client.get(url)
    assert r.status_code == 200


@pytest.mark.django_db
def test_request_to_coach_detail_access_superuser(client, rtc):
    from accounts.models import User
    su = User.objects.create_superuser(email='su8@example.com', password='pw')
    client.force_login(su)
    url = reverse('request_to_coach_detail', kwargs={'pk': rtc.pk})
    r = client.get(url)
    assert r.status_code == 200


@pytest.mark.django_db
def test_coach_respond_public_anonymous(client):
    url = reverse('coach_respond', kwargs={'token': 'invalid'})
    r = client.get(url)
    assert r.status_code == 200


@pytest.mark.django_db
def test_coach_respond_public_user(client, coach_user):
    client.force_login(coach_user)
    url = reverse('coach_respond', kwargs={'token': 'invalid'})
    r = client.get(url)
    assert r.status_code == 200


@pytest.mark.django_db
def test_coach_respond_public_staff(client, staff_user):
    client.force_login(staff_user)
    url = reverse('coach_respond', kwargs={'token': 'invalid'})
    r = client.get(url)
    assert r.status_code == 200


@pytest.mark.django_db
def test_coach_respond_public_superuser(client):
    from accounts.models import User
    su = User.objects.create_superuser(email='su9@example.com', password='pw')
    client.force_login(su)
    url = reverse('coach_respond', kwargs={'token': 'invalid'})
    r = client.get(url)
    assert r.status_code == 200


@pytest.mark.django_db
def test_create_matching_shows_error_when_active_exists(client, staff_user):

    client.force_login(staff_user)

    participant = Participant.objects.create(first_name='T', last_name='ester')
    # existing active matching
    MatchingAttempt.objects.create(participant=participant)

    url = reverse('matching_attempt_create')
    r = client.post(url, data={'participant': str(participant.pk)})

    # form invalid returns 200 and shows our message
    assert r.status_code == 200
    messages = list(get_messages(r.wsgi_request))
    assert any('aktives Matching' in str(m) for m in messages)


@pytest.mark.django_db
def test_request_to_coach_edit_access_anonymous(client, rtc):
    url = reverse('request_to_coach_edit', kwargs={'pk': rtc.pk})
    r = client.get(url)
    assert r.status_code == 302


@pytest.mark.django_db
def test_request_to_coach_edit_access_user(client, coach_user, rtc):
    client.force_login(coach_user)
    url = reverse('request_to_coach_edit', kwargs={'pk': rtc.pk})
    r = client.get(url)
    assert r.status_code == 403


@pytest.mark.django_db
def test_request_to_coach_edit_access_staff(client, staff_user, rtc):
    client.force_login(staff_user)
    url = reverse('request_to_coach_edit', kwargs={'pk': rtc.pk})
    r = client.get(url)
    assert r.status_code == 200


@pytest.mark.django_db
def test_request_to_coach_edit_access_superuser(client, rtc):
    from accounts.models import User
    su = User.objects.create_superuser(email='su10@example.com', password='pw')
    client.force_login(su)
    url = reverse('request_to_coach_edit', kwargs={'pk': rtc.pk})
    r = client.get(url)
    assert r.status_code == 200


@pytest.mark.django_db
def test_request_to_coach_delete_access_anonymous(client, rtc):
    url = reverse('request_to_coach_delete', kwargs={'pk': rtc.pk})
    r = client.get(url)
    assert r.status_code == 302


@pytest.mark.django_db
def test_request_to_coach_delete_access_user(client, coach_user, rtc):
    client.force_login(coach_user)
    url = reverse('request_to_coach_delete', kwargs={'pk': rtc.pk})
    r = client.get(url)
    assert r.status_code == 403


@pytest.mark.django_db
def test_request_to_coach_delete_access_staff(client, staff_user, rtc):
    client.force_login(staff_user)
    url = reverse('request_to_coach_delete', kwargs={'pk': rtc.pk})
    r = client.get(url)
    assert r.status_code == 200


@pytest.mark.django_db
def test_request_to_coach_delete_access_superuser(client, rtc):
    from accounts.models import User
    su = User.objects.create_superuser(email='su11@example.com', password='pw')
    client.force_login(su)
    url = reverse('request_to_coach_delete', kwargs={'pk': rtc.pk})
    r = client.get(url)
    assert r.status_code == 200
