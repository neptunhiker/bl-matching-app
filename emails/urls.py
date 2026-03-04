from django.urls import path

from .views import BrevoWebhookView

app_name = 'emails'

urlpatterns = [
    path('webhooks/brevo/', BrevoWebhookView.as_view(), name='brevo_webhook'),
]
