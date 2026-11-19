from __future__ import annotations

from app.data.models import Bar
from app.research.indicators import rsrs
from app.research.strategies.base import Strategy


class RsrsTimingStrategy(Strategy):
    strategy_id = "rsrs_timing"
    name = "RSRS 择时"
    description = "RSRS z-score 上穿买入阈值开仓，下穿卖出阈值平仓"

    def __init__(
        self,
        window: int = 18,
        z_window: int = 600,
        buy_th: float = 0.7,
        sell_th: float = -0.7,
        **kwargs,
    ) -> None:
        super().__init__(
            window=window,
            z_window=z_window,
            buy_th=buy_th,
            sell_th=sell_th,
            **kwargs,
        )
        self.window = window
        self.z_window = z_window
        self.buy_th = buy_th
        self.sell_th = sell_th

    def generate(self, bars: list[Bar]) -> list[float]:
        z = rsrs(
            [b.high for b in bars],
            [b.low for b in bars],
            window=self.window,
            z_window=self.z_window,
        )
        out = [0.0] * len(bars)
        position = 0.0
        for i, v in enumerate(z):
            if v is None:
                out[i] = position
                continue
            if v >= self.buy_th:
                position = 1.0
            elif v <= self.sell_th:
                position = 0.0
            out[i] = position
        return out
