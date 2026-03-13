from django.urls import path

from .views import slack_interactions

urlpatterns = [
    path("interactions/", slack_interactions, name="slack_interactions"),

]