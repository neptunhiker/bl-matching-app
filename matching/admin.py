from django.contrib import admin

from .models import CoachActionToken, MatchingAttempt, RequestToCoach, MatchingEvent

from django.contrib import admin



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
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False

    # def has_view_permission(self, request, obj=None):
    #     return False
    
    # def has_module_permission(self, request):
    #     return False
    
@admin.register(MatchingAttempt)
class MatchingAttemptAdmin(admin.ModelAdmin):
    list_display = ['id', 'participant', 'state', 'automation_enabled', 'created_at']
    list_filter = ['automation_enabled']
    search_fields = ['participant__first_name', 'participant__last_name', 'participant__email']
    ordering = ['-created_at']
    
@admin.register(RequestToCoach)
class RequestToCoachAdmin(admin.ModelAdmin):
    list_display = ['id', 'matching_attempt', 'coach', 'state', 'priority', 'first_sent_at', 'deadline_at']
    list_filter = ['state', 'priority']
    search_fields = ['matching_attempt__participant__first_name', 'matching_attempt__participant__last_name', 'matching_attempt__participant__email', 'coach__user__email']
    ordering = ['-first_sent_at']
    exclude = ['state']
    
      
@admin.register(MatchingEvent)
class MatchingEventAdmin(admin.ModelAdmin):
    list_display = ['id', 'matching_attempt', 'event_type', 'created_at']
    list_filter = ['event_type']
    search_fields = ['matching_attempt__participant__first_name', 'matching_attempt__participant__last_name', 'matching_attempt__participant__email']
    ordering = ['-created_at']
    

