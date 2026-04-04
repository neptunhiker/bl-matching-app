import datetime
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
    assert r.status_code == 403


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
    assert r.status_code == 403


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
def test_request_to_coach_detail_access_anonymous(client, rtc):
    url = reverse('request_to_coach_detail', kwargs={'pk': rtc.pk})
    r = client.get(url)
    assert r.status_code == 302


@pytest.mark.django_db
def test_request_to_coach_detail_access_user(client, coach_user, rtc):
    client.force_login(coach_user)
    url = reverse('request_to_coach_detail', kwargs={'pk': rtc.pk})
    r = client.get(url)
    assert r.status_code == 403


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
def test_create_matching_shows_error_when_active_exists(client, staff_user, bl_staff, participant):
    MatchingAttempt.objects.create(participant=participant, ue=48)
    client.force_login(staff_user)
    url = reverse('matching_attempt_create')
    r = client.post(url, data={'participant': participant.pk, 'ue': 40, 'bl_contact': bl_staff.pk})
    assert r.status_code == 200
    msgs = list(get_messages(r.wsgi_request))
    assert any("aktives Matching" in str(m) for m in msgs)


@pytest.mark.django_db
def test_create_matching_success(client, staff_user, bl_staff, participant):
    client.force_login(staff_user)
    url = reverse('matching_attempt_create')
    r = client.post(url, data={'participant': participant.pk, 'ue': 40, 'bl_contact': bl_staff.pk})
    assert r.status_code == 302
    new_ma = MatchingAttempt.objects.get(participant=participant, ue=40)
    assert r['Location'] == reverse('matching_attempt_detail', kwargs={'pk': new_ma.pk})


@pytest.mark.django_db
def test_create_matching_invalid_ue(client, staff_user, bl_staff, participant):
    client.force_login(staff_user)
    url = reverse('matching_attempt_create')
    r = client.post(url, data={'participant': participant.pk, 'ue': 0, 'bl_contact': bl_staff.pk})
    assert r.status_code == 200


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


# ── MatchingAttemptDeleteView ────────────────────────────────────────────────

@pytest.mark.django_db
def test_matching_attempt_delete_access_anonymous(client, matching_attempt):
    url = reverse('matching_attempt_delete', kwargs={'pk': matching_attempt.pk})
    r = client.get(url)
    assert r.status_code == 302


@pytest.mark.django_db
def test_matching_attempt_delete_access_user(client, coach_user, matching_attempt):
    client.force_login(coach_user)
    url = reverse('matching_attempt_delete', kwargs={'pk': matching_attempt.pk})
    r = client.get(url)
    assert r.status_code == 403


@pytest.mark.django_db
def test_matching_attempt_delete_access_staff(client, staff_user, matching_attempt):
    client.force_login(staff_user)
    url = reverse('matching_attempt_delete', kwargs={'pk': matching_attempt.pk})
    r = client.get(url)
    assert r.status_code == 200


@pytest.mark.django_db
def test_matching_attempt_delete_access_superuser(client, matching_attempt):
    from accounts.models import User
    su = User.objects.create_superuser(email='su_del@example.com', password='pw')
    client.force_login(su)
    url = reverse('matching_attempt_delete', kwargs={'pk': matching_attempt.pk})
    r = client.get(url)
    assert r.status_code == 200


# ── ResumeMatchingView ───────────────────────────────────────────────────────

@pytest.mark.django_db
def test_resume_matching_access_anonymous(client, matching_attempt):
    url = reverse('matching_attempt_resume', kwargs={'pk': matching_attempt.pk})
    r = client.post(url)
    assert r.status_code == 302


@pytest.mark.django_db
def test_resume_matching_access_user(client, coach_user, matching_attempt):
    client.force_login(coach_user)
    url = reverse('matching_attempt_resume', kwargs={'pk': matching_attempt.pk})
    r = client.post(url)
    assert r.status_code == 403


@pytest.mark.django_db
def test_resume_matching_access_staff(client, staff_user, matching_attempt, monkeypatch):
    monkeypatch.setattr(MatchingAttempt, 'resume_matching', lambda self, *a, **k: None)
    client.force_login(staff_user)
    url = reverse('matching_attempt_resume', kwargs={'pk': matching_attempt.pk})
    r = client.post(url)
    assert r.status_code in (302, 200)


@pytest.mark.django_db
def test_resume_matching_access_superuser(client, matching_attempt, monkeypatch):
    from accounts.models import User
    su = User.objects.create_superuser(email='su_res@example.com', password='pw')
    monkeypatch.setattr(MatchingAttempt, 'resume_matching', lambda self, *a, **k: None)
    client.force_login(su)
    url = reverse('matching_attempt_resume', kwargs={'pk': matching_attempt.pk})
    r = client.post(url)
    assert r.status_code in (302, 200)


# ── CancelMatchingView ───────────────────────────────────────────────────────

@pytest.mark.django_db
def test_cancel_matching_access_anonymous(client, matching_attempt):
    url = reverse('matching_attempt_cancel', kwargs={'pk': matching_attempt.pk})
    r = client.post(url)
    assert r.status_code == 302


@pytest.mark.django_db
def test_cancel_matching_access_user(client, coach_user, matching_attempt):
    client.force_login(coach_user)
    url = reverse('matching_attempt_cancel', kwargs={'pk': matching_attempt.pk})
    r = client.post(url)
    assert r.status_code == 403


@pytest.mark.django_db
def test_cancel_matching_access_staff(client, staff_user, matching_attempt, monkeypatch):
    import matching.services as svc
    monkeypatch.setattr(svc, 'cancel_matching', lambda *a, **k: None)
    client.force_login(staff_user)
    url = reverse('matching_attempt_cancel', kwargs={'pk': matching_attempt.pk})
    r = client.post(url)
    assert r.status_code in (302, 200)


@pytest.mark.django_db
def test_cancel_matching_access_superuser(client, matching_attempt, monkeypatch):
    from accounts.models import User
    import matching.services as svc
    su = User.objects.create_superuser(email='su_can@example.com', password='pw')
    monkeypatch.setattr(svc, 'cancel_matching', lambda *a, **k: None)
    client.force_login(su)
    url = reverse('matching_attempt_cancel', kwargs={'pk': matching_attempt.pk})
    r = client.post(url)
    assert r.status_code in (302, 200)


# ── ParticipantRespondView (public) ──────────────────────────────────────────

@pytest.mark.django_db
def test_participant_respond_public_anonymous(client):
    url = reverse('participant_respond', kwargs={'token': 'invalid'})
    r = client.get(url)
    assert r.status_code == 200


@pytest.mark.django_db
def test_participant_respond_public_user(client, coach_user):
    client.force_login(coach_user)
    url = reverse('participant_respond', kwargs={'token': 'invalid'})
    r = client.get(url)
    assert r.status_code == 200


@pytest.mark.django_db
def test_participant_respond_public_staff(client, staff_user):
    client.force_login(staff_user)
    url = reverse('participant_respond', kwargs={'token': 'invalid'})
    r = client.get(url)
    assert r.status_code == 200


@pytest.mark.django_db
def test_participant_respond_public_superuser(client):
    from accounts.models import User
    su = User.objects.create_superuser(email='su_pr@example.com', password='pw')
    client.force_login(su)
    url = reverse('participant_respond', kwargs={'token': 'invalid'})
    r = client.get(url)
    assert r.status_code == 200


# ── ConfirmIntroCallView (public) ────────────────────────────────────────────

@pytest.mark.django_db
def test_confirm_intro_call_public_anonymous(client):
    url = reverse('confirm_intro_call', kwargs={'token': 'invalid'})
    r = client.get(url)
    assert r.status_code == 200


@pytest.mark.django_db
def test_confirm_intro_call_public_user(client, coach_user):
    client.force_login(coach_user)
    url = reverse('confirm_intro_call', kwargs={'token': 'invalid'})
    r = client.get(url)
    assert r.status_code == 200


@pytest.mark.django_db
def test_confirm_intro_call_public_staff(client, staff_user):
    client.force_login(staff_user)
    url = reverse('confirm_intro_call', kwargs={'token': 'invalid'})
    r = client.get(url)
    assert r.status_code == 200


@pytest.mark.django_db
def test_confirm_intro_call_public_superuser(client):
    from accounts.models import User
    su = User.objects.create_superuser(email='su_cic@example.com', password='pw')
    client.force_login(su)
    url = reverse('confirm_intro_call', kwargs={'token': 'invalid'})
    r = client.get(url)
    assert r.status_code == 200


# ── MatchingEventDetailView ──────────────────────────────────────────────────

@pytest.mark.django_db
def test_matching_event_detail_access_anonymous(client, matching_event):
    url = reverse('matching_event_detail', kwargs={'pk': matching_event.pk})
    r = client.get(url)
    assert r.status_code == 302


@pytest.mark.django_db
def test_matching_event_detail_access_user(client, coach_user, matching_event):
    client.force_login(coach_user)
    url = reverse('matching_event_detail', kwargs={'pk': matching_event.pk})
    r = client.get(url)
    assert r.status_code == 403


@pytest.mark.django_db
def test_matching_event_detail_access_staff(client, staff_user, matching_event):
    client.force_login(staff_user)
    url = reverse('matching_event_detail', kwargs={'pk': matching_event.pk})
    r = client.get(url)
    assert r.status_code == 200


@pytest.mark.django_db
def test_matching_event_detail_access_superuser(client, matching_event):
    from accounts.models import User
    su = User.objects.create_superuser(email='su_med@example.com', password='pw')
    client.force_login(su)
    url = reverse('matching_event_detail', kwargs={'pk': matching_event.pk})
    r = client.get(url)
    assert r.status_code == 200


# ── ManualOverrideMatchingView ───────────────────────────────────────────────

@pytest.mark.django_db
def test_manual_override_access_anonymous(client, matching_attempt):
    url = reverse('manual_override_matching', kwargs={'matching_attempt_pk': matching_attempt.pk})
    r = client.get(url)
    assert r.status_code == 302


@pytest.mark.django_db
def test_manual_override_access_user(client, coach_user, matching_attempt):
    client.force_login(coach_user)
    url = reverse('manual_override_matching', kwargs={'matching_attempt_pk': matching_attempt.pk})
    r = client.get(url)
    assert r.status_code == 403


@pytest.mark.django_db
def test_manual_override_access_staff(client, staff_user, matching_attempt):
    client.force_login(staff_user)
    url = reverse('manual_override_matching', kwargs={'matching_attempt_pk': matching_attempt.pk})
    r = client.get(url)
    assert r.status_code == 200


@pytest.mark.django_db
def test_manual_override_access_superuser(client, matching_attempt):
    from accounts.models import User
    su = User.objects.create_superuser(email='su_mo@example.com', password='pw')
    client.force_login(su)
    url = reverse('manual_override_matching', kwargs={'matching_attempt_pk': matching_attempt.pk})
    r = client.get(url)
    assert r.status_code == 200


# ── FlowChartView ────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_flow_chart_access_anonymous(client):
    url = reverse('matching_flow_chart')
    r = client.get(url)
    assert r.status_code == 302


@pytest.mark.django_db
def test_flow_chart_access_user(client, coach_user):
    client.force_login(coach_user)
    url = reverse('matching_flow_chart')
    r = client.get(url)
    assert r.status_code == 403


@pytest.mark.django_db
def test_flow_chart_access_staff(client, staff_user):
    client.force_login(staff_user)
    url = reverse('matching_flow_chart')
    r = client.get(url)
    assert r.status_code == 200


@pytest.mark.django_db
def test_flow_chart_access_superuser(client):
    from accounts.models import User
    su = User.objects.create_superuser(email='su_fc@example.com', password='pw')
    client.force_login(su)
    url = reverse('matching_flow_chart')
    r = client.get(url)
    assert r.status_code == 200


# ── MatchingAttemptDeleteView (POST) ─────────────────────────────────────────

@pytest.mark.django_db
def test_matching_attempt_delete_post_staff(client, staff_user, matching_attempt):
    pk = matching_attempt.pk
    client.force_login(staff_user)
    url = reverse('matching_attempt_delete', kwargs={'pk': pk})
    r = client.post(url)
    assert r.status_code == 302
    assert r['Location'] == reverse('matching_attempts')
    assert not MatchingAttempt.objects.filter(pk=pk).exists()


# ── StartMatchingView (POST) ──────────────────────────────────────────────────

@pytest.mark.django_db
def test_start_matching_valid_state(client, staff_user, matching_attempt, monkeypatch):
    monkeypatch.setattr(MatchingAttempt, 'start_matching', lambda self, *a, **k: None)
    client.force_login(staff_user)
    url = reverse('matching_attempt_start', kwargs={'pk': matching_attempt.pk})
    r = client.post(url)
    assert r.status_code == 302
    assert r['Location'] == reverse('matching_attempt_detail', kwargs={'pk': matching_attempt.pk})


@pytest.mark.django_db
def test_start_matching_invalid_state(client, staff_user, matching_attempt, monkeypatch):
    from django_fsm import TransitionNotAllowed
    monkeypatch.setattr(MatchingAttempt, 'start_matching', lambda self, *a, **k: (_ for _ in ()).throw(TransitionNotAllowed()))
    client.force_login(staff_user)
    url = reverse('matching_attempt_start', kwargs={'pk': matching_attempt.pk})
    r = client.post(url)
    assert r.status_code == 302
    msgs = list(get_messages(r.wsgi_request))
    assert len(msgs) == 1


# ── CancelMatchingView (POST) ─────────────────────────────────────────────────

@pytest.mark.django_db
def test_cancel_matching(client, staff_user, matching_attempt, monkeypatch):
    import matching.services as svc
    monkeypatch.setattr(svc, 'cancel_matching', lambda *a, **k: None)
    client.force_login(staff_user)
    url = reverse('matching_attempt_cancel', kwargs={'pk': matching_attempt.pk})
    r = client.post(url)
    assert r.status_code == 302
    assert r['Location'] == reverse('matching_attempt_detail', kwargs={'pk': matching_attempt.pk})


# ── ResumeMatchingView (POST) ─────────────────────────────────────────────────

@pytest.mark.django_db
def test_resume_matching_valid_state(client, staff_user, matching_attempt, monkeypatch):
    monkeypatch.setattr(MatchingAttempt, 'resume_matching', lambda self, *a, **k: None)
    client.force_login(staff_user)
    url = reverse('matching_attempt_resume', kwargs={'pk': matching_attempt.pk})
    r = client.post(url)
    assert r.status_code == 302
    assert r['Location'] == reverse('matching_attempt_detail', kwargs={'pk': matching_attempt.pk})


@pytest.mark.django_db
def test_resume_matching_invalid_state(client, staff_user, matching_attempt, monkeypatch):
    from django_fsm import TransitionNotAllowed
    monkeypatch.setattr(MatchingAttempt, 'resume_matching', lambda self, *a, **k: (_ for _ in ()).throw(TransitionNotAllowed()))
    client.force_login(staff_user)
    url = reverse('matching_attempt_resume', kwargs={'pk': matching_attempt.pk})
    r = client.post(url)
    assert r.status_code == 302
    msgs = list(get_messages(r.wsgi_request))
    assert len(msgs) == 1


# ── RequestToCoachCreateView (GET / POST) ─────────────────────────────────────

@pytest.mark.django_db
def test_rtc_create_get_shows_available_coaches(client, staff_user, matching_attempt, coach):
    from profiles.models import Coach
    coach.status = Coach.Status.AVAILABLE
    coach.save()
    client.force_login(staff_user)
    url = reverse('request_to_coach_create', kwargs={'pk': matching_attempt.pk})
    r = client.get(url)
    assert r.status_code == 200
    assert len(r.context['available_coaches']) > 0


@pytest.mark.django_db
def test_rtc_create_post_valid(client, staff_user, matching_attempt, coach, monkeypatch):
    import matching.services as svc
    from profiles.models import Coach
    coach.status = Coach.Status.AVAILABLE
    coach.save()
    monkeypatch.setattr(svc, 'create_request_to_coach', lambda *a, **k: None)
    client.force_login(staff_user)
    url = reverse('request_to_coach_create', kwargs={'pk': matching_attempt.pk})
    r = client.post(url, data={
        'coach_id': str(coach.pk),
        'ue': 40,
        'priority': 10,
        'max_number_of_requests': 3,
    })
    assert r.status_code == 302
    assert r['Location'] == reverse('matching_attempt_detail', kwargs={'pk': matching_attempt.pk})


@pytest.mark.django_db
def test_rtc_create_post_invalid_missing_coach(client, staff_user, matching_attempt):
    client.force_login(staff_user)
    url = reverse('request_to_coach_create', kwargs={'pk': matching_attempt.pk})
    r = client.post(url, data={'ue': 40, 'priority': 10, 'max_number_of_requests': 3})
    assert r.status_code == 200
    assert 'errors' in r.context
    assert 'coach' in r.context['errors']

@pytest.mark.django_db
def test_toggle_automation_enable(client, staff_user, matching_attempt, monkeypatch):
    monkeypatch.setattr(MatchingAttempt, 'enable_automation', lambda self, *a, **k: None)
    client.force_login(staff_user)
    url = reverse('matching_attempt_automation', kwargs={'pk': matching_attempt.pk})
    r = client.post(url, data={'action': 'enable'})
    assert r.status_code == 302
    assert r['Location'] == reverse('matching_attempt_detail', kwargs={'pk': matching_attempt.pk})


@pytest.mark.django_db
def test_toggle_automation_disable(client, staff_user, matching_attempt, monkeypatch):
    monkeypatch.setattr(MatchingAttempt, 'disable_automation', lambda self, *a, **k: None)
    client.force_login(staff_user)
    url = reverse('matching_attempt_automation', kwargs={'pk': matching_attempt.pk})
    r = client.post(url, data={'action': 'disable'})
    assert r.status_code == 302
    assert r['Location'] == reverse('matching_attempt_detail', kwargs={'pk': matching_attempt.pk})


@pytest.mark.django_db
def test_toggle_automation_invalid_action(client, staff_user, matching_attempt):
    client.force_login(staff_user)
    url = reverse('matching_attempt_automation', kwargs={'pk': matching_attempt.pk})
    r = client.post(url, data={'action': 'foobar'})
    assert r.status_code == 302
    msgs = list(get_messages(r.wsgi_request))
    assert len(msgs) == 1


# ── RequestToCoachUpdateView (POST) ──────────────────────────────────────────

@pytest.mark.django_db
def test_rtc_update_post_valid(client, staff_user, rtc):
    client.force_login(staff_user)
    url = reverse('request_to_coach_edit', kwargs={'pk': rtc.pk})
    r = client.post(url, data={'priority': 30, 'max_number_of_requests': 5})
    assert r.status_code == 302
    assert r['Location'] == reverse('matching_attempt_detail', kwargs={'pk': rtc.matching_attempt.pk})
    from matching.models import RequestToCoach
    updated = RequestToCoach.objects.get(pk=rtc.pk)
    assert updated.priority == 30
    assert updated.max_number_of_requests == 5


@pytest.mark.django_db
def test_rtc_update_post_with_next_param(client, staff_user, rtc):
    client.force_login(staff_user)
    url = reverse('request_to_coach_edit', kwargs={'pk': rtc.pk})
    r = client.post(url, data={'priority': 30, 'max_number_of_requests': 3, 'next': '/matchings/'})
    assert r.status_code == 302
    assert r['Location'] == '/matchings/'


# ── RequestToCoachDeleteView (POST) ──────────────────────────────────────────

@pytest.mark.django_db
def test_rtc_delete_creates_rtc_deleted_event(client, staff_user, rtc):
    from matching.models import MatchingEvent
    client.force_login(staff_user)
    url = reverse('request_to_coach_delete', kwargs={'pk': rtc.pk})
    client.post(url)
    assert MatchingEvent.objects.filter(
        matching_attempt=rtc.matching_attempt,
        event_type=MatchingEvent.EventType.RTC_DELETED,
    ).exists()


@pytest.mark.django_db
def test_rtc_delete_redirects_to_matching(client, staff_user, rtc):
    client.force_login(staff_user)
    url = reverse('request_to_coach_delete', kwargs={'pk': rtc.pk})
    r = client.post(url)
    assert r.status_code == 302
    assert r['Location'] == reverse('matching_attempt_detail', kwargs={'pk': rtc.matching_attempt.pk})


@pytest.mark.django_db
def test_rtc_delete_redirects_to_next(client, staff_user, rtc):
    client.force_login(staff_user)
    url = reverse('request_to_coach_delete', kwargs={'pk': rtc.pk})
    r = client.post(url, data={'next': '/matchings/'})
    assert r.status_code == 302
    assert r['Location'] == '/matchings/'


@pytest.mark.django_db
def test_rtc_delete_ignores_unsafe_next(client, staff_user, rtc):
    client.force_login(staff_user)
    url = reverse('request_to_coach_delete', kwargs={'pk': rtc.pk})
    r = client.post(url, data={'next': 'http://evil.com/steal'})
    assert r.status_code == 302
    assert r['Location'] == reverse('matching_attempt_detail', kwargs={'pk': rtc.matching_attempt.pk})


@pytest.mark.django_db
def test_rtc_delete_ignores_own_detail_as_next(client, staff_user, rtc):
    own_detail = reverse('request_to_coach_detail', kwargs={'pk': rtc.pk})
    client.force_login(staff_user)
    url = reverse('request_to_coach_delete', kwargs={'pk': rtc.pk})
    r = client.post(url, data={'next': own_detail})
    assert r.status_code == 302
    assert r['Location'] == reverse('matching_attempt_detail', kwargs={'pk': rtc.matching_attempt.pk})


# ── ManualOverrideMatchingView (GET / POST) ───────────────────────────────────

@pytest.mark.django_db
def test_manual_override_get_context(client, staff_user, matching_attempt, coach):
    from profiles.models import Coach
    coach.status = Coach.Status.AVAILABLE
    coach.save()
    client.force_login(staff_user)
    url = reverse('manual_override_matching', kwargs={'matching_attempt_pk': matching_attempt.pk})
    r = client.get(url)
    assert r.status_code == 200
    assert 'available_coaches' in r.context


@pytest.mark.django_db
def test_manual_override_post_valid(client, staff_user, matching_attempt, coach, monkeypatch):
    import matching.services as svc
    monkeypatch.setattr(svc, 'manually_match_participant_to_coach', lambda *a, **k: None)
    client.force_login(staff_user)
    url = reverse('manual_override_matching', kwargs={'matching_attempt_pk': matching_attempt.pk})
    r = client.post(url, data={'coach_id': str(coach.pk)})
    assert r.status_code == 302
    assert r['Location'] == reverse('matching_attempt_detail', kwargs={'pk': matching_attempt.pk})


# ── CoachRespondView (public token) ──────────────────────────────────────────

@pytest.mark.django_db
def test_coach_respond_invalid_token(client):
    url = reverse('coach_respond', kwargs={'token': 'no-such-token'})
    r = client.get(url)
    assert r.status_code == 200
    assert 'matching/response_invalid_token.html' in [t.name for t in r.templates]


@pytest.mark.django_db
def test_coach_respond_already_used_token(client, coach_action_token_accept):
    from django.utils import timezone as tz
    coach_action_token_accept.used_at = tz.now()
    coach_action_token_accept.save()
    url = reverse('coach_respond', kwargs={'token': coach_action_token_accept.token})
    r = client.get(url)
    assert r.status_code == 200
    assert 'matching/response_already_used.html' in [t.name for t in r.templates]


@pytest.mark.django_db
def test_coach_respond_rtc_terminal_state(client, coach_action_token_accept):
    from matching.models import RequestToCoach
    RequestToCoach.objects.filter(pk=coach_action_token_accept.request_to_coach.pk).update(
        state=RequestToCoach.State.ACCEPTED
    )
    url = reverse('coach_respond', kwargs={'token': coach_action_token_accept.token})
    r = client.get(url)
    assert r.status_code == 200
    assert 'matching/response_already_used.html' in [t.name for t in r.templates]


@pytest.mark.django_db
def test_coach_respond_accept_on_time(client, coach_action_token_accept, monkeypatch):
    import matching.services as svc
    from django.utils import timezone as tz
    import datetime
    monkeypatch.setattr(svc, 'accept_or_decline_request_to_coach', lambda *a, **k: None)
    rtc = coach_action_token_accept.request_to_coach
    future = tz.now() + datetime.timedelta(days=1)
    from matching.models import RequestToCoach
    RequestToCoach.objects.filter(pk=rtc.pk).update(deadline_at=future)
    url = reverse('coach_respond', kwargs={'token': coach_action_token_accept.token})
    r = client.get(url)
    assert r.status_code == 200
    assert 'matching/coach_response_matching_request.html' in [t.name for t in r.templates]
    assert r.context['is_accept'] is True
    assert r.context['on_time'] is True


@pytest.mark.django_db
def test_coach_respond_decline_on_time(client, coach_action_token_decline, monkeypatch):
    import matching.services as svc
    from django.utils import timezone as tz
    import datetime
    monkeypatch.setattr(svc, 'accept_or_decline_request_to_coach', lambda *a, **k: None)
    rtc = coach_action_token_decline.request_to_coach
    future = tz.now() + datetime.timedelta(days=1)
    from matching.models import RequestToCoach
    RequestToCoach.objects.filter(pk=rtc.pk).update(deadline_at=future)
    url = reverse('coach_respond', kwargs={'token': coach_action_token_decline.token})
    r = client.get(url)
    assert r.status_code == 200
    assert r.context['is_accept'] is False
    assert r.context['on_time'] is True


@pytest.mark.django_db
def test_coach_respond_accept_late(client, coach_action_token_accept, monkeypatch):
    import matching.services as svc
    from django.utils import timezone as tz
    import datetime
    monkeypatch.setattr(svc, 'accept_or_decline_request_to_coach', lambda *a, **k: None)
    rtc = coach_action_token_accept.request_to_coach
    past = tz.now() - datetime.timedelta(days=1)
    from matching.models import RequestToCoach
    RequestToCoach.objects.filter(pk=rtc.pk).update(deadline_at=past)
    url = reverse('coach_respond', kwargs={'token': coach_action_token_accept.token})
    r = client.get(url)
    assert r.status_code == 200
    assert r.context['on_time'] is False


# ── ParticipantRespondView (public token) ─────────────────────────────────────

@pytest.mark.django_db
def test_participant_respond_invalid_token(client):
    url = reverse('participant_respond', kwargs={'token': 'no-such-token'})
    r = client.get(url)
    assert r.status_code == 200
    assert 'matching/participant_response_invalid_token.html' in [t.name for t in r.templates]


@pytest.mark.django_db
def test_participant_respond_already_used(client, participant_action_token_start):
    from django.utils import timezone as tz
    participant_action_token_start.used_at = tz.now()
    participant_action_token_start.save()
    url = reverse('participant_respond', kwargs={'token': participant_action_token_start.token})
    r = client.get(url)
    assert r.status_code == 200
    assert 'matching/response_already_used.html' in [t.name for t in r.templates]


@pytest.mark.django_db
def test_participant_respond_terminal_state(client, participant_action_token_start):
    from matching.models import MatchingAttempt
    ma = participant_action_token_start.matching_attempt
    MatchingAttempt.objects.filter(pk=ma.pk).update(state=MatchingAttempt.State.MATCHING_COMPLETED)
    url = reverse('participant_respond', kwargs={'token': participant_action_token_start.token})
    r = client.get(url)
    assert r.status_code == 200
    assert 'matching/participant_response_already_used.html' in [t.name for t in r.templates]


@pytest.mark.django_db
def test_participant_respond_start_coaching(client, participant_action_token_start, monkeypatch):
    import matching.services as svc
    monkeypatch.setattr(
        svc,
        'continue_matching_after_participant_responded_to_intro_call_feedback',
        lambda *a, **k: None,
    )
    url = reverse('participant_respond', kwargs={'token': participant_action_token_start.token})
    r = client.get(url)
    assert r.status_code == 200
    assert 'matching/participant_response_coaching_can_start.html' in [t.name for t in r.templates]


@pytest.mark.django_db
def test_participant_respond_clarification(client, participant_action_token_clarify, monkeypatch):
    import matching.services as svc
    monkeypatch.setattr(
        svc,
        'continue_matching_after_participant_responded_to_intro_call_feedback',
        lambda *a, **k: None,
    )
    url = reverse('participant_respond', kwargs={'token': participant_action_token_clarify.token})
    r = client.get(url)
    assert r.status_code == 200
    assert 'matching/participant_response_clarification_needed.html' in [t.name for t in r.templates]


# ── ConfirmIntroCallView (public token) ───────────────────────────────────────

@pytest.mark.django_db
def test_confirm_intro_call_invalid_token(client):
    url = reverse('confirm_intro_call', kwargs={'token': 'no-such-token'})
    r = client.get(url)
    assert r.status_code == 200
    assert 'matching/response_invalid_token.html' in [t.name for t in r.templates]


@pytest.mark.django_db
def test_confirm_intro_call_already_used(client, coach_action_token_confirm_intro_call):
    from django.utils import timezone as tz
    coach_action_token_confirm_intro_call.used_at = tz.now()
    coach_action_token_confirm_intro_call.save()
    url = reverse('confirm_intro_call', kwargs={'token': coach_action_token_confirm_intro_call.token})
    r = client.get(url)
    assert r.status_code == 200
    assert 'matching/response_already_used.html' in [t.name for t in r.templates]


@pytest.mark.django_db
def test_confirm_intro_call_terminal_state(client, coach_action_token_confirm_intro_call):
    from matching.models import MatchingAttempt
    ma = coach_action_token_confirm_intro_call.matching_attempt
    MatchingAttempt.objects.filter(pk=ma.pk).update(state=MatchingAttempt.State.MATCHING_COMPLETED)
    url = reverse('confirm_intro_call', kwargs={'token': coach_action_token_confirm_intro_call.token})
    r = client.get(url)
    assert r.status_code == 200
    assert 'matching/response_already_used.html' in [t.name for t in r.templates]


@pytest.mark.django_db
def test_confirm_intro_call_valid(client, coach_action_token_confirm_intro_call, monkeypatch):
    import matching.services as svc
    from matching.models import MatchingAttempt, MatchingEvent
    # Put the matching attempt in the right state for the signal handler transition to succeed
    ma = coach_action_token_confirm_intro_call.matching_attempt
    MatchingAttempt.objects.filter(pk=ma.pk).update(
        state=MatchingAttempt.State.AWAITING_INTRO_CALL_FEEDBACK_FROM_COACH
    )
    # Stub out the service call that sends emails after the state transition
    monkeypatch.setattr(svc, 'continue_matching_after_intro_call_feedback_from_coach', lambda *a, **k: None)
    url = reverse('confirm_intro_call', kwargs={'token': coach_action_token_confirm_intro_call.token})
    r = client.get(url)
    assert r.status_code == 200
    assert 'matching/coach_response_intro_call.html' in [t.name for t in r.templates]
    assert MatchingEvent.objects.filter(
        matching_attempt=ma,
        event_type=MatchingEvent.EventType.INTRO_CALL_FEEDBACK_RECEIVED_FROM_COACH,
    ).exists()


# ── MatchingAttemptCreateView: uncovered branches ────────────────────────────

@pytest.mark.django_db
def test_create_matching_form_valid_ue_below_one(rf, staff_user, participant, bl_staff):
    """Lines 47-48: ue < 1 guard inside form_valid.

    The form's own MinValueValidator prevents ue=0 from reaching form_valid during
    a normal POST, so we exercise this guard by calling form_valid directly with a
    mock form whose cleaned_data contains ue=0.
    """
    from unittest.mock import MagicMock, patch
    from django.contrib.messages.storage.fallback import FallbackStorage
    from matching.views import MatchingAttemptCreateView

    request = rf.post('/matching/create/')
    request.user = staff_user
    request.session = {}
    request._messages = FallbackStorage(request)

    view = MatchingAttemptCreateView()
    view.request = request
    view.kwargs = {}
    view.args = []
    view.object = None

    mock_form = MagicMock()
    mock_form.cleaned_data = {'ue': 0, 'participant': participant, 'bl_contact': bl_staff}

    with patch.object(view, 'form_invalid', return_value=MagicMock(status_code=200)) as mock_invalid:
        view.form_valid(mock_form)

    mock_invalid.assert_called_once_with(mock_form)
    from django.contrib.messages import get_messages
    msgs = list(get_messages(request))
    assert any("Unterrichtseinheiten" in str(m) for m in msgs)


@pytest.mark.django_db
def test_create_matching_validation_error_no_existing_url(client, staff_user, bl_staff, participant, monkeypatch):
    """Line 71: else-branch of the ValidationError handler, where e.message is falsy."""
    import matching.services as svc
    from django.core.exceptions import ValidationError

    def raise_no_url(*args, **kwargs):
        err = ValidationError("placeholder")
        err.message = None  # make `existing` falsy so the else-branch executes
        raise err

    monkeypatch.setattr(svc, 'create_matching_attempt', raise_no_url)
    client.force_login(staff_user)
    url = reverse('matching_attempt_create')
    r = client.post(url, data={'participant': participant.pk, 'ue': 40, 'bl_contact': bl_staff.pk})
    assert r.status_code == 200
    msgs = list(get_messages(r.wsgi_request))
    assert any("Es existiert bereits ein aktives Matching." in str(m) for m in msgs)


@pytest.mark.django_db
def test_create_matching_integrity_error_with_conflicting(
    client, staff_user, bl_staff, participant, matching_attempt, monkeypatch
):
    """Lines 75-90: IntegrityError handler when a conflicting active MA exists.

    `matching_attempt` fixture creates an IN_PREPARATION MA for the same participant,
    which is an ACTIVESTATE, so the filter returns it and the URL-link message is shown.
    """
    import matching.services as svc
    from django.db import IntegrityError

    monkeypatch.setattr(
        svc, 'create_matching_attempt',
        lambda *a, **k: (_ for _ in ()).throw(IntegrityError()),
    )
    client.force_login(staff_user)
    url = reverse('matching_attempt_create')
    r = client.post(url, data={'participant': participant.pk, 'ue': 40, 'bl_contact': bl_staff.pk})
    assert r.status_code == 200
    msgs = list(get_messages(r.wsgi_request))
    assert any("aktives Matching" in str(m) for m in msgs)


@pytest.mark.django_db
def test_create_matching_integrity_error_without_conflicting(
    client, staff_user, bl_staff, participant_2, monkeypatch
):
    """Lines 90-95: IntegrityError handler when no conflicting active MA can be found.

    Uses participant_2 who has no existing MatchingAttempt, so the filter returns
    nothing and the fallback plain-text message is shown.
    """
    import matching.services as svc
    from django.db import IntegrityError

    monkeypatch.setattr(
        svc, 'create_matching_attempt',
        lambda *a, **k: (_ for _ in ()).throw(IntegrityError()),
    )
    client.force_login(staff_user)
    url = reverse('matching_attempt_create')
    r = client.post(url, data={'participant': participant_2.pk, 'ue': 40, 'bl_contact': bl_staff.pk})
    assert r.status_code == 200
    msgs = list(get_messages(r.wsgi_request))
    assert any("bereits ein aktives Matching vorhanden" in str(m) for m in msgs)


# ── MatchingAttemptDetailView: coach_requests loop body ──────────────────────

@pytest.mark.django_db
def test_matching_attempt_detail_with_coach_requests(client, staff_user, rtc):
    """Lines 133-134: for-loop body in get_context_data runs when coach_requests exist."""
    client.force_login(staff_user)
    url = reverse('matching_attempt_detail', kwargs={'pk': rtc.matching_attempt.pk})
    r = client.get(url)
    assert r.status_code == 200


# ── MatchingEventDetailView: payload formatting branches ─────────────────────

@pytest.mark.django_db
def test_matching_event_detail_payload_iso_datetime_string(client, staff_user, matching_attempt):
    """Lines 673-678: payload value is a parseable ISO-datetime string."""
    from matching.models import MatchingEvent, TriggeredByOptions

    event = MatchingEvent.objects.create(
        matching_attempt=matching_attempt,
        event_type=MatchingEvent.EventType.CREATED,
        triggered_by=TriggeredByOptions.STAFF,
        triggered_by_user=staff_user,
        payload={"ts": "2026-01-15T10:30:00+00:00"},
    )
    client.force_login(staff_user)
    r = client.get(reverse('matching_event_detail', kwargs={'pk': event.pk}))
    assert r.status_code == 200
    keys = [k for k, _ in r.context['formatted_payload']]
    assert 'ts' in keys


@pytest.mark.django_db
def test_matching_event_detail_payload_plain_string(client, staff_user, matching_attempt):
    """Line 694: payload value is a plain (non-datetime) string — falls through to str()."""
    from matching.models import MatchingEvent, TriggeredByOptions

    event = MatchingEvent.objects.create(
        matching_attempt=matching_attempt,
        event_type=MatchingEvent.EventType.CREATED,
        triggered_by=TriggeredByOptions.STAFF,
        triggered_by_user=staff_user,
        payload={"label": "some plain text", "count": 42},
    )
    client.force_login(staff_user)
    r = client.get(reverse('matching_event_detail', kwargs={'pk': event.pk}))
    assert r.status_code == 200
    keys = [k for k, _ in r.context['formatted_payload']]
    assert 'label' in keys
    assert 'count' in keys


@pytest.mark.django_db
def test_matching_event_detail_payload_dict(client, staff_user, matching_attempt):
    """Lines 688-692: payload value is a dict — serialised with json.dumps()."""
    from matching.models import MatchingEvent, TriggeredByOptions

    event = MatchingEvent.objects.create(
        matching_attempt=matching_attempt,
        event_type=MatchingEvent.EventType.CREATED,
        triggered_by=TriggeredByOptions.STAFF,
        triggered_by_user=staff_user,
        payload={"metadata": {"key": "value", "nested": True}},
    )
    client.force_login(staff_user)
    r = client.get(reverse('matching_event_detail', kwargs={'pk': event.pk}))
    assert r.status_code == 200
    formatted = dict(r.context['formatted_payload'])
    assert '"key"' in formatted['metadata']
