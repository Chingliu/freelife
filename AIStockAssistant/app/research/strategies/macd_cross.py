from __future__ import annotations

from app.data.models import Bar
from app.research.indicators import macd
from app.research.strategies.base import Strategy


class MacdCrossStrategy(Strategy):
    strategy_id = "macd_cross"
    name = "MACD 金叉死叉"
    description = "DIF 上穿 DEA 开仓，下穿平仓"

    def __init__(
        self,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9,
        **kwargs,
    ) -> None:
        super().__init__(fast=fast, slow=slow, signal=signal, **kwargs)
        self.fast = fast
        self.slow = slow
        self.signal = signal

    def generate(self, bars: list[Bar]) -> list[float]:
        pts = macd([b.close for b in bars], self.fast, self.slow, self.signal)
        out = [0.0] * len(bars)
        position = 0.0
        for i in range(1, len(bars)):
            prev, cur = pts[i - 1], pts[i]
            if None in (prev.dif, prev.dea, cur.dif, cur.dea):
                out[i] = position
                continue
            if prev.dif <= prev.dea and cur.dif > cur.dea:
                position = 1.0
            elif prev.dif >= prev.dea and cur.dif < cur.dea:
                position = 0.0
            out[i] = position
        return out
