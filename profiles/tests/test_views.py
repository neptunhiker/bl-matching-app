import pytest

from profiles.models import Coach
from profiles.views import CoachDetailView

from django.urls import reverse


class TestParticipantDetailViewTest:
    def test_no_access_non_logged_in_user(self, client, participant):
        url = reverse('participant_detail', kwargs={'pk': participant.pk})
        response = client.get(url)
        assert response.status_code == 302 
        assert response.url.startswith('/accounts/login/')
    def test_no_access_for_plain_user(self, client, participant, plain_user):
        client.force_login(plain_user)
        url = reverse('participant_detail', kwargs={'pk': participant.pk})
        response = client.get(url)
        assert response.status_code == 403
        
    def test_access_for_staff_user(self, client, participant, staff_user):
        client.force_login(staff_user)
        url = reverse('participant_detail', kwargs={'pk': participant.pk})
        response = client.get(url)
        assert response.status_code == 200
        assert "profiles/participant_detail.html" in [t.name for t in response.templates]
        
    def test_access_for_superuser(self, client, participant, superuser):
        client.force_login(superuser)
        url = reverse('participant_detail', kwargs={'pk': participant.pk})
        response = client.get(url)
        assert response.status_code == 200
        assert "profiles/participant_detail.html" in [t.name for t in response.templates]

    def test_no_access_for_plain_user(self, client, participant, plain_user):
        client.force_login(plain_user)
        url = reverse('participant_detail', kwargs={'pk': participant.pk})
        response = client.get(url)
        assert response.status_code == 403

    def test_no_access_for_plain_user_alt(self, client, participant, plain_user):
        client.force_login(plain_user)
        url = reverse('participant_detail', kwargs={'pk': participant.pk})
        response = client.get(url)
        assert response.status_code == 403


class TestCoachDetailViewTest:
    
    @pytest.mark.django_db
    def test_coach_detail_view_not_logged_in(self, client, coach_1):
        url = reverse('coach_detail', kwargs={'pk': coach_1.pk})
        response = client.get(url)
        assert response.status_code == 302
        assert response.url.startswith('/accounts/login/')
        
    @pytest.mark.django_db
    def test_coach_detail_view_logged_in_staff_member(self, client, staff_user, coach_1):
        client.force_login(staff_user)
        url = reverse('coach_detail', kwargs={'pk': coach_1.pk})
        response = client.get(url)
        assert response.status_code == 200
        assert "profiles/coach_detail.html" in [t.name for t in response.templates]
        
    @pytest.mark.django_db
    def test_coach_detail_view_logged_in_superuser(self, client, superuser, coach_1):
        client.force_login(superuser)
        url = reverse('coach_detail', kwargs={'pk': coach_1.pk})
        response = client.get(url)
        assert response.status_code == 200
        assert "profiles/coach_detail.html" in [t.name for t in response.templates]

    @pytest.mark.django_db
    def test_no_access_for_plain_user(self, client, coach_1, plain_user):
        client.force_login(plain_user)
        url = reverse('coach_detail', kwargs={'pk': coach_1.pk})
        response = client.get(url)
        assert response.status_code == 403

    @pytest.mark.django_db
    def test_status_choices_available_in_context(self, client, staff_user, coach_1):
        client.force_login(staff_user)
        response = client.get(reverse('coach_detail', kwargs={'pk': coach_1.pk}))
        assert response.context['Status'] is Coach.Status


# ---------------------------------------------------------------------------
# StaffRequired views — uniform access rules
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestParticipantListView:
    def test_logged_out_redirects_to_login(self, client):
        response = client.get(reverse('participant_list'))
        assert response.status_code == 302
        assert response.url.startswith('/accounts/login/')

    def test_plain_user_forbidden(self, client, plain_user):
        client.force_login(plain_user)
        assert client.get(reverse('participant_list')).status_code == 403

    def test_coach_forbidden(self, client, plain_user):
        client.force_login(plain_user)
        assert client.get(reverse('participant_list')).status_code == 403

    def test_staff_has_access(self, client, staff_user):
        client.force_login(staff_user)
        assert client.get(reverse('participant_list')).status_code == 200

    def test_superuser_has_access(self, client, superuser):
        client.force_login(superuser)
        assert client.get(reverse('participant_list')).status_code == 200


@pytest.mark.django_db
class TestParticipantCreateView:
    def test_logged_out_redirects_to_login(self, client):
        response = client.get(reverse('participant_create'))
        assert response.status_code == 302
        assert response.url.startswith('/accounts/login/')

    def test_plain_user_forbidden(self, client, plain_user):
        client.force_login(plain_user)
        assert client.get(reverse('participant_create')).status_code == 403

    def test_coach_forbidden(self, client, plain_user):
        client.force_login(plain_user)
        assert client.get(reverse('participant_create')).status_code == 403

    def test_staff_has_access(self, client, staff_user):
        client.force_login(staff_user)
        assert client.get(reverse('participant_create')).status_code == 200

    def test_superuser_has_access(self, client, superuser):
        client.force_login(superuser)
        assert client.get(reverse('participant_create')).status_code == 200

    def test_successful_post_redirects_to_detail(self, client, staff_user):
        client.force_login(staff_user)
        data = {
            'first_name': 'New',
            'last_name': 'Person',
            'email': 'new_participant@example.com',
            'city': 'Berlin',
            'start_date': '2026-11-22',
        }
        response = client.post(reverse('participant_create'), data)
        assert response.status_code == 302
        assert '/teilnehmer/' in response.url


@pytest.mark.django_db
class TestParticipantUpdateView:
    def test_logged_out_redirects_to_login(self, client, participant):
        response = client.get(reverse('participant_update', kwargs={'pk': participant.pk}))
        assert response.status_code == 302
        assert response.url.startswith('/accounts/login/')

    def test_plain_user_forbidden(self, client, participant, plain_user):
        client.force_login(plain_user)
        assert client.get(reverse('participant_update', kwargs={'pk': participant.pk})).status_code == 403

    def test_coach_forbidden(self, client, participant, plain_user):
        client.force_login(plain_user)
        assert client.get(reverse('participant_update', kwargs={'pk': participant.pk})).status_code == 403

    def test_staff_has_access(self, client, participant, staff_user):
        client.force_login(staff_user)
        assert client.get(reverse('participant_update', kwargs={'pk': participant.pk})).status_code == 200

    def test_superuser_has_access(self, client, participant, superuser):
        client.force_login(superuser)
        assert client.get(reverse('participant_update', kwargs={'pk': participant.pk})).status_code == 200

    def test_successful_post_redirects_to_detail(self, client, staff_user, participant):
        client.force_login(staff_user)
        data = {
            'first_name': participant.first_name,
            'last_name': participant.last_name,
            'email': participant.email,
            'city': 'München',
            'start_date': '2026-11-22',
        }
        response = client.post(reverse('participant_update', kwargs={'pk': participant.pk}), data)
        assert response.status_code == 302
        assert '/teilnehmer/' in response.url


@pytest.mark.django_db
class TestParticipantDeleteView:
    def test_logged_out_redirects_to_login(self, client, participant):
        response = client.get(reverse('participant_delete', kwargs={'pk': participant.pk}))
        assert response.status_code == 302
        assert response.url.startswith('/accounts/login/')

    def test_plain_user_forbidden(self, client, participant, plain_user):
        client.force_login(plain_user)
        assert client.get(reverse('participant_delete', kwargs={'pk': participant.pk})).status_code == 403

    def test_coach_forbidden(self, client, participant, plain_user):
        client.force_login(plain_user)
        assert client.get(reverse('participant_delete', kwargs={'pk': participant.pk})).status_code == 403

    def test_staff_has_access(self, client, participant, staff_user):
        client.force_login(staff_user)
        assert client.get(reverse('participant_delete', kwargs={'pk': participant.pk})).status_code == 200

    def test_superuser_has_access(self, client, participant, superuser):
        client.force_login(superuser)
        assert client.get(reverse('participant_delete', kwargs={'pk': participant.pk})).status_code == 200


@pytest.mark.django_db
class TestCoachListView:
    def test_logged_out_redirects_to_login(self, client):
        response = client.get(reverse('coach_list'))
        assert response.status_code == 302
        assert response.url.startswith('/accounts/login/')

    def test_plain_user_forbidden(self, client, plain_user):
        client.force_login(plain_user)
        assert client.get(reverse('coach_list')).status_code == 403

    def test_coach_forbidden(self, client, plain_user):
        client.force_login(plain_user)
        assert client.get(reverse('coach_list')).status_code == 403

    def test_staff_has_access(self, client, staff_user):
        client.force_login(staff_user)
        assert client.get(reverse('coach_list')).status_code == 200

    def test_superuser_has_access(self, client, superuser):
        client.force_login(superuser)
        assert client.get(reverse('coach_list')).status_code == 200

    def test_search_filter_by_name(self, client, staff_user, coach_1):
        client.force_login(staff_user)
        response = client.get(reverse('coach_list'), {'q': coach_1.first_name})
        assert response.status_code == 200
        assert coach_1 in response.context['coaches']

    def test_status_filter(self, client, staff_user, coach_1):
        client.force_login(staff_user)
        response = client.get(reverse('coach_list'), {'status': 'onboarding'})
        assert response.status_code == 200
        assert coach_1 in response.context['coaches']

    def test_format_online_filter(self, client, staff_user):
        client.force_login(staff_user)
        assert client.get(reverse('coach_list'), {'format_online': '1'}).status_code == 200

    def test_format_presence_filter(self, client, staff_user):
        client.force_login(staff_user)
        assert client.get(reverse('coach_list'), {'format_presence': '1'}).status_code == 200

    def test_format_hybrid_filter(self, client, staff_user):
        client.force_login(staff_user)
        assert client.get(reverse('coach_list'), {'format_hybrid': '1'}).status_code == 200

    def test_page_param_stripped_from_filter_context(self, client, staff_user):
        client.force_login(staff_user)
        response = client.get(reverse('coach_list'), {'page': '1'})
        assert response.status_code == 200
        assert 'page' not in response.context['params']


@pytest.mark.django_db
class TestCoachCreateView:
    def test_logged_out_redirects_to_login(self, client):
        response = client.get(reverse('coach_create'))
        assert response.status_code == 302
        assert response.url.startswith('/accounts/login/')

    def test_plain_user_forbidden(self, client, plain_user):
        client.force_login(plain_user)
        assert client.get(reverse('coach_create')).status_code == 403

    def test_coach_forbidden(self, client, plain_user):
        client.force_login(plain_user)
        assert client.get(reverse('coach_create')).status_code == 403

    def test_staff_has_access(self, client, staff_user):
        client.force_login(staff_user)
        assert client.get(reverse('coach_create')).status_code == 200

    def test_superuser_has_access(self, client, superuser):
        client.force_login(superuser)
        assert client.get(reverse('coach_create')).status_code == 200

    def test_form_invalid_when_slack_channel_has_no_slack_id(self, client, staff_user):
        client.force_login(staff_user)
        data = {
            'first_name': 'Test',
            'last_name': 'Coach',
            'email': 'test_coach@example.com',
            'city': 'Berlin',
            'status': 'onboarding',
            'preferred_communication_channel': 'slack',
        }
        response = client.post(reverse('coach_create'), data)
        assert response.status_code == 200
        assert 'slack_user_id' in response.context['form'].errors

    def test_form_valid_with_slack_channel_and_slack_id(self, client, staff_user):
        client.force_login(staff_user)
        data = {
            'first_name': 'Test',
            'last_name': 'Coach',
            'email': 'test_coach2@example.com',
            'city': 'Berlin',
            'status': 'onboarding',
            'preferred_communication_channel': 'slack',
            'slack_user_id': 'U12345678',
        }
        response = client.post(reverse('coach_create'), data)
        assert response.status_code == 302


@pytest.mark.django_db
class TestCoachUpdateView:
    def test_logged_out_redirects_to_login(self, client, coach_1):
        response = client.get(reverse('coach_update', kwargs={'pk': coach_1.pk}))
        assert response.status_code == 302
        assert response.url.startswith('/accounts/login/')

    def test_plain_user_forbidden(self, client, coach_1, plain_user):
        client.force_login(plain_user)
        assert client.get(reverse('coach_update', kwargs={'pk': coach_1.pk})).status_code == 403

    def test_coach_forbidden(self, client, coach_1, plain_user):
        client.force_login(plain_user)
        assert client.get(reverse('coach_update', kwargs={'pk': coach_1.pk})).status_code == 403

    def test_staff_has_access(self, client, coach_1, staff_user):
        client.force_login(staff_user)
        assert client.get(reverse('coach_update', kwargs={'pk': coach_1.pk})).status_code == 200

    def test_superuser_has_access(self, client, coach_1, superuser):
        client.force_login(superuser)
        assert client.get(reverse('coach_update', kwargs={'pk': coach_1.pk})).status_code == 200

    def test_form_invalid_when_slack_channel_has_no_slack_id(self, client, staff_user, coach_1):
        client.force_login(staff_user)
        data = {
            'first_name': coach_1.first_name,
            'last_name': coach_1.last_name,
            'email': coach_1.email,
            'city': 'Berlin',
            'status': 'onboarding',
            'preferred_communication_channel': 'slack',
        }
        response = client.post(reverse('coach_update', kwargs={'pk': coach_1.pk}), data)
        assert response.status_code == 200
        assert 'slack_user_id' in response.context['form'].errors

    def test_form_valid_with_slack_channel_and_slack_id(self, client, staff_user, coach_1):
        client.force_login(staff_user)
        data = {
            'first_name': coach_1.first_name,
            'last_name': coach_1.last_name,
            'email': coach_1.email,
            'city': 'Hamburg',
            'status': 'onboarding',
            'preferred_communication_channel': 'slack',
            'slack_user_id': 'U12345678',
        }
        response = client.post(reverse('coach_update', kwargs={'pk': coach_1.pk}), data)
        assert response.status_code == 302


@pytest.mark.django_db
class TestCoachDeleteView:
    def test_logged_out_redirects_to_login(self, client, coach_1):
        response = client.get(reverse('coach_delete', kwargs={'pk': coach_1.pk}))
        assert response.status_code == 302
        assert response.url.startswith('/accounts/login/')

    def test_plain_user_forbidden(self, client, coach_1, plain_user):
        client.force_login(plain_user)
        assert client.get(reverse('coach_delete', kwargs={'pk': coach_1.pk})).status_code == 403

    def test_coach_forbidden(self, client, coach_1, plain_user):
        client.force_login(plain_user)
        assert client.get(reverse('coach_delete', kwargs={'pk': coach_1.pk})).status_code == 403

    def test_staff_has_access(self, client, coach_1, staff_user):
        client.force_login(staff_user)
        assert client.get(reverse('coach_delete', kwargs={'pk': coach_1.pk})).status_code == 200

    def test_superuser_has_access(self, client, coach_1, superuser):
        client.force_login(superuser)
        assert client.get(reverse('coach_delete', kwargs={'pk': coach_1.pk})).status_code == 200