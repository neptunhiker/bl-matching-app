from profiles.views import CoachDetailView

from django.urls import reverse


class TestParticipantDetailViewTest:
    def test_no_access_non_logged_in_user(self, client, participant):
        url = reverse('participant_detail', kwargs={'pk': participant.pk})
        response = client.get(url)
        assert response.status_code == 302 
        assert response.url.startswith('/accounts/login/')
    def test_no_access_for_coach_without_request(self, client, participant, coach_2):
        client.force_login(coach_2.user)
        url = reverse('participant_detail', kwargs={'pk': participant.pk})
        response = client.get(url)
        assert response.status_code == 403
        
    def test_access_for_coach_with_request(self, client, participant, coach_1, rtc):
        client.force_login(coach_1.user)
        url = reverse('participant_detail', kwargs={'pk': participant.pk})
        response = client.get(url)
        assert response.status_code == 200
        assert "profiles/participant_detail_for_coach.html" in [t.name for t in response.templates]
        
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