from django.contrib import admin

from .models import CoachActionToken, MatchingAttempt, RequestToCoach

admin.site.register(MatchingAttempt)
admin.site.register(RequestToCoach)


@admin.register(CoachActionToken)
class CoachActionTokenAdmin(admin.ModelAdmin):
    list_display = ['short_token', 'request_to_coach', 'action', 'created_at', 'used_at']
    list_filter = ['action', 'used_at']
    search_fields = ['token', 'request_to_coach__coach__user__email']
    readonly_fields = ['id', 'token', 'request_to_coach', 'action', 'created_at', 'used_at']
    ordering = ['-created_at']

    @admin.display(description='Token')
    def short_token(self, obj):
        return f'{obj.token[:12]}…'
