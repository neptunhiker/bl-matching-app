from django.urls import path

from .views import (
    CoachRespondView,
    MatchingAttemptCreateView,
    MatchingAttemptDeleteView,
    MatchingAttemptDetailView,
    MatchingAttemptListView,
    RequestToCoachCreateView,
    RequestToCoachDetailView,
    StartMatchingView,
    ResumeMatchingView,
    ToggleAutomationView,
    RequestToCoachUpdateView,
    RequestToCoachDeleteView,
    ConfirmIntroCallView,
    FlowChartView,
    MatchingEventDetailView,
    ParticipantRespondView,
    CancelMatchingView,
    ManualOverrideMatchingView
)


urlpatterns = [
    path('matchings/', MatchingAttemptListView.as_view(), name='matching_attempts'),
    path('matchings/new/', MatchingAttemptCreateView.as_view(), name='matching_attempt_create'),
    path('matching/<uuid:pk>/delete/', MatchingAttemptDeleteView.as_view(), name='matching_attempt_delete'),
    path('matching/<uuid:pk>/', MatchingAttemptDetailView.as_view(), name='matching_attempt_detail'),
    path('matching/<uuid:pk>/start/', StartMatchingView.as_view(), name='matching_attempt_start'),
    path('matching/<uuid:pk>/resume/', ResumeMatchingView.as_view(), name='matching_attempt_resume'),
    path('matching/<uuid:pk>/automation/', ToggleAutomationView.as_view(), name='matching_attempt_automation'),
    path('matching/<uuid:pk>/add-coach/', RequestToCoachCreateView.as_view(), name='request_to_coach_create'),
    path('request-to-coach/<uuid:pk>/', RequestToCoachDetailView.as_view(), name='request_to_coach_detail'),
    path('request-to-coach/<uuid:pk>/edit/', RequestToCoachUpdateView.as_view(), name='request_to_coach_edit'),
    path('request-to-coach/<uuid:pk>/delete/', RequestToCoachDeleteView.as_view(), name='request_to_coach_delete'),
    # Public — no login required. Token in URL authorises the action.
    path('response_coach/<str:token>/', CoachRespondView.as_view(), name='coach_respond'),
    path('response_participant/<str:token>/', ParticipantRespondView.as_view(), name='participant_respond'),
    path('confirm_intro_call/<str:token>/', ConfirmIntroCallView.as_view(), name='confirm_intro_call'),
    path('flow_chart/', FlowChartView.as_view(), name='matching_flow_chart'),
    path('matching_event/<uuid:pk>/', MatchingEventDetailView.as_view(), name='matching_event_detail'),
    path('matching/<uuid:pk>/cancel/', CancelMatchingView.as_view(), name='matching_attempt_cancel'),
    path('matching/<uuid:matching_attempt_pk>/manual-override/', ManualOverrideMatchingView.as_view(), name='manual_override_matching'),
]



