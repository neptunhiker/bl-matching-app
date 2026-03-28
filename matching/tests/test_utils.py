import pytest
from datetime import datetime

from matching.utils import get_deadline

def test_weekend():
    # Saturday → Monday 20:00
    assert get_deadline(datetime(2023, 3, 4, 10, 30)) == datetime(2023, 3, 6, 20, 0)

    # Sunday → Monday 20:00
    assert get_deadline(datetime(2023, 3, 5, 15, 0)) == datetime(2023, 3, 6, 20, 0)


def test_business_hours():
    # 9 AM Monday → Tuesday 9 AM → rounded = 9 AM
    assert get_deadline(datetime(2023, 3, 6, 9, 0)) == datetime(2023, 3, 7, 9, 0)

    # 9:30 AM → next day 10 AM
    assert get_deadline(datetime(2023, 3, 6, 9, 30)) == datetime(2023, 3, 7, 10, 0)


def test_early_morning():
    # 6 AM → same day 20:00
    assert get_deadline(datetime(2023, 3, 6, 6, 0)) == datetime(2023, 3, 6, 20, 0)
    
    # 7.59 AM → same day 20:00 PM
    assert get_deadline(datetime(2023, 3, 6, 7, 59)) == datetime(2023, 3, 6, 20, 0)
    
    # 8 AM → next day 8:00 AM
    assert get_deadline(datetime(2023, 3, 6, 8, 0)) == datetime(2023, 3, 7, 8, 0)
    
    # 8.01 AM → next day 9 am
    assert get_deadline(datetime(2023, 3, 6, 8, 1)) == datetime(2023, 3, 7, 9, 0)


def test_evening():
    # Monday 19:00 → Tuesday 20:00
    assert get_deadline(datetime(2023, 3, 6, 19, 0)) == datetime(2023, 3, 7, 20, 0)
    
    # Monday 17:59 → Tuesday 18:00
    assert get_deadline(datetime(2023, 3, 6, 17, 59)) == datetime(2023, 3, 7, 18, 0)
    
    # Monday 18:00 → Tuesday 20:00
    assert get_deadline(datetime(2023, 3, 6, 18, 0)) == datetime(2023, 3, 7, 20, 0)

    # Monday 18:01 → Tuesday 20:00
    assert get_deadline(datetime(2023, 3, 6, 18, 1)) == datetime(2023, 3, 7, 20, 0)

    # Friday 19:00 → Monday 20:00
    assert get_deadline(datetime(2023, 3, 3, 19, 0)) == datetime(2023, 3, 6, 20, 0)


def test_friday_business_hours():
    # Friday 17:30 → Monday 18:00 
    assert get_deadline(datetime(2023, 3, 3, 17, 30)) == datetime(2023, 3, 6, 18, 0)