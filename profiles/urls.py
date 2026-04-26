from django.urls import path
from . import views

urlpatterns = [
    path('teilnehmer/', views.ParticipantListView.as_view(), name='participant_list'),
    path('teilnehmer/neu/', views.ParticipantCreateView.as_view(), name='participant_create'),
    path('teilnehmer/<uuid:pk>/', views.ParticipantDetailView.as_view(), name='participant_detail'),
    path('teilnehmer/<uuid:pk>/bearbeiten/', views.ParticipantUpdateView.as_view(), name='participant_update'),
    path('teilnehmer/<uuid:pk>/loeschen/', views.ParticipantDeleteView.as_view(), name='participant_delete'),
    
    # Coaches
    path('coaches/', views.CoachListView.as_view(), name='coach_list'),
    path('coaches/neu/', views.CoachCreateView.as_view(), name='coach_create'),
    path('coaches/<uuid:pk>/', views.CoachDetailView.as_view(), name='coach_detail'),
    path('coaches/<uuid:pk>/bearbeiten/', views.CoachUpdateView.as_view(), name='coach_update'),
    path('coaches/<uuid:pk>/loeschen/', views.CoachDeleteView.as_view(), name='coach_delete'),
    path('coaches/abrufen/', views.coach_import_preview, name='get_coaches'),
    path('coaches/abrufen/bestaetigen/', views.coach_import_confirm, name='coach_import_confirm'),
]