from __future__ import annotations

from app.data.models import Bar
from app.research.indicators import momentum
from app.research.strategies.base import Strategy


class DualMomentumStrategy(Strategy):
    """Absolute momentum: hold risk asset iff lookback return > threshold."""

    strategy_id = "dual_momentum"
    name = "绝对动量择时"
    description = "过去 N 日收益高于阈值则满仓，否则空仓"

    def __init__(
        self,
        lookback: int = 252,
        threshold: float = 0.0,
        **kwargs,
    ) -> None:
        super().__init__(lookback=lookback, threshold=threshold, **kwargs)
        self.lookback = lookback
        self.threshold = threshold

    def generate(self, bars: list[Bar]) -> list[float]:
        closes = [b.close for b in bars]
        mom = momentum(closes, self.lookback)
        out = [0.0] * len(bars)
        for i, m in enumerate(mom):
            if m is None:
                continue
            out[i] = 1.0 if m > self.threshold else 0.0
        return out
