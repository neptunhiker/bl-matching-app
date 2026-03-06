from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path

from .forms import EmailAuthenticationForm

urlpatterns = [
    path(
        'login/',
        LoginView.as_view(
            template_name='accounts/login.html',
            authentication_form=EmailAuthenticationForm,
        ),
        name='login',
    ),
    path('logout/', LogoutView.as_view(), name='logout'),
]
