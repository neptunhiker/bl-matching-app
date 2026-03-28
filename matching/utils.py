from __future__ import annotations

from datetime import date, datetime, timedelta

from django.utils import timezone

from profiles.models import Participant



def get_deadline(
    start: datetime,
    hours: int=24,
) -> datetime:
    """Advance a datetime by a given number of business hours, skipping weekends and dark hours (22:00–08:00)."""
    def round_up_to_next_hour(dt):
        if dt.minute == 0 and dt.second == 0 and dt.microsecond == 0:
            return dt
        return dt.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)

    def next_business_day(dt):
        days = 1
        if dt.weekday() == 4:  # Friday
            days = 3
        elif dt.weekday() == 5:  # Saturday
            days = 2
        elif dt.weekday() == 6:  # Sunday
            days = 1
        return dt + timedelta(days=days)
    
    # 0. Friday evenings after 18:00 should be treated like the weekend
    if start.weekday() == 4 and start.hour >= 18:
        monday = start + timedelta(days=(7 - start.weekday()))
        return monday.replace(hour=20, minute=0, second=0, microsecond=0)

    # 1. Weekend → Monday 20:00
    if start.weekday() >= 5:
        monday = start + timedelta(days=(7 - start.weekday()))
        return monday.replace(hour=20, minute=0, second=0, microsecond=0)

    # 2. Business hours
    if 8 <= start.hour < 18:
        next_hour = round_up_to_next_hour(start)
        return next_business_day(next_hour)
        

    # 3. Off-hours (weekday)
    if start.hour < 8:
        return start.replace(hour=20, minute=0, second=0, microsecond=0)

    # after 18:00
    next_day = next_business_day(start)
    return next_day.replace(hour=20, minute=0, second=0, microsecond=0)

def get_urgency_message(participant: Participant, current_date: datetime.date = timezone.now().date(), start_date: datetime.date = None):
    """Generate an urgency message for the coach based on how soon the coaching should start."""
    
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