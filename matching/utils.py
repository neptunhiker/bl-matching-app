from __future__ import annotations

from datetime import date, datetime, timedelta

from django.utils import timezone

from profiles.models import Participant



def get_deadline(
    start: datetime,
    hours: int=24,
) -> datetime:
    """Advance a datetime by a given number of business hours, skipping weekends and dark hours (22:00–08:00)."""

    # Convert to local time so that weekday checks and hour replacements
    # operate in Europe/Berlin time, not UTC. Without this, .replace(hour=18)
    # would set 18:00 UTC which displays as 20:00 in CEST (UTC+2).
    # Naive datetimes (e.g. in tests) are left as-is since localtime() rejects them.
    local_start = timezone.localtime(start) if timezone.is_aware(start) else start

    # if monday, tuesday, wednesday → add 2 days and set time to 09:00
    if local_start.weekday() in [0, 1, 2]:  # Monday, Tuesday, Wednesday
        return local_start.replace(hour=9, minute=0, second=0, microsecond=0) + timedelta(days=2)
    
    # if thursday → add 1 days and set time to 18:00
    if local_start.weekday() == 3:  # Thursday
        return local_start.replace(hour=18, minute=0, second=0, microsecond=0) + timedelta(days=1)
    
    # if friday → add 3 days and set time to 18:00
    if local_start.weekday() == 4:  # Friday
        return local_start.replace(hour=18, minute=0, second=0, microsecond=0) + timedelta(days=3)
    
    # if saturday → add 2 days and set time to 18:00
    if local_start.weekday() == 5:  # Saturday
        return local_start.replace(hour=18, minute=0, second=0, microsecond=0) + timedelta(days=2)
    
    # if sunday → add 1 day and set time to 18:00
    if local_start.weekday() == 6:  # Sunday
        return local_start.replace(hour=18, minute=0, second=0, microsecond=0) + timedelta(days=1)
    
def get_standard_deadline(start: datetime) -> datetime:
    """Calculate a standard 3-working-day deadline at 18:00. E.g. when a request goes out on a Monday the deadline is Thursday at 18:00."""
    local_start = timezone.localtime(start) if timezone.is_aware(start) else start
    if local_start.weekday() in [0, 1]:  # Monday, Tuesday
        return local_start.replace(hour=18, minute=0, second=0, microsecond=0) + timedelta(days=3)
    if local_start.weekday() in [2, 3, 4]:  # Wednesday, Thursday, Friday
        return local_start.replace(hour=18, minute=0, second=0, microsecond=0) + timedelta(days=5)
    if local_start.weekday() == 5:  # Saturday
        return local_start.replace(hour=18, minute=0, second=0, microsecond=0) + timedelta(days=4)
    if local_start.weekday() == 6:  # Sunday
        return local_start.replace(hour=18, minute=0, second=0, microsecond=0) + timedelta(days=3)
    raise ValueError(f"Unexpected weekday: {local_start.weekday()}")

def get_standard_extension_deadline(start: datetime) -> datetime:
    """Calculate a one-working-day extension deadline at 18:00. E.g. if the original deadline was Monday 18:00 the extended deadline is Tuesday 18:00."""
    local_start = timezone.localtime(start) if timezone.is_aware(start) else start
    if local_start.weekday() in [0, 1, 2, 3]:  # Monday, Tuesday, Wednesday, Thursday
        return local_start.replace(hour=18, minute=0, second=0, microsecond=0) + timedelta(days=1)
    if local_start.weekday() == 4:  # Friday
        return local_start.replace(hour=18, minute=0, second=0, microsecond=0) + timedelta(days=3)
    if local_start.weekday() == 5:  # Saturday
        return local_start.replace(hour=18, minute=0, second=0, microsecond=0) + timedelta(days=2)
    if local_start.weekday() == 6:  # Sunday
        return local_start.replace(hour=18, minute=0, second=0, microsecond=0) + timedelta(days=1)
    raise ValueError(f"Unexpected weekday: {local_start.weekday()}")


def build_notifications(email_logs, slack_logs):
    """Merge email and slack log lists into a single time-sorted notifications list.

    Each entry is a dict with keys: 'type' ('email'|'slack'), 'obj', 'sent_at'.
    """
    notifications = (
        [{'type': 'email', 'obj': e, 'sent_at': e.sent_at} for e in email_logs]
        + [{'type': 'slack', 'obj': s, 'sent_at': s.sent_at} for s in slack_logs]
    )
    return sorted(notifications, key=lambda n: n['sent_at'], reverse=True)


def get_urgency_message(participant: Participant, current_date: datetime.date = timezone.now().date(), start_date: datetime.date = None):
    """Generate an urgency message for the coach based on how soon the coaching should start."""
    
    if start_date is None:
        return f"Bitte melde dich so zeitnah wie möglich bei {participant.first_name}, damit ihr das Coaching starten könnt."
    
    time_until_start = (start_date - current_date).days
    
    if time_until_start < 0:
        urgency_msg = f"Das Coaching hätte bereits am {start_date.strftime('%d.%m.%Y')} starten sollen. Daher melde dich bitte ganz besonders schnell bei {participant.first_name}."
    elif time_until_start == 0:
        urgency_msg = f"Das Coaching soll idealerweise schon heute am {start_date.strftime('%d.%m.%Y')} starten. Daher melde dich bitte ganz schnell bei {participant.first_name}."
    elif time_until_start == 1:
        urgency_msg = f"Das Coaching soll schon morgen am {start_date.strftime('%d.%m.%Y')} starten. Daher melde dich bitte noch heute bei {participant.first_name}."
    elif time_until_start == 2:
        urgency_msg = f"Das Coaching soll schon übermorgen am {start_date.strftime('%d.%m.%Y')} starten. Daher melde dich bitte noch heute, aber spätestens morgen bei {participant.first_name}."
    elif time_until_start <= 7:
        urgency_msg = f"Das Coaching soll schon in {time_until_start} Tagen am {start_date.strftime('%d.%m.%Y')} starten. Also melde dich bitte heute oder morgen noch bei {participant.first_name}."
    elif time_until_start <= 14:
        urgency_msg = f"Das Coaching soll in {time_until_start} Tagen am {start_date.strftime('%d.%m.%Y')} starten. Das klingt vielleicht noch weit weg, aber lass bitte trotzdem nicht zu viel Zeit verstreichen und melde dich heute oder morgen noch bei {participant.first_name}."
    else:
        urgency_msg = f"Das Coaching soll in {time_until_start} Tagen am {start_date.strftime('%d.%m.%Y')} starten. Bitte melde dich bei {participant.first_name} so zeitnah wie möglich, damit ihr euch vor dem Start noch kennelernen könnt."
        
    return urgency_msg