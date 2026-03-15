"""
General-purpose utilities for the matching app.

add_business_hours(start, hours, holidays=None)
    Advance a datetime by *hours* business hours, skipping weekends and
    optionally a set of holiday dates.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from django.utils import timezone

from profiles.models import Participant



def add_business_hours(
    start: datetime,
    hours: int,
    holidays: set[date] | None = None,
) -> datetime:
    """
    Advance *start* by *hours* business hours, skipping weekends.

    Weekends (Saturday = 5, Sunday = 6) are skipped entirely: the clock
    resumes at midnight on the following Monday.

    Args:
        start:    Timezone-aware (or naive) datetime to count forward from.
        hours:    Number of business hours to add.  Must be >= 0.
        holidays: Optional set of ``datetime.date`` objects treated as
                  non-business days (e.g. public holidays).  When the cursor
                  lands on one of these dates it is skipped in the same way
                  as a weekend.  Pass ``None`` (default) to ignore holidays.

    Returns:
        A datetime of the same type (aware/naive) as *start*.

    Examples:
        >>> from datetime import datetime
        >>> thu = datetime(2026, 3, 5, 11, 0)   # Thursday 11:00
        >>> add_business_hours(thu, 24)
        datetime.datetime(2026, 3, 6, 11, 0)    # Friday 11:00

        >>> fri = datetime(2026, 3, 6, 13, 0)   # Friday 13:00
        >>> add_business_hours(fri, 24)
        datetime.datetime(2026, 3, 9, 13, 0)    # Monday 13:00

        >>> add_business_hours(fri, 48)
        datetime.datetime(2026, 3, 10, 13, 0)   # Tuesday 13:00
    """
    if hours < 0:
        raise ValueError("hours must be >= 0")

    holidays = holidays or set()
    current = start

    for _ in range(hours):
        current = current + timedelta(hours=1)
        # If we have landed on a non-business day, advance to midnight of the
        # next business day.  We do NOT preserve the start time-of-day here:
        # the cursor is at e.g. Saturday 00:00 and we simply fast-forward to
        # Monday 00:00 so that subsequent loop iterations continue counting
        # from there.  This ensures "Friday 13:00 + 24 h = Monday 13:00":
        #   11 iterations reach Saturday 00:00  → jump to Monday 00:00
        #   13 more iterations reach Monday 13:00
        while current.weekday() >= 5 or current.date() in holidays:
            current = (current + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )

    return current

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