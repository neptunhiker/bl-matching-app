# bookings/urls.py
from django.urls import path
from .views import calendly_webhook, CalendlyBookingsListView, CalendlyBookingDetailView

urlpatterns = [
    path("", CalendlyBookingsListView.as_view(), name="calendly_bookings_list"),
    path("<uuid:pk>/", CalendlyBookingDetailView.as_view(), name="calendly_booking_detail"),
    path("webhooks/calendly/", calendly_webhook, name="calendly_webhook"),
]