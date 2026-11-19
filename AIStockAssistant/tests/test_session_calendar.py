from __future__ import annotations

from datetime import date, datetime

from app.data.session_calendar import previous_weekday, settled_as_of


def test_previous_weekday_skips_weekend() -> None:
    assert previous_weekday(date(2026, 7, 27)) == date(2026, 7, 24)  # Mon -> Fri
    assert previous_weekday(date(2026, 7, 25)) == date(2026, 7, 24)  # Sat -> Fri


def test_settled_as_of_before_eod_uses_previous_session() -> None:
    # Tuesday 10:00 — settled = Monday
    now = datetime(2026, 7, 28, 10, 0, 0)
    assert settled_as_of(now, eod_hour=16, eod_minute=0) == date(2026, 7, 27)


def test_settled_as_of_after_eod_uses_today() -> None:
    now = datetime(2026, 7, 28, 16, 0, 0)
    assert settled_as_of(now, eod_hour=16, eod_minute=0) == date(2026, 7, 28)


def test_settled_as_of_weekend_uses_friday() -> None:
    now = datetime(2026, 7, 26, 12, 0, 0)  # Sunday
    assert settled_as_of(now, eod_hour=16, eod_minute=0) == date(2026, 7, 24)
