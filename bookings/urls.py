# bookings/urls.py
from django.urls import path
from .views import calendly_webhook

urlpatterns = [
    path("webhooks/calendly/", calendly_webhook, name="calendly_webhook"),
]