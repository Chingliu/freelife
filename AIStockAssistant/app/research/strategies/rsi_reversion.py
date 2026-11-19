from __future__ import annotations

from app.data.models import Bar
from app.research.indicators import rsi
from app.research.strategies.base import Strategy


class RsiReversionStrategy(Strategy):
    strategy_id = "rsi_reversion"
    name = "RSI 均值回归"
    description = "RSI 跌破超卖线买入，升破超买线卖出"

    def __init__(
        self,
        window: int = 14,
        oversold: float = 30.0,
        overbought: float = 70.0,
        **kwargs,
    ) -> None:
        super().__init__(
            window=window, oversold=oversold, overbought=overbought, **kwargs
        )
        self.window = window
        self.oversold = oversold
        self.overbought = overbought

    def generate(self, bars: list[Bar]) -> list[float]:
        vals = rsi([b.close for b in bars], self.window)
        out = [0.0] * len(bars)
        position = 0.0
        for i, v in enumerate(vals):
            if v is None:
                out[i] = position
                continue
            if v <= self.oversold:
                position = 1.0
            elif v >= self.overbought:
                position = 0.0
            out[i] = position
        return out
