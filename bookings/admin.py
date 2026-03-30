# bookings/admin.py
from django.contrib import admin
from .models import CalendlyBooking


@admin.register(CalendlyBooking)
class CalendlyBookingAdmin(admin.ModelAdmin):
    list_display = (
        "invitee_name_display",
        "invitee_email",
        "event_name",
        "start_time",
        "status",
        "created_at",
    )

    search_fields = (
        "invitee_name",
        "invitee_first_name",
        "invitee_last_name",
        "invitee_email",
        "event_name",
        "calendly_event_uuid",
        "calendly_invitee_uri",
    )

    list_filter = (
        "status",
        "event_name",
        "start_time",
        "created_at",
    )

    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
        "calendly_event_uri",
        "calendly_invitee_uri",
        "calendly_event_uuid",
        "raw_payload_pretty",
        "questions_and_answers_pretty",
    )

    ordering = ("-created_at",)

    # 👉 bessere Darstellung des Namens
    def invitee_name_display(self, obj):
        return obj.invitee_name or f"{obj.invitee_first_name} {obj.invitee_last_name}".strip()

    invitee_name_display.short_description = "Name"

    # 👉 schön lesbares JSON für Debugging
    def raw_payload_pretty(self, obj):
        import json
        return json.dumps(obj.raw_payload, indent=2, ensure_ascii=False)

    raw_payload_pretty.short_description = "Raw payload"

    def questions_and_answers_pretty(self, obj):
        import json
        return json.dumps(obj.questions_and_answers, indent=2, ensure_ascii=False)

    questions_and_answers_pretty.short_description = "Questions & Answers"