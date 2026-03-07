from django.urls import path

from .views import BrevoWebhookView, EmailLogDetailView

app_name = 'emails'

urlpatterns = [
    path('webhooks/brevo/', BrevoWebhookView.as_view(), name='brevo_webhook'),
    path('email_log/<uuid:pk>/', EmailLogDetailView.as_view(), name='email_log_detail'),
]
