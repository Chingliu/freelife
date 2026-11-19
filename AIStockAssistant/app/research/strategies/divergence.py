"""Regular MACD/RSI price–oscillator divergence strategies (long-only)."""

from __future__ import annotations

from app.data.models import Bar
from app.research.indicators import detect_regular_divergences, macd, rsi
from app.research.strategies.base import Strategy


def _weights_from_events(
    events: list[str | None],
    *,
    max_hold: int,
) -> list[float]:
    out = [0.0] * len(events)
    position = 0.0
    bars_held = 0
    for i, ev in enumerate(events):
        if position > 0:
            bars_held += 1
            if bars_held >= max_hold:
                position = 0.0
                bars_held = 0
        if ev == "bullish":
            position = 1.0
            bars_held = 0
        elif ev == "bearish" and position > 0:
            position = 0.0
            bars_held = 0
        out[i] = position
    return out


class RsiDivergenceStrategy(Strategy):
    strategy_id = "rsi_divergence"
    name = "RSI 顶底背离"
    description = "价格与 RSI 常规底背离开仓，顶背离或最长持仓到期平仓"

    def __init__(
        self,
        rsi_window: int = 14,
        left: int = 5,
        right: int = 5,
        min_bars: int = 6,
        min_osc_delta: float = 3.0,
        max_hold: int = 60,
        **kwargs,
    ) -> None:
        super().__init__(
            rsi_window=rsi_window,
            left=left,
            right=right,
            min_bars=min_bars,
            min_osc_delta=min_osc_delta,
            max_hold=max_hold,
            **kwargs,
        )
        self.rsi_window = rsi_window
        self.left = left
        self.right = right
        self.min_bars = min_bars
        self.min_osc_delta = min_osc_delta
        self.max_hold = max_hold

    def generate(self, bars: list[Bar]) -> list[float]:
        closes = [b.close for b in bars]
        osc = rsi(closes, self.rsi_window)
        events = detect_regular_divergences(
            closes,
            osc,
            left=self.left,
            right=self.right,
            min_bars=self.min_bars,
            min_osc_delta=self.min_osc_delta,
        )
        return _weights_from_events(events, max_hold=self.max_hold)


class MacdDivergenceStrategy(Strategy):
    strategy_id = "macd_divergence"
    name = "MACD 顶底背离"
    description = "价格与 MACD DIF 常规底背离开仓，顶背离或最长持仓到期平仓"

    def __init__(
        self,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9,
        left: int = 5,
        right: int = 5,
        min_bars: int = 6,
        min_osc_delta: float = 0.0,
        min_osc_rel: float = 0.05,
        max_hold: int = 60,
        **kwargs,
    ) -> None:
        super().__init__(
            fast=fast,
            slow=slow,
            signal=signal,
            left=left,
            right=right,
            min_bars=min_bars,
            min_osc_delta=min_osc_delta,
            min_osc_rel=min_osc_rel,
            max_hold=max_hold,
            **kwargs,
        )
        self.fast = fast
        self.slow = slow
        self.signal = signal
        self.left = left
        self.right = right
        self.min_bars = min_bars
        self.min_osc_delta = min_osc_delta
        self.min_osc_rel = min_osc_rel
        self.max_hold = max_hold

    def generate(self, bars: list[Bar]) -> list[float]:
        closes = [b.close for b in bars]
        pts = macd(closes, self.fast, self.slow, self.signal)
        osc = [p.dif for p in pts]
        events = detect_regular_divergences(
            closes,
            osc,
            left=self.left,
            right=self.right,
            min_bars=self.min_bars,
            min_osc_delta=self.min_osc_delta,
            min_osc_rel=self.min_osc_rel,
        )
        return _weights_from_events(events, max_hold=self.max_hold)
