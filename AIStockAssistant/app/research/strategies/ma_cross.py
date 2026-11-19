from __future__ import annotations

from app.data.models import Bar
from app.research.indicators import sma
from app.research.strategies.base import Strategy


class MaCrossStrategy(Strategy):
    """Classic MA golden/death cross, long-only."""

    def __init__(self, short: int = 5, long: int = 20, **kwargs) -> None:
        super().__init__(short=short, long=long, **kwargs)
        self.short = short
        self.long = long
        self.strategy_id = f"ma_{short}_{long}"
        self.name = f"{short}日/{long}日均线趋势交叉"
        self.description = f"{short}日均线上穿{long}日均线开仓，下穿平仓"

    def generate(self, bars: list[Bar]) -> list[float]:
        closes = [b.close for b in bars]
        ms = sma(closes, self.short)
        ml = sma(closes, self.long)
        out = [0.0] * len(bars)
        position = 0.0
        for i in range(1, len(bars)):
            if ms[i] is None or ml[i] is None or ms[i - 1] is None or ml[i - 1] is None:
                out[i] = position
                continue
            if ms[i - 1] <= ml[i - 1] and ms[i] > ml[i]:
                position = 1.0
            elif ms[i - 1] >= ml[i - 1] and ms[i] < ml[i]:
                position = 0.0
            out[i] = position
        return out
