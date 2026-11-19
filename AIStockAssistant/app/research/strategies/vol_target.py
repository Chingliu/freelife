from __future__ import annotations

from app.data.models import Bar
from app.research.indicators import realized_volatility
from app.research.strategies.base import Strategy


class VolatilityTargetStrategy(Strategy):
    """Always long but scale weight to target annualized volatility."""

    strategy_id = "vol_target"
    name = "波动率目标仓位"
    description = "按目标年化波动率缩放仓位，高波动降仓"

    def __init__(
        self,
        target_vol: float = 0.12,
        vol_window: int = 20,
        max_weight: float = 1.0,
        **kwargs,
    ) -> None:
        super().__init__(
            target_vol=target_vol,
            vol_window=vol_window,
            max_weight=max_weight,
            **kwargs,
        )
        self.target_vol = target_vol
        self.vol_window = vol_window
        self.max_weight = max_weight

    def generate(self, bars: list[Bar]) -> list[float]:
        vol = realized_volatility([b.close for b in bars], self.vol_window)
        out = [0.0] * len(bars)
        for i, v in enumerate(vol):
            if v is None or v <= 0:
                continue
            w = min(self.max_weight, self.target_vol / float(v))
            out[i] = max(0.0, w)
        return out
