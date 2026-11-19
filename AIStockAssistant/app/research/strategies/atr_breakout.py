from __future__ import annotations

from app.data.models import Bar
from app.research.indicators import atr, sma
from app.research.strategies.base import Strategy


class AtrBreakoutStrategy(Strategy):
    strategy_id = "atr_breakout"
    name = "ATR 通道突破"
    description = "收盘突破 MA+k*ATR 开仓，跌破 MA-k*ATR 平仓"

    def __init__(
        self,
        ma_window: int = 20,
        atr_window: int = 14,
        k: float = 2.0,
        **kwargs,
    ) -> None:
        super().__init__(ma_window=ma_window, atr_window=atr_window, k=k, **kwargs)
        self.ma_window = ma_window
        self.atr_window = atr_window
        self.k = k

    def generate(self, bars: list[Bar]) -> list[float]:
        closes = [b.close for b in bars]
        highs = [b.high for b in bars]
        lows = [b.low for b in bars]
        mid = sma(closes, self.ma_window)
        av = atr(highs, lows, closes, self.atr_window)
        out = [0.0] * len(bars)
        position = 0.0
        for i, c in enumerate(closes):
            if mid[i] is None or av[i] is None:
                out[i] = position
                continue
            upper = float(mid[i]) + self.k * float(av[i])
            lower = float(mid[i]) - self.k * float(av[i])
            if c > upper:
                position = 1.0
            elif c < lower:
                position = 0.0
            out[i] = position
        return out
