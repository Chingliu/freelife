"""Cross-check helpers for vipdoc daily bars vs HQ payloads."""

from __future__ import annotations

import logging
from datetime import date

from app.data.models import Bar

logger = logging.getLogger(__name__)

# Relative close tolerance for "local matches HQ" (2%).
DEFAULT_PRICE_TOL = 0.02
# Relative volume tolerance (15%) — mid-session vs EOD often diverges more.
DEFAULT_VOL_TOL = 0.15
# Reject bars that jump more than this vs prior close (catches 0.42 vs 2.52).
DEFAULT_MAX_DAY_MOVE = 0.50


def rel_diff(a: float, b: float) -> float:
    base = max(abs(a), abs(b), 1e-12)
    return abs(a - b) / base


def ohlc_sane(bar: Bar) -> bool:
    if bar.close <= 0 or bar.open <= 0 or bar.high <= 0 or bar.low <= 0:
        return False
    if bar.high + 1e-12 < max(bar.open, bar.close):
        return False
    if bar.low - 1e-12 > min(bar.open, bar.close):
        return False
    if bar.high < bar.low:
        return False
    return True


def continuity_ok(
    prev: Bar | None,
    bar: Bar,
    *,
    max_day_move: float = DEFAULT_MAX_DAY_MOVE,
) -> bool:
    """True if bar looks plausible vs previous session close."""
    if not ohlc_sane(bar):
        return False
    if prev is None or prev.close <= 0:
        return True
    return rel_diff(bar.close, prev.close) <= max_day_move


def bars_match(
    local: Bar,
    hq: Bar,
    *,
    price_tol: float = DEFAULT_PRICE_TOL,
    vol_tol: float = DEFAULT_VOL_TOL,
) -> bool:
    """True when local settled bar agrees with a fresh HQ fetch."""
    if local.trade_date != hq.trade_date:
        return False
    for attr in ("open", "high", "low", "close"):
        if rel_diff(float(getattr(local, attr)), float(getattr(hq, attr))) > price_tol:
            return False
    # Zero/tiny volume on either side: require both tiny or both substantial.
    lv, hv = float(local.volume), float(hq.volume)
    if max(lv, hv) < 1.0:
        return True
    if min(lv, hv) < 1.0:
        return False
    return rel_diff(lv, hv) <= vol_tol


def pick_bar_for_date(bars: list[Bar], day: date) -> Bar | None:
    for b in bars:
        if b.trade_date == day:
            return b
    return None


def effective_target(hq_bars: list[Bar], wall_target: date) -> date | None:
    """
    Wall-clock settled date capped by what HQ actually returned
    (handles holidays / late publish).
    """
    dates = [b.trade_date for b in hq_bars if b.trade_date <= wall_target]
    return max(dates) if dates else None


def filter_bars_through(bars: list[Bar], max_date: date) -> list[Bar]:
    return [b for b in bars if b.trade_date <= max_date]


def select_writable_bars(
    existing: list[Bar],
    incoming: list[Bar],
    *,
    target: date,
    max_day_move: float = DEFAULT_MAX_DAY_MOVE,
) -> list[Bar]:
    """
    Keep incoming bars through target that pass continuity vs prior close.

    Skips individual bad HQ days (log) instead of poisoning the file.
    """
    by_date = {b.trade_date: b for b in existing if b.trade_date <= target}
    out: list[Bar] = []
    for bar in sorted(incoming, key=lambda b: b.trade_date):
        if bar.trade_date > target:
            continue
        prev = by_date.get(bar.trade_date)
        # Prefer chronological prior session for continuity.
        prior_dates = [d for d in by_date if d < bar.trade_date]
        prior = by_date[max(prior_dates)] if prior_dates else None
        # When replacing same date, continuity vs session before that date.
        if not continuity_ok(prior, bar, max_day_move=max_day_move):
            logger.warning(
                "reject HQ bar %s %s close=%s (prior=%s): day move / OHLC check failed",
                bar.code,
                bar.trade_date,
                bar.close,
                prior.close if prior else None,
            )
            continue
        out.append(bar)
        by_date[bar.trade_date] = bar
    return out
