"""A-share session helpers for settled (EOD) daily bars."""

from __future__ import annotations

from datetime import date, datetime, timedelta


def previous_weekday(day: date) -> date:
    """Previous Mon–Fri calendar day (holidays ignored)."""
    d = day - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def settled_as_of(
    now: datetime | None = None,
    *,
    eod_hour: int = 16,
    eod_minute: int = 0,
) -> date:
    """
    Latest session date whose daily OHLCV should be treated as final.

    Before the EOD cutoff on a weekday, "today" is still forming — use the
    previous weekday. On/after cutoff, weekday "today" is eligible.
    Weekends resolve to the prior Friday.
    """
    now = now or datetime.now()
    today = now.date()
    cutoff = now.replace(hour=eod_hour, minute=eod_minute, second=0, microsecond=0)
    if today.weekday() >= 5:
        return previous_weekday(today)
    if now < cutoff:
        return previous_weekday(today)
    return today
