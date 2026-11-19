from __future__ import annotations

from datetime import date

from app.data.day_bar_validate import (
    bars_match,
    continuity_ok,
    effective_target,
    select_writable_bars,
)
from app.data.models import Bar


def _bar(code: str, d: date, close: float, volume: float = 1_000_000.0) -> Bar:
    return Bar(
        code=code,
        trade_date=d,
        open=close,
        high=close + 0.01,
        low=close - 0.01,
        close=close,
        volume=volume,
        amount=close * volume,
    )


def test_continuity_rejects_spike() -> None:
    prev = _bar("sh513500", date(2026, 7, 23), 2.524)
    bad = _bar("sh513500", date(2026, 7, 24), 0.417)
    good = _bar("sh513500", date(2026, 7, 24), 2.506)
    assert not continuity_ok(prev, bad)
    assert continuity_ok(prev, good)


def test_bars_match_volume_and_price() -> None:
    a = _bar("sh513500", date(2026, 7, 27), 2.509, volume=35_000_000)
    b = _bar("sh513500", date(2026, 7, 27), 2.520, volume=114_000_000)
    assert not bars_match(a, b)
    c = _bar("sh513500", date(2026, 7, 27), 2.520, volume=114_000_000)
    assert bars_match(b, c)


def test_select_writable_skips_spike_keeps_good() -> None:
    existing = [_bar("sh513500", date(2026, 7, 23), 2.524)]
    incoming = [
        _bar("sh513500", date(2026, 7, 24), 0.417),
        _bar("sh513500", date(2026, 7, 27), 2.520),
    ]
    # After rejecting 07-24, 07-27 is checked vs 07-23 prior — still ok (~0.16%).
    out = select_writable_bars(existing, incoming, target=date(2026, 7, 27))
    assert [b.trade_date for b in out] == [date(2026, 7, 27)]
    assert abs(out[0].close - 2.520) < 1e-9


def test_effective_target_caps_to_hq() -> None:
    bars = [
        _bar("sh510300", date(2026, 7, 24), 4.0),
        _bar("sh510300", date(2026, 7, 27), 4.1),
    ]
    assert effective_target(bars, date(2026, 7, 28)) == date(2026, 7, 27)
    assert effective_target([], date(2026, 7, 28)) is None
