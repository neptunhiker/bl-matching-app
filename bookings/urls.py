# bookings/urls.py
from django.urls import path
from .views import calendly_webhook, CalendlyBookingsListView

urlpatterns = [
    path("", CalendlyBookingsListView.as_view(), name="calendly_bookings_list"),
    path("webhooks/calendly/", calendly_webhook, name="calendly_webhook"),
]