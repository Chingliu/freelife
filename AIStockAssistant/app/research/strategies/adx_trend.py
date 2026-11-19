from __future__ import annotations

from app.data.models import Bar
from app.research.indicators import adx, sma
from app.research.strategies.base import Strategy


class AdxTrendStrategy(Strategy):
    strategy_id = "adx_ma_trend"
    name = "ADX 过滤趋势"
    description = "MA 多头且 ADX 高于阈值才持仓，降低震荡市假信号"

    def __init__(
        self,
        short: int = 20,
        long: int = 60,
        adx_window: int = 14,
        adx_min: float = 20.0,
        **kwargs,
    ) -> None:
        super().__init__(
            short=short, long=long, adx_window=adx_window, adx_min=adx_min, **kwargs
        )
        self.short = short
        self.long = long
        self.adx_window = adx_window
        self.adx_min = adx_min

    def generate(self, bars: list[Bar]) -> list[float]:
        closes = [b.close for b in bars]
        ms = sma(closes, self.short)
        ml = sma(closes, self.long)
        adx_v, _, _ = adx(
            [b.high for b in bars],
            [b.low for b in bars],
            closes,
            self.adx_window,
        )
        out = [0.0] * len(bars)
        for i in range(len(bars)):
            if ms[i] is None or ml[i] is None or adx_v[i] is None:
                continue
            out[i] = (
                1.0
                if ms[i] > ml[i] and float(adx_v[i]) >= self.adx_min
                else 0.0
            )
        return out
