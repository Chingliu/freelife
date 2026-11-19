"""Smoke / regression guards for Tongdaxin .day price scaling.

Catches the class of bugs where ETF/fund/bond prices are mis-scaled
(e.g. 510050 shown as 30.84 instead of 3.084).
"""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from app.data.tdx_day_reader import FMT, price_divisor, read_day_file

# Loose bands for liquid anchors — wide enough to survive years, tight enough
# to catch a 10x / 100x scale bug.
LIVE_PRICE_BANDS: dict[str, tuple[float, float]] = {
    "sh600000": (2.0, 40.0),  # A-share
    "sz000001": (2.0, 40.0),
    "sh000001": (1500.0, 8000.0),  # index
    "sz399001": (4000.0, 30000.0),
    "sh510050": (1.0, 10.0),  # equity ETF (the original bug)
    "sh510300": (1.5, 15.0),
    "sz159915": (0.8, 10.0),
    "sh511880": (90.0, 110.0),  # money-market ETF ~100
    "sh511010": (80.0, 200.0),  # bond ETF
}


def _pack_bar(
    yyyymmdd: int,
    open_: int,
    high: int,
    low: int,
    close: int,
    amount: float = 1.0e6,
    volume: int = 1000,
) -> bytes:
    return struct.pack(FMT, yyyymmdd, open_, high, low, close, amount, volume, 0)


def _write_day(tmp_path: Path, code: str, raw_ohlc: tuple[int, int, int, int]) -> Path:
    market = code[:2]
    path = tmp_path / market / "lday" / f"{code}.day"
    path.parent.mkdir(parents=True, exist_ok=True)
    o, h, l, c = raw_ohlc
    path.write_bytes(_pack_bar(20260723, o, h, l, c))
    return path


def _assert_bar_invariants(code: str, close: float, open_: float, high: float, low: float) -> None:
    assert close > 0, f"{code}: non-positive close {close}"
    assert high >= max(open_, close) - 1e-9, f"{code}: high < open/close"
    assert low <= min(open_, close) + 1e-9, f"{code}: low > open/close"
    assert high >= low, f"{code}: high < low"


# ---------------------------------------------------------------------------
# Always-on synthetic guards (no vipdoc required)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "code,raw_close,expected_close",
    [
        ("sh600000", 905, 9.05),
        ("sh000001", 387678, 3876.78),
        ("sh510050", 3084, 3.084),
        ("sh511880", 100643, 100.643),
        ("sz159915", 3597, 3.597),
        ("sz161725", 548, 0.548),
        ("sh110059", 1108000, 110.8),
        ("sz127045", 1250950, 125.095),
    ],
)
def test_synthetic_day_price_scale(
    tmp_path: Path, code: str, raw_close: int, expected_close: float
) -> None:
    raw = (raw_close, raw_close, raw_close, raw_close)
    path = _write_day(tmp_path, code, raw)
    bars = read_day_file(path, code=code)
    assert len(bars) == 1
    assert bars[0].close == pytest.approx(expected_close, rel=0, abs=1e-6)
    _assert_bar_invariants(code, bars[0].close, bars[0].open, bars[0].high, bars[0].low)


def test_etf_tenx_bug_is_rejected_by_band() -> None:
    """Document the original failure mode: /100 on ETF → 10x price."""
    wrong = 3084 / 100.0
    lo, hi = LIVE_PRICE_BANDS["sh510050"]
    assert not (lo <= wrong <= hi)


def test_price_divisor_table_is_complete_for_common_prefixes() -> None:
    assert price_divisor("sh600000") == 100.0
    assert price_divisor("sz300750") == 100.0
    assert price_divisor("bj920000") == 100.0
    assert price_divisor("sh510050") == 1000.0
    assert price_divisor("sz159915") == 1000.0
    assert price_divisor("sh204001") == 1000.0
    assert price_divisor("sh110059") == 10000.0
    assert price_divisor("sz127045") == 10000.0


# ---------------------------------------------------------------------------
# Local vipdoc smoke (skipped when data absent)
# ---------------------------------------------------------------------------


@pytest.mark.smoke
def test_live_anchor_prices_in_band(require_vipdoc: Path) -> None:
    failures: list[str] = []
    checked = 0
    for code, (lo, hi) in LIVE_PRICE_BANDS.items():
        market = code[:2]
        path = require_vipdoc / market / "lday" / f"{code}.day"
        if not path.is_file():
            continue
        bars = read_day_file(path)
        if not bars:
            failures.append(f"{code}: empty bars")
            continue
        last = bars[-1]
        checked += 1
        _assert_bar_invariants(code, last.close, last.open, last.high, last.low)
        if not (lo <= last.close <= hi):
            failures.append(
                f"{code}: close={last.close} outside [{lo}, {hi}] "
                f"(date={last.trade_date}, divisor={price_divisor(code)})"
            )
    assert checked >= 3, "need at least 3 anchor .day files for smoke"
    assert not failures, "price-scale smoke failures:\n" + "\n".join(failures)


@pytest.mark.smoke
def test_live_sample_ohlc_invariants_by_category(require_vipdoc: Path) -> None:
    """Sample liquid names across categories; catch broken OHLC / empty files."""
    samples = [
        "sh600000",
        "sz000001",
        "sh000001",
        "sh510050",
        "sh510300",
        "sz159915",
        "sh511880",
        "sz161725",
    ]
    seen = 0
    for code in samples:
        path = require_vipdoc / code[:2] / "lday" / f"{code}.day"
        if not path.is_file():
            continue
        bars = read_day_file(path)
        assert bars, f"{code}: no bars"
        last = bars[-1]
        _assert_bar_invariants(code, last.close, last.open, last.high, last.low)
        # Dates should be chronological in file
        assert bars[0].trade_date <= bars[-1].trade_date
        seen += 1
    assert seen >= 3


@pytest.mark.smoke
def test_analysis_service_etf_close_not_inflated(require_vipdoc: Path) -> None:
    from app.ai.service import AnalysisService
    from app.config.settings import Settings

    svc = AnalysisService(
        Settings.from_dict(
            {
                "data": {
                    "provider": "tdx_local",
                    "tdx": {"vipdoc": str(require_vipdoc)},
                }
            }
        )
    )
    path = require_vipdoc / "sh" / "lday" / "sh510050.day"
    if not path.is_file():
        pytest.skip("sh510050.day missing")
    bars = svc.get_daily_bars("sh510050", limit=1)
    assert bars
    close = float(bars[0]["close"])
    lo, hi = LIVE_PRICE_BANDS["sh510050"]
    assert lo <= close <= hi, f"MCP path still returns inflated ETF price: {close}"
