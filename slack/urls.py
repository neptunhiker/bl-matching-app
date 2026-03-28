from django.urls import path

from slack.views import SlackLogDetailView    

app_name = "slack"

urlpatterns = [
    path('slack_log/<uuid:pk>/', SlackLogDetailView.as_view(), name='slack_log_detail'),
]