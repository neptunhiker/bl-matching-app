from django.urls import path

from .views import (
    CoachAutocompleteView,
    CoachRespondView,
    MatchingAttemptCreateView,
    MatchingAttemptDetailView,
    MatchingAttemptListView,
    RequestToCoachCreateView,
    RequestToCoachDetailView,
    ToggleAutomationView,
)


urlpatterns = [
    path('matchings/', MatchingAttemptListView.as_view(), name='matching_attempts'),
    path('matchings/new/', MatchingAttemptCreateView.as_view(), name='matching_attempt_create'),
    path('matching/<uuid:pk>/', MatchingAttemptDetailView.as_view(), name='matching_attempt_detail'),
    path('matching/<uuid:pk>/automation/', ToggleAutomationView.as_view(), name='matching_attempt_automation'),
    path('matching/<uuid:pk>/add-coach/', RequestToCoachCreateView.as_view(), name='request_to_coach_create'),
    path('matching/coaches/search/', CoachAutocompleteView.as_view(), name='coach_autocomplete'),
    path('request-to-coach/<uuid:pk>/', RequestToCoachDetailView.as_view(), name='request_to_coach_detail'),
    # Public — no login required. Token in URL authorises the action.
    path('response_coach/<str:token>/', CoachRespondView.as_view(), name='coach_respond'),
]