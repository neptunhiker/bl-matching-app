from django.contrib import admin
from django.utils.html import format_html
from .models import EmailLog


@admin.register(EmailLog)
class EmailLogAdmin(admin.ModelAdmin):
    list_display = ('subject', 'to', 'status_badge', 'sent_at', 'sent_by')
    list_filter = ('status', 'sent_at')
    search_fields = ('to', 'subject')
    readonly_fields = ('id', 'to', 'subject', 'html_body', 'status',
                       'error_message', 'sent_at', 'sent_by')
    ordering = ('-sent_at',)

    def status_badge(self, obj):
        colour = '#28a745' if obj.status == 'sent' else '#dc3545'
        return format_html(
            '<span style="color:{};font-weight:bold">{}</span>',
            colour,
            obj.get_status_display(),
        )
    status_badge.short_description = 'Status'

    def has_add_permission(self, request):
        return False  # logs are created by the service only
