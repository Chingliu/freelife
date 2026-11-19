from __future__ import annotations

from app.data.models import Bar
from app.research.indicators import bollinger
from app.research.strategies.base import Strategy


class BollingerReversionStrategy(Strategy):
    strategy_id = "bollinger_reversion"
    name = "布林带均值回归"
    description = "跌破下轨买入，升破中轨卖出"

    def __init__(self, window: int = 20, num_std: float = 2.0, **kwargs) -> None:
        super().__init__(window=window, num_std=num_std, **kwargs)
        self.window = window
        self.num_std = num_std

    def generate(self, bars: list[Bar]) -> list[float]:
        closes = [b.close for b in bars]
        bb = bollinger(closes, self.window, self.num_std)
        out = [0.0] * len(bars)
        position = 0.0
        for i, (c, pt) in enumerate(zip(closes, bb)):
            if pt.lower is None or pt.mid is None:
                out[i] = position
                continue
            if c <= pt.lower:
                position = 1.0
            elif c >= pt.mid:
                position = 0.0
            out[i] = position
        return out
