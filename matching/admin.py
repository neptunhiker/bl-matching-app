from django.contrib import admin

from .models import MatchingAttempt, RequestToCoach

admin.site.register(MatchingAttempt)
admin.site.register(RequestToCoach)
