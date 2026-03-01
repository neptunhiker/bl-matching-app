from django.contrib import admin
from .models import Language, CoachProfile, CoacheeProfile


@admin.register(Language)
class LanguageAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)
    ordering = ('name',)


@admin.register(CoachProfile)
class CoachProfileAdmin(admin.ModelAdmin):
    list_display = ('last_name', 'first_name', 'city', 'status',
                    'coaching_format_online', 'coaching_format_presence', 'coaching_format_hybrid')
    list_filter = ('status', 'languages',
                   'coaching_format_online', 'coaching_format_presence', 'coaching_format_hybrid')
    search_fields = ('first_name', 'last_name', 'city', 'user__email')
    filter_horizontal = ('languages',)
    ordering = ('last_name', 'first_name')


@admin.register(CoacheeProfile)
class CoacheeProfileAdmin(admin.ModelAdmin):
    list_display = ('last_name', 'first_name', 'email', 'city',
                    'coaching_format_online', 'coaching_format_presence', 'coaching_format_hybrid')
    list_filter = ('languages',
                   'coaching_format_online', 'coaching_format_presence', 'coaching_format_hybrid')
    search_fields = ('first_name', 'last_name', 'email', 'city')
    filter_horizontal = ('languages',)
    ordering = ('last_name', 'first_name')
