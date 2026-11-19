"""L2 liquidity / listing / ST / suspend filters."""

from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from typing import Any

from app.data.models import Bar
from app.data.provider import IDataProvider
from app.selection.meta import MetaStore
from app.selection.types import FilterReject, FilterResult


def apply_filters(
    codes: list[str],
    provider: IDataProvider,
    meta: MetaStore,
    *,
    min_listing_days: int = 365,
    min_avg_amount_20d: float = 50_000_000.0,
    min_bars: int = 120,
    as_of: date | None = None,
) -> FilterResult:
    kept: list[str] = []
    rejected: list[FilterReject] = []
    gaps: list[str] = []
    st_available = meta.has_st_flags()
    suspend_available = meta.has_suspend_flags()
    if not st_available:
        gaps.append("ST filter skipped: no st_flags.json")
    if not suspend_available:
        gaps.append("suspend filter skipped: no suspend_flags.json")

    for code in codes:
        bars = provider.get_daily_bars(code)
        if len(bars) < min_bars:
            rejected.append(FilterReject(code, "insufficient_bars"))
            continue

        if st_available:
            st = meta.is_st(code)
            if st is True:
                rejected.append(FilterReject(code, "st"))
                continue
        if suspend_available:
            sus = meta.is_suspended(code)
            if sus is True:
                rejected.append(FilterReject(code, "suspended"))
                continue

        first = bars[0].trade_date
        last = bars[-1].trade_date
        ref = as_of or last
        if (ref - first).days < min_listing_days:
            rejected.append(FilterReject(code, "ipo_lt_1y"))
            continue

        avg_amt = _avg_amount(bars, 20)
        if avg_amt is None or avg_amt < min_avg_amount_20d:
            rejected.append(FilterReject(code, "low_turnover"))
            continue

        kept.append(code)

    counts = Counter(r.reason for r in rejected)
    return FilterResult(
        kept=kept,
        rejected=rejected,
        reason_counts=dict(counts),
        gaps=gaps,
    )


def _avg_amount(bars: list[Bar], window: int) -> float | None:
    if not bars:
        return None
    chunk = bars[-window:]
    if not chunk:
        return None
    return sum(b.amount for b in chunk) / len(chunk)


def filter_config_dict() -> dict[str, Any]:
    return {
        "min_listing_days": 365,
        "min_avg_amount_20d": 50_000_000.0,
        "min_bars": 120,
    }
