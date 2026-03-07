"""
Tests for matching.tokens.add_business_hours.

Each test class covers one category of behaviour.  The test names follow the
pattern test_<start_condition>_<duration>, e.g.
test_thursday_11am_plus_24h, so failures are self-documenting.

All datetimes use naive values unless the test is specifically checking
timezone-aware behaviour.
"""

import pytest
from datetime import date, datetime, timezone as dt_timezone

from matching.utils import add_business_hours


# ---------------------------------------------------------------------------
# Category 1 – Zero hours: result must equal the input exactly
# ---------------------------------------------------------------------------

class TestZeroHours:

    def test_zero_hours_returns_same_datetime(self):
        start = datetime(2026, 3, 4, 9, 0)   # Wednesday
        assert add_business_hours(start, 0) == start

    def test_zero_hours_on_friday_returns_same_datetime(self):
        """Friday start with 0 h must NOT jump to Monday."""
        start = datetime(2026, 3, 6, 13, 0)  # Friday
        assert add_business_hours(start, 0) == start


# ---------------------------------------------------------------------------
# Category 2 – Pure weekday: no weekend involved at all
# ---------------------------------------------------------------------------

class TestPureWeekday:

    def test_monday_plus_8h(self):
        # Mon 09:00 + 8 h = Mon 17:00 (office-hours day)
        start = datetime(2026, 3, 2, 9, 0)
        assert add_business_hours(start, 8) == datetime(2026, 3, 2, 17, 0)

    def test_wednesday_plus_48h(self):
        # Wed 09:00 + 48 h (no weekend in range) = Fri 09:00
        start = datetime(2026, 3, 4, 9, 0)
        assert add_business_hours(start, 48) == datetime(2026, 3, 6, 9, 0)

    def test_tuesday_plus_24h(self):
        # Tue 10:30 + 24 h = Wed 10:30
        start = datetime(2026, 3, 3, 10, 30)
        assert add_business_hours(start, 24) == datetime(2026, 3, 4, 10, 30)


# ---------------------------------------------------------------------------
# Category 3 – Single weekend crossing (the core agreed examples)
# ---------------------------------------------------------------------------

class TestSingleWeekendCrossing:

    def test_thursday_11am_plus_24h(self):
        """Thu 11:00 + 24 h → Fri 11:00.  No weekend involved."""
        start = datetime(2026, 3, 5, 11, 0)
        assert add_business_hours(start, 24) == datetime(2026, 3, 6, 11, 0)

    def test_friday_1pm_plus_24h_skips_weekend(self):
        """Fri 13:00 + 24 h → Mon 13:00.  Weekend must be skipped entirely."""
        start = datetime(2026, 3, 6, 13, 0)
        assert add_business_hours(start, 24) == datetime(2026, 3, 9, 13, 0)

    def test_friday_9am_plus_24h(self):
        """Fri 09:00 + 24 h → Mon 09:00."""
        start = datetime(2026, 3, 6, 9, 0)
        assert add_business_hours(start, 24) == datetime(2026, 3, 9, 9, 0)


# ---------------------------------------------------------------------------
# Category 4 – Bridge weekend (start Thursday, skip to Monday)
# ---------------------------------------------------------------------------

class TestBridgeWeekend:

    def test_thursday_1pm_plus_48h(self):
        """Thu 13:00 + 48 h → Mon 13:00.
        +24 h reaches Fri 13:00, +24 more skips the weekend → Mon 13:00.
        """
        start = datetime(2026, 3, 5, 13, 0)
        assert add_business_hours(start, 48) == datetime(2026, 3, 9, 13, 0)

    def test_friday_1pm_plus_48h(self):
        """Fri 13:00 + 48 h → Tue 13:00."""
        start = datetime(2026, 3, 6, 13, 0)
        assert add_business_hours(start, 48) == datetime(2026, 3, 10, 13, 0)

    def test_wednesday_9am_plus_72h(self):
        """Wed 09:00 + 72 h = 3 business days forward → Mon 09:00.
        63 h brings us to Sat 00:00, which skips to Mon 00:00; 9 more h = Mon 09:00.
        """
        start = datetime(2026, 3, 4, 9, 0)
        assert add_business_hours(start, 72) == datetime(2026, 3, 9, 9, 0)


# ---------------------------------------------------------------------------
# Category 5 – Midnight edge cases (cursor lands exactly at a day boundary)
# ---------------------------------------------------------------------------

class TestMidnightEdgeCases:

    def test_friday_11pm_plus_1h_lands_at_monday_midnight(self):
        """Fri 23:00 + 1 h → Sat 00:00 → skip → Mon 00:00."""
        start = datetime(2026, 3, 6, 23, 0)
        assert add_business_hours(start, 1) == datetime(2026, 3, 9, 0, 0)

    def test_friday_6pm_plus_6h_lands_at_monday_midnight(self):
        """Fri 18:00 + 6 h → Sat 00:00 → Mon 00:00."""
        start = datetime(2026, 3, 6, 18, 0)
        assert add_business_hours(start, 6) == datetime(2026, 3, 9, 0, 0)

    def test_friday_6pm_plus_7h_resumes_from_monday_midnight(self):
        """One hour after the above: Mon 01:00."""
        start = datetime(2026, 3, 6, 18, 0)
        assert add_business_hours(start, 7) == datetime(2026, 3, 9, 1, 0)

    def test_start_on_saturday_counts_hours_from_monday(self):
        """Starting on Saturday: first advance lands on Sat 11:00 → skips to Mon 00:00.
        Remaining 23 h are counted from Mon 00:00 → Mon 23:00.
        """
        start = datetime(2026, 3, 7, 10, 0)   # Saturday
        assert add_business_hours(start, 24) == datetime(2026, 3, 9, 23, 0)


# ---------------------------------------------------------------------------
# Category 6 – Holiday support
# ---------------------------------------------------------------------------

class TestHolidays:

    def test_single_holiday_on_landing_day_extends_deadline(self):
        """Mon 09:00 + 8 h = Mon 17:00 normally.
        With Mon as holiday:
          i=0: Mon 10:00 → holiday → skip to Tue 00:00
          i=1..7: Tue 01:00 … Tue 07:00
        """
        start = datetime(2026, 3, 2, 9, 0)   # Monday
        holiday = {date(2026, 3, 2)}          # same Monday is a holiday
        assert add_business_hours(start, 8, holidays=holiday) == datetime(2026, 3, 3, 7, 0)

    def test_holiday_on_friday_extends_into_monday(self):
        """Thu 11:00 + 24 h → Fri 11:00 normally.
        With Friday as holiday:
          Thu 11:00 + 13 h = Fri 00:00 → holiday →
          skip to Sat 00:00 → weekend → Mon 00:00.
          Remaining 11 h counted from Mon 00:00 → Mon 11:00.
        """
        start = datetime(2026, 3, 5, 11, 0)   # Thursday
        holiday = {date(2026, 3, 6)}           # Friday
        assert add_business_hours(start, 24, holidays=holiday) == datetime(2026, 3, 9, 11, 0)

    def test_empty_holiday_set_behaves_like_no_holidays(self):
        """Passing an empty set must produce the same result as no holidays."""
        start = datetime(2026, 3, 6, 13, 0)
        assert add_business_hours(start, 24, holidays=set()) == datetime(2026, 3, 9, 13, 0)

    def test_none_holidays_behaves_like_no_holidays(self):
        """None (the default) must produce the same result as an empty set."""
        start = datetime(2026, 3, 6, 13, 0)
        assert add_business_hours(start, 24, holidays=None) == datetime(2026, 3, 9, 13, 0)


# ---------------------------------------------------------------------------
# Category 7 – Timezone-aware datetimes
# ---------------------------------------------------------------------------

class TestTimezoneAware:

    def test_utc_aware_datetime_preserves_tzinfo(self):
        """Result must remain timezone-aware with the same tzinfo."""
        start = datetime(2026, 3, 5, 11, 0, tzinfo=dt_timezone.utc)  # Thu 11:00 UTC
        result = add_business_hours(start, 24)
        assert result == datetime(2026, 3, 6, 11, 0, tzinfo=dt_timezone.utc)
        assert result.tzinfo is not None

    def test_utc_aware_friday_skips_weekend(self):
        start = datetime(2026, 3, 6, 13, 0, tzinfo=dt_timezone.utc)  # Fri 13:00 UTC
        result = add_business_hours(start, 24)
        assert result == datetime(2026, 3, 9, 13, 0, tzinfo=dt_timezone.utc)


# ---------------------------------------------------------------------------
# Category 8 – Invalid input
# ---------------------------------------------------------------------------

class TestInvalidInput:

    def test_negative_hours_raises_value_error(self):
        with pytest.raises(ValueError, match="hours must be >= 0"):
            add_business_hours(datetime(2026, 3, 5, 9, 0), -1)

    def test_negative_large_raises_value_error(self):
        with pytest.raises(ValueError):
            add_business_hours(datetime(2026, 3, 5, 9, 0), -100)
