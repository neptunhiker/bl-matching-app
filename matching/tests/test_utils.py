import pytest
from datetime import datetime

from matching.utils import get_deadline, get_deadline_for_intro_call, get_intro_call_extension_deadline

class TestGetDeadline:
    
    def test_monday(self):
        start = datetime(2024, 6, 3, 9, 30)  # Monday 9:30
        deadline = get_deadline(start)
        assert deadline == datetime(2024, 6, 5, 9, 0)  # Wednesday 09:00
        
    def test_tuesday(self):
        start = datetime(2024, 6, 4, 15, 45)  # Tuesday 15:45
        deadline = get_deadline(start)
        assert deadline == datetime(2024, 6, 6, 9, 0)  # Thursday 09:00
    
    def test_wednesday(self):
        start = datetime(2024, 6, 5, 17, 15)  # Wednesday 17:15
        deadline = get_deadline(start)
        assert deadline == datetime(2024, 6, 7, 9, 0)  # Friday 09:00
        
    def test_thursday(self):
        start = datetime(2024, 6, 6, 10, 0)  # Thursday 10:00
        deadline = get_deadline(start)
        assert deadline == datetime(2024, 6, 7, 18, 0)  # Friday 18:00

    def test_friday(self):
        start = datetime(2024, 6, 7, 14, 0)  # Friday 14:00
        deadline = get_deadline(start)
        assert deadline == datetime(2024, 6, 10, 18, 0)  # Monday 18:00
        
    def test_saturday(self):
        start = datetime(2024, 6, 8, 11, 0)  # Saturday 11:00
        deadline = get_deadline(start)
        assert deadline == datetime(2024, 6, 10, 18, 0)  # Monday 18:00

    def test_sunday(self):
        start = datetime(2024, 6, 9, 16, 0)  # Sunday 16:00
        deadline = get_deadline(start)
        assert deadline == datetime(2024, 6, 10, 18, 0)  # Monday 18:00
        
        
class TestGetDeadlineForIntroCall:
    
    def test_monday(self):
        start = datetime(2024, 6, 3, 9, 30)  # Monday 9:30
        deadline = get_deadline_for_intro_call(start)
        assert deadline == datetime(2024, 6, 6, 18, 0)  # Thursday 18:00
        
    def test_tuesday(self):
        start = datetime(2024, 6, 4, 15, 45)  # Tuesday 15:45
        deadline = get_deadline_for_intro_call(start)
        assert deadline == datetime(2024, 6, 7, 18, 0)  # Friday 18:00
    
    def test_wednesday(self):
        start = datetime(2024, 6, 5, 17, 15)  # Wednesday 17:15
        deadline = get_deadline_for_intro_call(start)
        assert deadline == datetime(2024, 6, 10, 18, 0)  # Monday 18:00
        
    def test_thursday(self):
        start = datetime(2024, 6, 6, 10, 0)  # Thursday 10:00
        deadline = get_deadline_for_intro_call(start)
        assert deadline == datetime(2024, 6, 11, 18, 0)  # Tuesday 18:00
        
    def test_friday(self):
        start = datetime(2024, 6, 7, 14, 0)  # Friday 14:00
        deadline = get_deadline_for_intro_call(start)
        assert deadline == datetime(2024, 6, 12, 18, 0)  # Wednesday 18:00
        
    def test_saturday(self):
        start = datetime(2024, 6, 8, 11, 0)  # Saturday 11:00
        deadline = get_deadline_for_intro_call(start)
        assert deadline == datetime(2024, 6, 12, 18, 0)  # Wednesday 18:00
        
    def test_sunday(self):
        start = datetime(2024, 6, 9, 16, 0)  # Sunday 16:00
        deadline = get_deadline_for_intro_call(start)
        assert deadline == datetime(2024, 6, 12, 18, 0)  # Wednesday 18:00
        

class TestGetIntroCallExtensionDeadline:
    
    def test_Monday(self):
        start = datetime(2024, 6, 3, 18, 5)  # Monday 18:05
        deadline = get_intro_call_extension_deadline(start)
        assert deadline == datetime(2024, 6, 4, 18, 0)  # Tuesday 18:00
        
    def test_Tuesday(self):
        start = datetime(2024, 6, 4, 18, 5)  # Tuesday 18:05
        deadline = get_intro_call_extension_deadline(start)
        assert deadline == datetime(2024, 6, 5, 18, 0)  # Wednesday 18:00
        
    def test_Wednesday(self):
        start = datetime(2024, 6, 5, 18, 5)  # Wednesday 18:05
        deadline = get_intro_call_extension_deadline(start)
        assert deadline == datetime(2024, 6, 6, 18, 0)  # Thursday 18:00
        
    def test_Thursday(self):
        start = datetime(2024, 6, 6, 18, 5)  # Thursday 18:05
        deadline = get_intro_call_extension_deadline(start)
        assert deadline == datetime(2024, 6, 7, 18, 0)  # Friday 18:00
        
    def test_Friday(self):
        start = datetime(2024, 6, 7, 18, 5)  # Friday 18:05
        deadline = get_intro_call_extension_deadline(start)
        assert deadline == datetime(2024, 6, 10, 18, 0)  # Monday 18:00
        
    def test_Saturday(self):
        start = datetime(2024, 6, 8, 18, 5)  # Saturday 18:05
        deadline = get_intro_call_extension_deadline(start)
        assert deadline == datetime(2024, 6, 10, 18, 0)  # Monday 18:00
        
    def test_Sunday(self):
        start = datetime(2024, 6, 9, 18, 5)  # Sunday 18:05
        deadline = get_intro_call_extension_deadline(start)
        assert deadline == datetime(2024, 6, 10, 18, 0)  # Monday 18:00