from __future__ import annotations

from app.data.models import Bar
from app.research.indicators import kdj
from app.research.strategies.base import Strategy


class KdjCrossStrategy(Strategy):
    strategy_id = "kdj_cross"
    name = "KDJ 金叉死叉"
    description = "K 上穿 D 且位于低位区开仓，K 下穿 D 平仓"

    def __init__(self, n: int = 9, low_zone: float = 30.0, **kwargs) -> None:
        super().__init__(n=n, low_zone=low_zone, **kwargs)
        self.n = n
        self.low_zone = low_zone

    def generate(self, bars: list[Bar]) -> list[float]:
        pts = kdj(
            [b.high for b in bars],
            [b.low for b in bars],
            [b.close for b in bars],
            n=self.n,
        )
        out = [0.0] * len(bars)
        position = 0.0
        for i in range(1, len(bars)):
            prev, cur = pts[i - 1], pts[i]
            if None in (prev.k, prev.d, cur.k, cur.d):
                out[i] = position
                continue
            if prev.k <= prev.d and cur.k > cur.d and cur.k <= self.low_zone + 20:
                position = 1.0
            elif prev.k >= prev.d and cur.k < cur.d:
                position = 0.0
            out[i] = position
        return out
