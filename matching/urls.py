from django.urls import path

from .views import MatchingAttemptCreateView, MatchingAttemptDetailView, MatchingAttemptListView, RequestToCoachDetailView


urlpatterns = [
    path('matchings/', MatchingAttemptListView.as_view(), name='matching_attempts'),
    path('matchings/new/', MatchingAttemptCreateView.as_view(), name='matching_attempt_create'),
    path('matching-attempt/<uuid:pk>/', MatchingAttemptDetailView.as_view(), name='matching_attempt_detail'),
    path('request-to-coach/<uuid:pk>/', RequestToCoachDetailView.as_view(), name='request_to_coach_detail'),
]