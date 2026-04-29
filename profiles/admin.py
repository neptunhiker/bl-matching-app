from django.contrib import admin
from .models import Language, City, Industry, Coach, Participant, BeginnerLuftStaff


@admin.register(Language)
class LanguageAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)
    ordering = ('name',)


@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)
    ordering = ('name',)


@admin.register(Industry)
class IndustryAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)
    ordering = ('name',)


@admin.register(Coach)
class CoachAdmin(admin.ModelAdmin):
    list_display = ('last_name', 'first_name', 'email', 'status',
                    'coaching_format_online', 'coaching_format_presence', 'coaching_format_hybrid',
                    'preferred_communication_channel', 'own_coaching_room')
    list_filter = (
        'status',
        'languages',
        'coaching_format_online', 'coaching_format_presence', 'coaching_format_hybrid',
        'leadership_coaching', 'hr_experience', 'expert_for_job_applications',
        'intercultural_coaching', 'high_profile_coaching', 'coaching_with_language_barriers',
        'therapeutic_experience', 'adhs_coaching', 'lgbtq_coaching',
        'own_coaching_room',
    )
    search_fields = ('first_name', 'last_name', 'email', 'slack_user_id')
    filter_horizontal = ('languages', 'coaching_cities', 'industry_experience')
    readonly_fields = ('coaching_hub_id', 'updated', 'created_at')
    ordering = ('last_name', 'first_name')


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