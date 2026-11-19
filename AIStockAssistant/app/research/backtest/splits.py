"""Chronological train / valid / test splits for Phase-2 L1 OOS."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from app.data.models import Bar
from app.research.backtest.horizons import metrics_dict, metrics_on_slice
from app.research.backtest.types import Trade


@dataclass(frozen=True)
class SplitBounds:
    """Inclusive calendar bounds; labels are 历史段/校准段/样本外段."""

    train_start: date | None
    train_end: date | None
    valid_start: date | None
    valid_end: date | None
    test_start: date | None
    test_end: date | None

    def to_dict(self) -> dict[str, Any]:
        def _iso(d: date | None) -> str | None:
            return d.isoformat() if d else None

        return {
            "train": {"start": _iso(self.train_start), "end": _iso(self.train_end), "label": "历史段"},
            "valid": {"start": _iso(self.valid_start), "end": _iso(self.valid_end), "label": "校准段"},
            "test": {"start": _iso(self.test_start), "end": _iso(self.test_end), "label": "样本外段"},
            "note": (
                "信号可用全历史预热；绩效仅统计各段内路径。"
                "固定参数策略下历史段为画像，样本外段为可推荐依据。"
            ),
        }


def chronological_split(
    bars: list[Bar],
    *,
    ratios: tuple[float, float, float] = (0.6, 0.2, 0.2),
) -> SplitBounds:
    """Split by bar count ratios (train/valid/test)."""
    if not bars:
        return SplitBounds(None, None, None, None, None, None)
    n = len(bars)
    r0, r1, r2 = ratios
    s = r0 + r1 + r2
    r0, r1, r2 = r0 / s, r1 / s, r2 / s
    n_train = max(1, int(n * r0))
    n_valid = max(1, int(n * r1))
    if n_train + n_valid >= n:
        n_train = max(1, n // 2)
        n_valid = max(1, (n - n_train) // 2)
    n_test = n - n_train - n_valid
    if n_test < 1:
        n_test = 1
        n_valid = max(1, n - n_train - n_test)
    i0 = n_train - 1
    i1 = n_train + n_valid - 1
    dates = [b.trade_date for b in bars]
    return SplitBounds(
        train_start=dates[0],
        train_end=dates[i0],
        valid_start=dates[n_train] if n_train < n else dates[-1],
        valid_end=dates[i1] if i1 < n else dates[-1],
        test_start=dates[n_train + n_valid] if n_train + n_valid < n else dates[-1],
        test_end=dates[-1],
    )


def holdout_last_years(bars: list[Bar], *, n: float = 1.0) -> SplitBounds:
    """
    Test = last n calendar years; valid = prior n years; train = remainder.
    Falls back to chronological_split if history is short.
    """
    if len(bars) < 60:
        return chronological_split(bars)
    end = bars[-1].trade_date
    test_start = end - timedelta(days=int(365 * n))
    valid_start = test_start - timedelta(days=int(365 * n))
    dates = [b.trade_date for b in bars]
    # Ensure non-empty segments
    test_bars = [d for d in dates if d >= test_start]
    valid_bars = [d for d in dates if valid_start <= d < test_start]
    train_bars = [d for d in dates if d < valid_start]
    if len(test_bars) < 20 or len(train_bars) < 40:
        return chronological_split(bars)
    return SplitBounds(
        train_start=train_bars[0],
        train_end=train_bars[-1],
        valid_start=valid_bars[0] if valid_bars else None,
        valid_end=valid_bars[-1] if valid_bars else None,
        test_start=test_bars[0],
        test_end=test_bars[-1],
    )


def oos_metrics_for_result(
    equity: list[float],
    dates: list[date],
    positions: list[float],
    trades: list[Trade],
    bounds: SplitBounds,
) -> dict[str, Any]:
    """Compute train/valid/test metrics dicts for one backtest path."""

    def _one(start: date | None, end: date | None) -> dict[str, Any]:
        if start is None or end is None:
            return metrics_dict(None, status="insufficient")
        m = metrics_on_slice(
            equity, dates, positions, trades, start=start, end=end
        )
        if m is None:
            return metrics_dict(None, status="insufficient")
        return metrics_dict(m)

    return {
        "train": _one(bounds.train_start, bounds.train_end),
        "valid": _one(bounds.valid_start, bounds.valid_end),
        "test": _one(bounds.test_start, bounds.test_end),
        "bounds": bounds.to_dict(),
    }


def oos_pass(test_metrics: dict[str, Any], *, min_calmar: float = 0.0) -> bool:
    """Sample-out pass: status ok and Calmar above threshold."""
    if not test_metrics or test_metrics.get("status") != "ok":
        return False
    cal = test_metrics.get("calmar")
    return cal is not None and float(cal) > min_calmar
