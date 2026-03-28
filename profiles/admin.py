from django.contrib import admin
from .models import Language, Coach, Participant, BeginnerLuftStaff


@admin.register(Language)
class LanguageAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)
    ordering = ('name',)


@admin.register(Coach)
class CoachAdmin(admin.ModelAdmin):
    list_display = ('user__last_name', 'user__first_name', 'city', 'status',
                    'coaching_format_online', 'coaching_format_presence', 'coaching_format_hybrid', 'preferred_communication_channel')
    list_filter = ('status', 'languages',
                   'coaching_format_online', 'coaching_format_presence', 'coaching_format_hybrid')
    search_fields = ('user__first_name', 'user__last_name', 'city', 'user__email', 'slack_user_id')
    filter_horizontal = ('languages',)
    ordering = ('user__last_name', 'user__first_name')


@admin.register(Participant)
class ParticipantAdmin(admin.ModelAdmin):
    list_display = ('last_name', 'first_name', 'email', 'city',
                    'coaching_format_online', 'coaching_format_presence', 'coaching_format_hybrid')
    list_filter = ('languages',
                   'coaching_format_online', 'coaching_format_presence', 'coaching_format_hybrid')
    search_fields = ('first_name', 'last_name', 'email', 'city')
    filter_horizontal = ('languages',)
    ordering = ('last_name', 'first_name')


@admin.register(BeginnerLuftStaff)
class BeginnerLuftStaffAdmin(admin.ModelAdmin):
    list_display = ('user__last_name', 'user__first_name', 'user__email')
    search_fields = ('user__first_name', 'user__last_name', 'user__email')
    ordering = ('user__last_name', 'user__first_name')